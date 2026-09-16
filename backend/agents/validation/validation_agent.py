"""
agents/validation/validation_agent.py
---------------------------------------
Validation Agent — documentation quality assurance.

Responsibilities (SRS Part 6):
- Validate every generated document for completeness, accuracy,
  consistency, formatting, and hallucinations.
- Produce a structured validation report.
- Compute an overall quality score (0–100).
- Write the report into SharedMemory.validation.
- Return PASSED, PASSED_WITH_WARNINGS, or FAILED status.

This agent MUST NOT:
- Modify or rewrite documentation.
- Read repository files directly.
- Use Git.
- Save files to disk.
- Generate new documentation.
"""

import logging
import re
import time
from dataclasses import dataclass, field

from agents.coordinator.coordinator import AgentResult
from agents.documentation.context_slicer import ContextSlicer
from agents.memory.shared_memory import SharedMemory, ValidationReport
from prompts.validation_prompt import (
    DOCUMENT_VALIDATION_PROMPT,
    CONSISTENCY_VALIDATION_PROMPT,
    FAITHFULNESS_VALIDATION_PROMPT,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Thresholds  (SRS Part 6, Section 19)
# ---------------------------------------------------------------------------

PASS_THRESHOLD: float = 70.0          # minimum score to PASS
WARN_THRESHOLD: float = 85.0          # score above this = PASSED, below = PASSED_WITH_WARNINGS

# Below this faithfulness score (when the check actually ran), the document
# is forced to FAILED regardless of structural quality — 50 is the
# FAITHFULNESS_VALIDATION_PROMPT's own rubric midpoint ("half the claims are
# traceable"). Without this floor a structurally polished but fabricated
# document (e.g. inventing "Flask" instead of "FastAPI") could still pass
# and would never reach the Revision Agent.
FAITHFULNESS_FLOOR: float = 50.0

# ---------------------------------------------------------------------------
# Quality score weights  (SRS Part 6, Section 16)
# ---------------------------------------------------------------------------

WEIGHT_COMPLETENESS: float = 0.25
WEIGHT_ACCURACY: float = 0.30
WEIGHT_CONSISTENCY: float = 0.20
WEIGHT_MARKDOWN: float = 0.10
WEIGHT_COVERAGE: float = 0.10
WEIGHT_READABILITY: float = 0.05

# Only folded into overall_score when faithfulness was actually checked
# (LLM + RAG context + at least one non-empty doc available) — see
# _compute_overall_score's applied_weight_sum normalisation.
WEIGHT_FAITHFULNESS: float = 0.20

# LLM-authored documents checked for groundedness against RAG context.
# REPORTS.md is deliberately excluded: it's rendered deterministically from
# static-analysis data (code_reports.py), not LLM-authored, so it can't
# hallucinate.
FAITHFULNESS_CHECKED_DOCS: list[str] = [
    "README.md", "ARCHITECTURE.md", "WORKFLOW.md", "CHANGELOG.md", "SECURITY.md",
]

# Per-document truncation applied before sending to the faithfulness judge.
FAITHFULNESS_DOC_CHAR_LIMIT: int = 12_000

# ---------------------------------------------------------------------------
# Expected sections in every per-file document
# ---------------------------------------------------------------------------

FILE_DOC_EXPECTED_SECTIONS: list[str] = [
    "## Overview",
    "## Change Summary",
    "## Key Components",
]


# ---------------------------------------------------------------------------
# Per-document validation result
# ---------------------------------------------------------------------------

@dataclass
class DocumentValidationResult:
    """Result of validating a single document."""

    document_type: str
    completeness_score: float = 0.0
    accuracy_score: float = 0.0
    formatting_score: float = 0.0
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    # style_warnings is a SEPARATE counter from warnings.
    # warnings = lint issues (fence balance, empty headings) → feeds formatting_score.
    # style_warnings = prose style issues (avg sentence length) → feeds readability.
    # Keeping them distinct ensures a fence error does not penalise two score axes.
    style_warnings: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    hallucinations: list[str] = field(default_factory=list)
    summary: str = ""


# ---------------------------------------------------------------------------
# Validation Agent
# ---------------------------------------------------------------------------

class ValidationAgent:
    """
    Evaluates every generated document and produces a quality report.

    Args:
        llm_client: Object implementing generate(prompt: str) -> str.
                    Pass None to use rule-based validation only (no LLM scoring).
    """

    def __init__(self, llm_client=None) -> None:
        self._llm = llm_client
        self._slicer = ContextSlicer()

    def run(self, shared_memory: SharedMemory) -> AgentResult:
        """
        Validate all per-file documents in SharedMemory and write the report.

        Reads:  shared_memory.documentation.file_docs
        Writes: shared_memory.validation

        Args:
            shared_memory: The shared memory object.

        Returns:
            AgentResult: Success result (agent itself succeeds even if docs fail).
        """
        start = time.monotonic()
        repo_name = shared_memory.repository.full_name or shared_memory.repository.name
        logger.info("Validation started: %s", repo_name)

        docs = shared_memory.documentation.all_documents()
        if not docs:
            report = ValidationReport(
                validation_status="FAILED",
                quality_score=0.0,
                errors=["No documents were generated in shared memory"],
                timestamp=_now(),
            )
            shared_memory.validation = report
            return AgentResult(
                success=True,
                message="Validation completed: FAILED (no documents in shared memory)",
                errors=["No documents found in shared memory"],
            )

        # 1 — Rule-based structural validation (no LLM needed)
        doc_results: list[DocumentValidationResult] = []
        for file_path, content in docs.items():
            result = self._validate_structure(file_path, content)
            doc_results.append(result)
            logger.info(
                "File doc validation completed: %s  formatting=%.0f",
                file_path, result.formatting_score,
            )

        # 2 — LLM-based content validation (if LLM is available)
        if self._llm:
            self._validate_content_with_llm(shared_memory, doc_results)
            logger.info("LLM content validation completed")

        # 2.5 — Cross-document consistency check (if LLM is available)
        consistency_issues = self._validate_cross_document_consistency(shared_memory)
        if consistency_issues:
            logger.info(
                "Cross-document consistency check found %d issue(s)",
                len(consistency_issues),
            )

        # 2.6 — Faithfulness / groundedness score, across all LLM-authored docs
        # (if LLM is available)
        faithfulness_score, faithfulness_notes, faithfulness_checked = (
            self._compute_faithfulness_score(shared_memory)
        )

        # 3 — Compute overall score
        overall_score = self._compute_overall_score(
            doc_results, consistency_issues, faithfulness_score, faithfulness_checked,
        )

        # 4 — Determine status
        if overall_score >= WARN_THRESHOLD:
            status = "PASSED"
        elif overall_score >= PASS_THRESHOLD:
            status = "PASSED_WITH_WARNINGS"
        else:
            status = "FAILED"

        # 4.5 — Faithfulness floor: a document whose claims are largely
        # unsupported must not pass on structural quality alone, otherwise
        # hallucinations never reach the Revision Agent (see FAITHFULNESS_FLOOR).
        if faithfulness_checked and faithfulness_score < FAITHFULNESS_FLOOR:
            status = "FAILED"

        # 5 — Aggregate results
        # Consistency findings are prefixed and folded into `errors` (not
        # kept separate) so RevisionAgent._group_issues — which attributes
        # an issue to a document by checking whether that document's key
        # (e.g. "README.md") appears as a substring of the issue string —
        # automatically routes each contradiction to both documents it
        # names, without any RevisionAgent changes.
        consistency_errors = [f"Consistency: {c}" for c in consistency_issues]
        all_errors = [e for r in doc_results for e in r.errors] + consistency_errors
        all_warnings = [w for r in doc_results for w in r.warnings]
        all_missing = [m for r in doc_results for m in r.missing_sections]
        all_hallucinations = [h for r in doc_results for h in r.hallucinations]

        per_doc_scores = {
            r.document_type: round(
                (r.completeness_score + r.accuracy_score + r.formatting_score) / 3, 1
            )
            for r in doc_results
        }

        report = ValidationReport(
            validation_status=status,
            quality_score=overall_score,
            faithfulness_score=faithfulness_score,
            faithfulness_notes=faithfulness_notes,
            errors=all_errors,
            warnings=all_warnings,
            missing_sections=all_missing,
            hallucination_findings=all_hallucinations,
            consistency_issues=consistency_issues,
            per_document_scores=per_doc_scores,
            timestamp=_now(),
        )
        shared_memory.validation = report

        duration = time.monotonic() - start
        logger.info(
            "Validation report generated: status=%s  score=%.1f  duration=%.2fs",
            status, overall_score, duration,
        )
        logger.info("Validation completed: %s", repo_name)

        return AgentResult(
            success=True,
            message=f"Validation completed: {status}  score={overall_score:.1f}",
            execution_time=duration,
            warnings=all_warnings,
            errors=all_errors,
        )

    # ------------------------------------------------------------------
    # Rule-based structural validation (no LLM)
    # ------------------------------------------------------------------

    def _validate_structure(self, file_path: str, content: str) -> DocumentValidationResult:
        """Validate a per-file document's structure without using an LLM.

        Checks:
        - Content is not empty.
        - Expected sections are present (Overview, Change Summary, Key Components).
        - Code fences are balanced.
        - No empty headings.

        Args:
            file_path: Relative file path used as the document identifier.
            content:   Markdown content string.

        Returns:
            DocumentValidationResult: Structural validation result.
        """
        result = DocumentValidationResult(document_type=file_path)
        errors: list[str] = []
        warnings: list[str] = []
        missing: list[str] = []

        # Empty content check
        if not content or not content.strip():
            errors.append(f"{file_path}: Document is empty")
            result.errors = errors
            result.formatting_score = 0.0
            result.completeness_score = 0.0
            result.accuracy_score = 0.0
            return result

        # Expected sections
        is_file_doc = file_path.startswith("files/") or "/" in file_path
        if is_file_doc:
            expected = FILE_DOC_EXPECTED_SECTIONS
        else:
            expected = ["## Overview"]

        for section in expected:
            if section.lower() not in content.lower():
                # If ## Overview missing but has any ## section, don't penalize top-level docs
                if not is_file_doc and "## " in content:
                    continue
                missing.append(f"{file_path}: Missing section '{section}'")

        # Balanced code fences
        fence_count = len(re.findall(r"^```", content, re.MULTILINE))
        if fence_count % 2 != 0:
            warnings.append(f"{file_path}: Unbalanced code fences (count={fence_count})")

        # Empty headings
        empty_headings = re.findall(r"^#{1,6}\s*$", content, re.MULTILINE)
        if empty_headings:
            warnings.append(f"{file_path}: {len(empty_headings)} empty heading(s) found")

        # Formatting score: derived from lint warnings ONLY (fence balance, empty headings)
        deductions = len(warnings) * 5 + len(errors) * 15
        formatting_score = max(0.0, 100.0 - deductions)

        # Completeness score based on missing sections
        total_expected = len(expected)
        completeness_score = max(
            0.0, 100.0 - (len(missing) / total_expected) * 100
        ) if total_expected else 100.0

        # Readability check: sentence length (separate counter from lint warnings).
        # This populates style_warnings, NOT warnings, so it does not affect
        # formatting_score. A prose issue and a fence issue are independent signals.
        style_warnings: list[str] = []
        sentences = [s.strip() for s in re.split(r'[.!?]', content) if s.strip()]
        if sentences:
            avg_words = sum(len(s.split()) for s in sentences) / len(sentences)
            if avg_words > 40:
                style_warnings.append(
                    f"{file_path}: Avg sentence length {avg_words:.0f} words (>40 word threshold)"
                )

        result.formatting_score = formatting_score
        result.completeness_score = completeness_score
        result.accuracy_score = 80.0   # Default — updated by LLM validation if available
        result.errors = errors
        result.warnings = warnings
        result.style_warnings = style_warnings
        result.missing_sections = missing
        return result

    # ------------------------------------------------------------------
    # LLM-based content validation
    # ------------------------------------------------------------------

    def _validate_content_with_llm(
        self,
        shared_memory: SharedMemory,
        doc_results: list[DocumentValidationResult],
    ) -> None:
        """Use the LLM to validate content accuracy and detect hallucinations.

        Updates doc_results in-place.

        Args:
            shared_memory: Full shared memory.
            doc_results:   List of structural results to update.
        """
        llm = self._llm
        if llm is None:
            # Callers only invoke this when self._llm is truthy (see run()),
            # but guard locally too so this method is safe standalone.
            return

        meta = shared_memory.metadata
        und = shared_memory.understanding
        repo = shared_memory.repository
        docs = shared_memory.documentation.file_docs

        modules_str = ", ".join(m.name for m in und.modules) or "Unknown"
        apis_str = ", ".join(f"{e.method} {e.route}" for e in und.apis) or "None"
        folders_str = ", ".join(und.folder_responsibilities.keys()) or "Unknown"

        for result in doc_results:
            content = docs.get(result.document_type, "")
            if not content:
                continue

            # Truncate large documents to keep prompt manageable
            excerpt = content[:3000]

            prompt = DOCUMENT_VALIDATION_PROMPT.format(
                document_type=result.document_type,
                repository_name=repo.full_name,
                languages=", ".join(ls.language for ls in meta.languages) or "Unknown",
                frameworks=", ".join(meta.frameworks) or "Unknown",
                architecture_type=und.architecture_type,
                modules=modules_str,
                apis=apis_str,
                folders=folders_str,
                document_content=excerpt,
            )

            try:
                raw = llm.generate(prompt)
                self._parse_llm_validation(raw, result)
            except Exception as exc:
                logger.warning(
                    "LLM validation failed for %s: %s", result.document_type, exc
                )

    def _parse_llm_validation(
        self, raw: str, result: DocumentValidationResult
    ) -> None:
        """Parse the LLM validation response and update the result in-place.

        Args:
            raw:    Raw LLM response text.
            result: DocumentValidationResult to update.
        """
        def _extract_score(label: str) -> float:
            match = re.search(rf"{label}:\s*(\d+)", raw)
            return float(match.group(1)) if match else result.accuracy_score

        def _extract_list(label: str) -> list[str]:
            match = re.search(rf"{label}:\n(.*?)(?=\n[A-Z_]+:|$)", raw, re.DOTALL)
            if not match:
                return []
            block = match.group(1).strip()
            if block.upper() == "NONE":
                return []
            return [line.strip("- ").strip() for line in block.splitlines() if line.strip()]

        result.accuracy_score = _extract_score("ACCURACY_SCORE")

        llm_errors = _extract_list("ERRORS")
        llm_warnings = _extract_list("WARNINGS")
        llm_missing = _extract_list("MISSING_SECTIONS")
        llm_hallucinations = _extract_list("HALLUCINATIONS")

        result.errors.extend(llm_errors)
        result.warnings.extend(llm_warnings)
        result.missing_sections.extend(llm_missing)
        result.hallucinations.extend(llm_hallucinations)

        summary_match = re.search(r"SUMMARY:\n(.*?)$", raw, re.DOTALL)
        if summary_match:
            result.summary = summary_match.group(1).strip()

    # ------------------------------------------------------------------
    # Cross-document consistency check
    # ------------------------------------------------------------------

    def _validate_cross_document_consistency(
        self, shared_memory: SharedMemory
    ) -> list[str]:
        """Use the LLM to check README/Architecture/API docs for contradictions.

        Only runs when both README.md and ARCHITECTURE.md were generated —
        checking a document against itself, or against a document that
        doesn't exist, can't surface a real contradiction.

        Args:
            shared_memory: Full shared memory.

        Returns:
            list[str]: Human-readable contradiction descriptions, formatted
            as "<doc_a> vs <doc_b>: <description>".
        """
        llm = self._llm
        if llm is None:
            return []

        docs = shared_memory.documentation.file_docs
        readme = docs.get("README.md", "")
        architecture = docs.get("ARCHITECTURE.md", "")
        if not readme.strip() or not architecture.strip():
            return []

        und = shared_memory.understanding
        apis_str = ", ".join(f"{e.method} {e.route}" for e in und.apis) or "None"
        repo = shared_memory.repository

        prompt = CONSISTENCY_VALIDATION_PROMPT.format(
            repository_name=repo.full_name or repo.name,
            readme_excerpt=readme[:2500],
            architecture_excerpt=architecture[:2500],
            api_excerpt=apis_str,
        )

        try:
            raw = llm.generate(prompt)
        except Exception as exc:
            logger.warning("Cross-document consistency check failed: %s", exc)
            return []

        return self._parse_consistency_findings(raw)

    @staticmethod
    def _parse_consistency_findings(raw: str) -> list[str]:
        """Parse the CONSISTENCY_VALIDATION_PROMPT response.

        Format: CONTRADICTION | DOCUMENT_A | DOCUMENT_B | DESCRIPTION

        Args:
            raw: Raw LLM response text.

        Returns:
            list[str]: "<doc_a> vs <doc_b>: <description>" per contradiction.
        """
        if "NO_CONTRADICTIONS" in raw:
            return []

        findings: list[str] = []
        for line in raw.splitlines():
            line = line.strip()
            if not line or line.startswith("#") or line.startswith("```"):
                continue
            if re.match(r"^\|?[\s\-:|]+\|?$", line):
                continue
            parts = [p.strip() for p in line.split("|") if p.strip()]
            if not parts or parts[0].upper() != "CONTRADICTION":
                continue
            if len(parts) < 4:
                continue
            # Skip an echoed header row: the sentinel word "CONTRADICTION"
            # doubles as the literal header cell in this prompt's format
            # spec, so a real row is distinguished by DOCUMENT_A/DOCUMENT_B
            # not being the literal placeholder names.
            if parts[1].upper() == "DOCUMENT_A" and parts[2].upper() == "DOCUMENT_B":
                continue
            findings.append(f"{parts[1]} vs {parts[2]}: {parts[3]}")
        return findings

    # ------------------------------------------------------------------
    # Faithfulness / groundedness check
    # ------------------------------------------------------------------

    def _compute_faithfulness_score(self, shared_memory: SharedMemory) -> tuple[float, str, bool]:
        """LLM-judge how well each generated document's claims are grounded in
        the RAG context they were generated from (hallucination-risk signal,
        in the same spirit as RAGAS's faithfulness metric).

        Checks every document in FAITHFULNESS_CHECKED_DOCS that has content;
        REPORTS.md is excluded because it's rendered deterministically from
        static-analysis data, not LLM-authored, so it can't hallucinate.

        Runs only when both an LLM and RAG context are available — with no
        context to check claims against, any score would be meaningless.

        Returns:
            tuple[float, str, bool]: (mean score 0-100 across checked docs,
            combined notes on unsupported claims, whether any doc was
            actually checked). (0.0, "", False) when nothing could be checked.
        """
        llm = self._llm
        if llm is None:
            return 0.0, "", False

        ctx_pkg = getattr(shared_memory, "rag_context_package", None)
        rag_context = self._slicer.get_global_context(ctx_pkg)
        if not rag_context.strip():
            return 0.0, "", False

        repo = shared_memory.repository
        repo_name = repo.full_name or repo.name

        scores: list[float] = []
        notes_parts: list[str] = []
        for doc_key in FAITHFULNESS_CHECKED_DOCS:
            content = shared_memory.documentation.file_docs.get(doc_key, "")
            if not content.strip():
                continue
            result = self._score_document_faithfulness(
                llm, repo_name, rag_context, doc_key, content,
            )
            if result is None:
                # LLM call failed for this doc — exclude it rather than
                # counting it as a 0, so a transient API error on one judge
                # call can't drag an otherwise-fine set of docs into the
                # FAITHFULNESS_FLOOR and force a false FAILED verdict.
                continue
            score, notes = result
            scores.append(score)
            if notes:
                notes_parts.append(f"[{doc_key}] {notes}")

        if not scores:
            return 0.0, "", False

        return round(sum(scores) / len(scores), 1), "\n".join(notes_parts), True

    def _score_document_faithfulness(
        self, llm, repo_name: str, rag_context: str, doc_key: str, content: str,
    ) -> tuple[float, str] | None:
        """Judge a single document's groundedness against rag_context.

        Args:
            llm:        LLM client to use (already confirmed non-None by the caller).
            repo_name:  Repository full name, for the prompt header.
            rag_context: Retrieved code context to check claims against.
            doc_key:    Document identifier, e.g. "README.md".
            content:    Full document content (truncated to
                        FAITHFULNESS_DOC_CHAR_LIMIT before sending to the LLM).

        Returns:
            tuple[float, str] | None: (score 0-100, notes on unsupported
            claims), or None if the LLM call itself failed (as opposed to a
            genuinely low score, which is a valid result).
        """
        prompt = FAITHFULNESS_VALIDATION_PROMPT.format(
            repository_name=repo_name,
            rag_context=rag_context,
            document_type=doc_key,
            document_content=content[:FAITHFULNESS_DOC_CHAR_LIMIT],
        )

        try:
            raw = llm.generate(prompt)
        except Exception as exc:
            logger.warning("Faithfulness check failed for %s: %s", doc_key, exc)
            return None

        return self._parse_faithfulness_result(raw)

    @staticmethod
    def _parse_faithfulness_result(raw: str) -> tuple[float, str]:
        """Parse the FAITHFULNESS_VALIDATION_PROMPT response."""
        score_match = re.search(r"FAITHFULNESS_SCORE:\s*(\d+(?:\.\d+)?)", raw)
        score = min(100.0, max(0.0, float(score_match.group(1)))) if score_match else 0.0

        claims_match = re.search(
            r"UNSUPPORTED_CLAIMS:\s*(.*)", raw, re.DOTALL
        )
        notes = ""
        if claims_match:
            claims_text = claims_match.group(1).strip()
            if claims_text and "NONE" not in claims_text.splitlines()[0].upper():
                notes = claims_text

        return score, notes

    # ------------------------------------------------------------------
    # Score computation
    # ------------------------------------------------------------------

    def _compute_overall_score(
        self,
        doc_results: list[DocumentValidationResult],
        consistency_issues: list[str] | None = None,
        faithfulness_score: float = 0.0,
        faithfulness_checked: bool = False,
    ) -> float:
        """Compute the weighted overall quality score.

        Args:
            doc_results:          Per-document validation results.
            consistency_issues:   Cross-document contradictions found by
                                   _validate_cross_document_consistency.
            faithfulness_score:   Groundedness score from
                                   _compute_faithfulness_score (0-100).
            faithfulness_checked: Whether the faithfulness check actually
                                   ran. When False, faithfulness_score is
                                   ignored entirely (same rationale as the
                                   WEIGHT_COVERAGE exclusion below — folding
                                   in an unmeasured 0.0 would deflate every
                                   score for reasons unrelated to quality).

        Returns:
            float: Score from 0 to 100, rounded to one decimal place.
        """
        if not doc_results:
            return 0.0

        consistency_issues = consistency_issues or []

        avg_completeness = sum(r.completeness_score for r in doc_results) / len(doc_results)
        avg_accuracy = sum(r.accuracy_score for r in doc_results) / len(doc_results)
        avg_formatting = sum(r.formatting_score for r in doc_results) / len(doc_results)

        # Readability: derived from style_warnings ONLY (sentence-length prose checks).
        # style_warnings is populated by _validate_structure() separately from
        # lint warnings, so a fence error does NOT also deflate readability.
        total_style_warnings = sum(len(r.style_warnings) for r in doc_results)
        readability = max(0.0, 100.0 - total_style_warnings * 5)

        # Consistency: cross-document contradictions ONLY.
        # Hallucinations are penalized exclusively in faithfulness_score
        # (_compute_faithfulness_score). Do NOT subtract hallucinations here —
        # that would double-count the same signal across two supposedly
        # independent metrics, making their correlation artificial.
        consistency = max(0.0, 100.0 - len(consistency_issues) * 15)

        # NOTE: WEIGHT_COVERAGE has no corresponding computed score, so it is
        # excluded here. Normalise by the sum of weights actually applied —
        # otherwise the weights below sum to 0.90 instead of 1.0 and every
        # score is deflated by 10 points regardless of document quality.
        # WEIGHT_FAITHFULNESS follows the same rule: only included when the
        # faithfulness check actually ran (see faithfulness_checked docstring).
        applied_weight_sum = (
            WEIGHT_COMPLETENESS + WEIGHT_ACCURACY + WEIGHT_CONSISTENCY
            + WEIGHT_MARKDOWN + WEIGHT_READABILITY
        )
        if faithfulness_checked:
            applied_weight_sum += WEIGHT_FAITHFULNESS

        score_sum = (
            avg_completeness * WEIGHT_COMPLETENESS
            + avg_accuracy * WEIGHT_ACCURACY
            + consistency * WEIGHT_CONSISTENCY
            + avg_formatting * WEIGHT_MARKDOWN
            + readability * WEIGHT_READABILITY
        )
        if faithfulness_checked:
            score_sum += faithfulness_score * WEIGHT_FAITHFULNESS

        score = score_sum / applied_weight_sum
        return round(min(score, 100.0), 1)


# ---------------------------------------------------------------------------
# Utility
# ---------------------------------------------------------------------------

def _now() -> str:
    """Return current UTC time as an ISO 8601 string."""
    from datetime import datetime
    return datetime.utcnow().strftime("%Y-%m-%dT%H:%M:%SZ")
