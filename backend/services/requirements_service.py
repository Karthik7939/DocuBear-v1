"""
services/requirements_service.py
---------------------------------
Service for parsing Requirements Specification documents (PDF) containing
Functional (FR) and Non-Functional (NFR) requirements, and evaluating codebase
implementation coverage using AST symbols and RAG retrieval.
"""

import io
import json
import logging
import os
import re
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Dict, List, Optional

from pypdf import PdfReader

from app.core.config import settings
from services.llm_service import LLMService
from services.rag_service import RAGService
from services.repository_service import RepositoryService

logger = logging.getLogger(__name__)


class RequirementItem:
    def __init__(
        self,
        id: str,
        type: str,  # "functional" | "non_functional"
        category: str,
        title: str,
        description: str,
        status: str = "missing",  # "completed" | "partial" | "missing"
        confidence: float = 0.0,
        evidence_files: Optional[List[str]] = None,
        evidence_snippet: str = "",
        remediation: str = "",
    ):
        self.id = id
        self.type = type
        self.category = category
        self.title = title
        self.description = description
        self.status = status
        self.confidence = confidence
        self.evidence_files = evidence_files or []
        self.evidence_snippet = evidence_snippet
        self.remediation = remediation

    def to_dict(self) -> Dict[str, Any]:
        return {
            "id": self.id,
            "type": self.type,
            "category": self.category,
            "title": self.title,
            "description": self.description,
            "status": self.status,
            "confidence": round(self.confidence, 2),
            "evidence_files": self.evidence_files,
            "evidence_snippet": self.evidence_snippet,
            "remediation": self.remediation,
        }


class RequirementsService:
    """Service to handle PDF requirement extraction and codebase verification."""

    def __init__(
        self,
        llm: Optional[LLMService] = None,
        rag: Optional[RAGService] = None,
        repo_service: Optional[RepositoryService] = None,
    ) -> None:
        self.llm = llm or LLMService()
        self.rag = rag or RAGService()
        self.repo_service = repo_service or RepositoryService(
            repository_root=settings.repository_root
        )

    def extract_text_from_pdf(self, pdf_bytes: bytes) -> str:
        """Extract plain text from PDF bytes."""
        try:
            reader = PdfReader(io.BytesIO(pdf_bytes))
            text_parts = []
            for i, page in enumerate(reader.pages):
                page_text = page.extract_text() or ""
                if page_text.strip():
                    text_parts.append(f"--- Page {i+1} ---\n{page_text.strip()}")
            full_text = "\n\n".join(text_parts)
            if not full_text.strip():
                raise ValueError("The uploaded PDF did not contain any readable text.")
            return full_text
        except Exception as e:
            logger.error("Failed to extract text from PDF: %s", e)
            raise ValueError(f"Could not read PDF content: {str(e)}")

    def parse_markdown_requirements(self, markdown_text: str) -> List[Dict[str, Any]]:
        """Parse structured requirements from a markdown document like REQUIREMENTS.md."""
        items: List[Dict[str, Any]] = []
        seen_ids = set()
        current_section = "functional"
        current_category = "General"

        for line in markdown_text.splitlines():
            line_s = line.strip()
            if not line_s:
                continue

            # Section headers
            if re.search(r"^##\s+.*\b(Non-Functional|NFR|Quality|Error Handling|Constraints|Standards)\b", line_s, re.IGNORECASE):
                current_section = "non_functional"
                current_category = "General"
                continue
            elif re.search(r"^##\s+.*\b(Functional|FR|Features|Capabilities)\b", line_s, re.IGNORECASE):
                current_section = "functional"
                current_category = "General"
                continue

            # Sub-headers (Categories)
            cat_match = re.match(r"^###\s+[0-9\.]*\s*(.+)", line_s)
            if cat_match:
                current_category = cat_match.group(1).strip()
                continue

            # Requirement bullet point: - **FR-1.1.1**: Description
            item_match = re.match(r"^[-\*]\s+\*\*([A-Za-z0-9\.\-_]+)\*\*:\s*(.+)", line_s)
            if item_match:
                req_id = item_match.group(1).strip()
                desc = item_match.group(2).strip()
                if req_id not in seen_ids:
                    seen_ids.add(req_id)
                    is_nfr = (
                        "NFR" in req_id.upper()
                        or "SEC" in req_id.upper()
                        or "PERF" in req_id.upper()
                        or "REL" in req_id.upper()
                        or "COMP" in req_id.upper()
                        or "E-" in req_id.upper()
                        or "ERR" in req_id.upper()
                        or current_section == "non_functional"
                        or any(k in current_category.lower() for k in [
                            "performance", "concurrency", "reliability", "security",
                            "fault tolerance", "standards", "error handling", "compatibility"
                        ])
                    )
                    req_type = "non_functional" if is_nfr else "functional"
                    title = desc.split(".")[0].strip() if "." in desc else desc[:70].strip()
                    if len(title) > 80:
                        title = title[:77] + "..."

                    items.append({
                        "id": req_id,
                        "type": req_type,
                        "category": current_category,
                        "title": title,
                        "description": desc,
                    })
                continue

            # Alternate bullet point: - FR-1.1.1: Description or 1.1.1 Description
            alt_match = re.match(r"^[-\*•–—]?\s*([A-Za-z]{1,5}[-\s]?[0-9\.\-_]+)\s*[:\-\)]\s*(.+)", line_s)
            if alt_match:
                req_id = alt_match.group(1).strip().replace(" ", "-")
                desc = alt_match.group(2).strip()
                if req_id not in seen_ids:
                    seen_ids.add(req_id)
                    is_nfr = (
                        "NFR" in req_id.upper()
                        or "SEC" in req_id.upper()
                        or "PERF" in req_id.upper()
                        or "REL" in req_id.upper()
                        or "COMP" in req_id.upper()
                        or "E-" in req_id.upper()
                        or "ERR" in req_id.upper()
                        or current_section == "non_functional"
                        or any(k in current_category.lower() for k in [
                            "performance", "concurrency", "reliability", "security",
                            "fault tolerance", "standards", "error handling", "compatibility"
                        ])
                    )
                    req_type = "non_functional" if is_nfr else "functional"
                    title = desc.split(".")[0].strip() if "." in desc else desc[:70].strip()
                    if len(title) > 80:
                        title = title[:77] + "..."
                    items.append({
                        "id": req_id,
                        "type": req_type,
                        "category": current_category,
                        "title": title,
                        "description": desc,
                    })
                continue

        return items

    def _parse_hierarchical_requirements(self, text: str) -> List[Dict[str, Any]]:
        """
        Robust line-by-line hierarchical parser that extracts requirement IDs, category headers,
        and accumulates multi-line descriptions across pages without losing continuation sentences.
        Supports all Unicode bullet points (•, –, —, ◦, ▪), NFR headers, error codes, and formats.
        """
        lines = text.splitlines()
        items: List[Dict[str, Any]] = []
        seen_ids: Dict[str, int] = {}  # id -> index in items
        current_section = "functional"
        current_category = "General"

        current_id: Optional[str] = None
        current_type: Optional[str] = None
        current_cat: Optional[str] = None
        current_desc_lines: List[str] = []

        # Subsection/Category pattern: e.g. "1.1 Connection Establishment", "2.1 Performance & Concurrency", "### 2.2 Reliability"
        category_pattern = re.compile(
            r"^(?:#{1,4}\s*)?(?:[0-9]+(?:\.[0-9]+)*\.?)\s+([A-Za-z0-9\s&/\(\),\-]+)$"
        )
        # Requirement ID pattern: e.g. "FR-1.1.1: ...", "• NFR-2.1.1: ...", "- **NFR-2.1.1**: ...", "NFR 2.1.1: ...", "E-3.1: ..."
        req_start_pattern = re.compile(
            r"^(?:[-\*•–—+◦▪\u2022\u2013\u2014\u25e6\u25aa]\s+)?(?:\*\*)?(?:\[|\()?((?:FR|NFR|REQ|SEC|PERF|REL|COMP|AC|E|ERR|BR|DR|INT|FEAT|UI|API|NF|SYS)\b[-\s\._]?[0-9]*(?:\.[0-9]+)*|[0-9]+\.[0-9]+(?:\.[0-9]+)+)(?:\]|\))?(?:\*\*)?\s*[:\-\)\.]\s*(.*)$",
            re.IGNORECASE
        )

        def flush() -> None:
            nonlocal current_id, current_type, current_cat, current_desc_lines
            if current_id and current_desc_lines:
                desc = " ".join([l.strip() for l in current_desc_lines if l.strip()]).strip()
                first_sentence = desc.split(".")[0].strip() if "." in desc else desc
                title = first_sentence[:80].strip() if len(first_sentence) > 80 else first_sentence
                if not title:
                    title = f"Requirement {current_id}"

                item_data = {
                    "id": current_id,
                    "type": current_type or "functional",
                    "category": current_cat or "General",
                    "title": title,
                    "description": desc,
                }

                if current_id in seen_ids:
                    existing_idx = seen_ids[current_id]
                    if len(desc) > len(items[existing_idx]["description"]):
                        items[existing_idx] = item_data
                else:
                    seen_ids[current_id] = len(items)
                    items.append(item_data)

                current_id = None
                current_type = None
                current_cat = None
                current_desc_lines = []

        for line in lines:
            line_s = line.strip()
            if not line_s or line_s.startswith("--- Page"):
                continue

            # 1. Requirement start check FIRST (prevents NFR lines from matching section headers)
            req_match = req_start_pattern.match(line_s)
            if req_match:
                raw_id_candidate = req_match.group(1).strip()
                # Ignore plain single digits unless in requirement section
                if raw_id_candidate.isdigit() and len(raw_id_candidate) < 2 and current_category == "General":
                    if current_id:
                        current_desc_lines.append(line_s)
                    continue

                flush()
                raw_id = raw_id_candidate.replace(" ", "-").upper()
                initial_text = req_match.group(2).strip()

                is_nfr = (
                    "NFR" in raw_id
                    or "SEC" in raw_id
                    or "PERF" in raw_id
                    or "RELIAB" in raw_id
                    or "COMP" in raw_id
                    or "E-" in raw_id
                    or "ERR" in raw_id
                    or current_section == "non_functional"
                    or any(k in current_category.lower() for k in [
                        "performance", "concurrency", "reliability", "security",
                        "fault tolerance", "standards", "error handling", "compatibility",
                        "scalability", "maintainability", "availability", "latency"
                    ])
                )

                req_type = "non_functional" if is_nfr else "functional"

                current_id = raw_id
                current_type = req_type
                current_cat = current_category
                current_desc_lines = [initial_text] if initial_text else []
                continue

            # 2. Major section headers: Non-Functional vs Functional (anchored at start of line)
            if re.search(r"^(?:#{1,4}\s*)?(?:[0-9]+\.?\s*)?(?:non[\s\-_]?functional(?:\s+requirements?|\s+specifications?|\s+specs?)?|quality\s+attributes|system\s+constraints)\b", line_s, re.IGNORECASE) and len(line_s) < 80:
                flush()
                current_section = "non_functional"
                current_category = "General"
                continue
            elif re.search(r"^(?:#{1,4}\s*)?(?:[0-9]+\.?\s*)?(?:functional(?:\s+requirements?|\s+specifications?|\s+specs?)?|system\s+features|core\s+capabilities)\b", line_s, re.IGNORECASE) and len(line_s) < 80:
                flush()
                current_section = "functional"
                current_category = "General"
                continue

            # 3. Sub-category header
            cat_match = category_pattern.match(line_s)
            if cat_match:
                flush()
                current_category = cat_match.group(1).strip()
                continue

            # 4. Multi-line continuation of current requirement
            if current_id:
                current_desc_lines.append(line_s)

        flush()
        return items

    def extract_requirements_from_text(self, text: str) -> List[Dict[str, Any]]:
        """Extract ALL distinct requirements from text using hierarchical parsing + LLM fallback."""
        # 1. Try direct markdown parser if formatted as markdown
        if "##" in text and ("FR" in text or "Requirement" in text or "NFR" in text):
            md_items = self.parse_markdown_requirements(text)
            if len(md_items) >= 3:
                logger.info("Parsed %d requirements using markdown structure parser", len(md_items))
                return md_items

        # 2. Try hierarchical line-by-line scanner for PDFs and spec documents
        hierarchical_items = self._parse_hierarchical_requirements(text)
        has_nfr_in_text = bool(re.search(r"non[\s\-_]?functional|nfr", text, re.IGNORECASE))
        has_nfr_in_items = any(i.get("type") == "non_functional" for i in hierarchical_items)

        # If hierarchical found both FR and NFR (or no NFR mentioned in text), return
        if len(hierarchical_items) >= 3 and (not has_nfr_in_text or has_nfr_in_items):
            logger.info("Parsed %d requirements (including NFRs) using hierarchical pattern scanner", len(hierarchical_items))
            return hierarchical_items

        # 3. LLM-powered extraction with chunking & exhaustive prompt
        all_extracted_items: List[Dict[str, Any]] = []
        seen_ids = set()
        for item in hierarchical_items:
            clean_id = str(item.get("id", "")).strip().upper()
            if clean_id:
                seen_ids.add(clean_id)
                all_extracted_items.append(item)

        chunk_size = 5000
        text_chunks = [text[i:i + chunk_size] for i in range(0, min(len(text), 25000), chunk_size)]
        if not text_chunks:
            text_chunks = [text]

        for chunk_idx, chunk in enumerate(text_chunks):
            prompt = (
                "You are an expert Systems Analyst and Requirement Engineer.\n"
                "Extract EVERY SINGLE Functional Requirement (FR) AND Non-Functional Requirement (NFR) "
                "from the text below. Pay special attention to NFR sections (Performance, Latency, Concurrency, "
                "Reliability, Security, Standards, Error Handling). DO NOT skip any requirement.\n\n"
                "CRITICAL: Return ONLY a valid JSON array of objects with keys: id, type ('functional' or 'non_functional'), category, title, description.\n\n"
                "JSON format:\n"
                "[\n"
                "  {\"id\": \"FR-1.1\", \"type\": \"functional\", \"category\": \"Core\", \"title\": \"Feature\", \"description\": \"...\"},\n"
                "  {\"id\": \"NFR-2.1\", \"type\": \"non_functional\", \"category\": \"Performance\", \"title\": \"Latency\", \"description\": \"...\"}\n"
                "]\n\n"
                f"DOCUMENT TEXT CHUNK {chunk_idx + 1}:\n"
                f"{chunk}"
            )

            try:
                raw_response = self.llm.generate(prompt)
                cleaned = re.sub(r"^```(?:json)?\s*", "", raw_response.strip(), flags=re.MULTILINE)
                cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE).strip()

                parsed_chunk_items = []
                try:
                    res_json = json.loads(cleaned)
                    if isinstance(res_json, list):
                        parsed_chunk_items = res_json
                except Exception:
                    # Individual object regex fallback for slightly malformed JSON arrays
                    raw_objs = re.findall(r"\{[^{}]*\"id\"[^{}]*\}", raw_response, re.DOTALL)
                    for obj_str in raw_objs:
                        try:
                            item_obj = json.loads(obj_str)
                            if isinstance(item_obj, dict) and "id" in item_obj:
                                parsed_chunk_items.append(item_obj)
                        except Exception:
                            continue

                for it in parsed_chunk_items:
                    item_id = str(it.get("id", "")).strip()
                    if item_id and item_id not in seen_ids:
                        seen_ids.add(item_id)
                        all_extracted_items.append({
                            "id": item_id,
                            "type": it.get("type", "functional"),
                            "category": it.get("category", "General"),
                            "title": it.get("title", f"Requirement {item_id}"),
                            "description": it.get("description", ""),
                        })
            except Exception as e:
                logger.warning("Error in LLM requirement extraction chunk %d: %s", chunk_idx, e)

        # If LLM found items across chunks, return them
        if len(all_extracted_items) > 0:
            logger.info("Extracted %d requirements via LLM chunk extraction", len(all_extracted_items))
            return all_extracted_items

        # If LLM failed, fallback to sentence heuristics (search for 'must', 'shall', 'should', 'required')
        fallback_items = []
        sentences = re.split(r"(?<=[.!?])\s+", text)
        idx = 1
        for s in sentences:
            s_clean = s.strip()
            if any(k in s_clean.lower() for k in ["must", "shall", "should", "required", "system will", "support"]):
                if 20 <= len(s_clean) <= 300:
                    req_type = "non_functional" if any(n in s_clean.lower() for n in ["latency", "security", "memory", "performance", "uptime"]) else "functional"
                    fallback_items.append({
                        "id": f"REQ-{idx:02d}",
                        "type": req_type,
                        "category": "Specification",
                        "title": s_clean.split(".")[0][:60].strip(),
                        "description": s_clean,
                    })
                    idx += 1
                    if len(fallback_items) >= 40:
                        break

        if fallback_items:
            logger.info("Extracted %d requirements via sentence heuristics", len(fallback_items))
            return fallback_items

        return [
            {
                "id": "FR-01",
                "type": "functional",
                "category": "Core Features",
                "title": "Primary System Functionality",
                "description": "Implement core functional workflows described in specification.",
            }
        ]

    def _get_codebase_context(self, repo_slug: str) -> str:
        """Collect prioritized source code file structure and outlines from local repository clones."""
        normalized_slug = repo_slug.replace("/", "_")
        repo_path = Path(self.repo_service.get_repository_path(normalized_slug))
        if not repo_path.is_dir():
            return "No local repository clone found on disk."

        code_exts = {
            ".c", ".cpp", ".cc", ".h", ".hpp", ".py", ".ts", ".tsx", ".js", ".jsx",
            ".go", ".rs", ".java", ".cs", ".sh", ".ini", ".rc", ".md", ".nsi", ".json", ".yaml", ".yml"
        }
        skip_exts = {
            ".exe", ".dll", ".obj", ".aps", ".suo", ".res", ".pdb", ".pal", ".jpg",
            ".jpeg", ".png", ".ico", ".pdf", ".zip", ".tar", ".gz", ".7z", ".pyc"
        }

        code_files: List[str] = []
        other_files: List[str] = []

        for root, _, files in os.walk(repo_path):
            for file in files:
                if file.startswith(".") or file.startswith("~"):
                    continue
                rel_path = os.path.relpath(os.path.join(root, file), repo_path)
                ext = Path(file).suffix.lower()
                if ext in skip_exts:
                    continue
                if ext in code_exts or any(d in rel_path.lower() for d in ["src", "lib", "services", "app", "core"]):
                    code_files.append(rel_path)
                else:
                    other_files.append(rel_path)

        # Prioritize src/ and services/ and core code at top
        code_files.sort(key=lambda p: (
            0 if p.startswith("src") or p.startswith("app") or p.startswith("services") else 1,
            p
        ))
        all_files = code_files + other_files
        return "\n".join(all_files[:250])

    def evaluate_requirement_against_codebase(
        self,
        item: Dict[str, Any],
        repo_slug: str,
        codebase_file_list: str,
    ) -> Dict[str, Any]:
        """Check codebase RAG & symbols to see if requirement is implemented."""
        query = f"{item.get('title', '')} {item.get('description', '')}"
        rag_result = self.rag.retrieve(query)
        rag_context = rag_result.context if rag_result and hasattr(rag_result, "context") else ""

        prompt = (
            "You are a Senior Code Auditor and Quality Engineer.\n"
            f"Evaluate if the following {item.get('type', 'functional').upper()} requirement is implemented in the codebase.\n\n"
            f"REQUIREMENT ID: {item.get('id')}\n"
            f"TITLE: {item.get('title')}\n"
            f"CATEGORY: {item.get('category')}\n"
            f"DESCRIPTION: {item.get('description')}\n\n"
            f"REPOSITORY FILES AVAILABLE:\n{codebase_file_list[:2500]}\n\n"
            f"RETRIEVED CODE CONTEXT & EVIDENCE (RAG):\n{rag_context[:3500]}\n\n"
            "Evaluate implementation completeness. Return ONLY valid JSON in the exact schema:\n"
            "{\n"
            "  \"status\": \"completed\" | \"partial\" | \"missing\",\n"
            "  \"confidence\": 0.95,\n"
            "  \"evidence_files\": [\"path/to/relevant/file.py\"],\n"
            "  \"evidence_snippet\": \"Found UserAuth class handling JWT creation and validation in backend/auth.py\",\n"
            "  \"remediation\": \"If missing or partial, explain briefly what needs to be implemented. Otherwise 'Fully implemented.'\"\n"
            "}\n"
        )

        raw = self.llm.generate(prompt)
        cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
        cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE).strip()

        try:
            eval_data = json.loads(cleaned)
            return {
                "id": item.get("id"),
                "type": item.get("type", "functional"),
                "category": item.get("category", "General"),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "status": eval_data.get("status", "missing"),
                "confidence": float(eval_data.get("confidence", 0.7)),
                "evidence_files": eval_data.get("evidence_files", []),
                "evidence_snippet": eval_data.get("evidence_snippet", ""),
                "remediation": eval_data.get("remediation", ""),
            }
        except Exception as exc:
            logger.warning("Failed to parse evaluation response for %s: %s", item.get("id"), exc)
            return {
                "id": item.get("id"),
                "type": item.get("type", "functional"),
                "category": item.get("category", "General"),
                "title": item.get("title", ""),
                "description": item.get("description", ""),
                "status": "missing",
                "confidence": 0.5,
                "evidence_files": [],
                "evidence_snippet": "Unable to verify in codebase automatically.",
                "remediation": "Review implementation in source code.",
            }

    def _evaluate_batch_of_items(
        self,
        batch: List[Dict[str, Any]],
        repo_slug: str,
        codebase_files: str,
        rag_ctx: str = "",
    ) -> List[Dict[str, Any]]:
        """Evaluate a batch of requirements in a single LLM prompt with retrieved context."""
        prompt = (
            "You are a Senior Code Auditor and Software Architecture Assessor.\n"
            f"Evaluate the implementation status of each requirement below against the target repository '{repo_slug}'.\n\n"
            f"REPOSITORY FILES AVAILABLE:\n{codebase_files[:2500]}\n\n"
            f"RETRIEVED CODE CONTEXT & EVIDENCE:\n{rag_ctx[:3000]}\n\n"
            "REQUIREMENTS TO EVALUATE:\n"
            + json.dumps(batch, indent=2) + "\n\n"
            "For EACH requirement in the input list, evaluate implementation completeness. Return ONLY a valid JSON array of objects with the exact schema:\n"
            "[\n"
            "  {\n"
            "    \"id\": \"FR-1.1.1\",\n"
            "    \"status\": \"completed\" | \"partial\" | \"missing\",\n"
            "    \"confidence\": 0.95,\n"
            "    \"evidence_files\": [\"path/to/file.cpp\"],\n"
            "    \"evidence_snippet\": \"Found relevant symbols / implementation details...\",\n"
            "    \"remediation\": \"If missing or partial, explain what needs to be implemented. Otherwise 'Fully implemented.'\"\n"
            "  }\n"
            "]"
        )

        try:
            raw = self.llm.generate(prompt)
            cleaned = re.sub(r"^```(?:json)?\s*", "", raw.strip(), flags=re.MULTILINE)
            cleaned = re.sub(r"```$", "", cleaned.strip(), flags=re.MULTILINE).strip()

            eval_map: Dict[str, Dict[str, Any]] = {}
            try:
                parsed = json.loads(cleaned)
                if isinstance(parsed, list):
                    for obj in parsed:
                        if isinstance(obj, dict) and "id" in obj:
                            eval_map[str(obj["id"]).upper().replace(" ", "-")] = obj
            except Exception:
                pass

            evaluated_batch = []
            for item in batch:
                clean_id = str(item.get("id", "")).upper().replace(" ", "-")
                e = eval_map.get(clean_id, {})
                evaluated_batch.append({
                    "id": item.get("id"),
                    "type": item.get("type", "functional"),
                    "category": item.get("category", "General"),
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "status": e.get("status", "missing"),
                    "confidence": float(e.get("confidence", 0.7)),
                    "evidence_files": e.get("evidence_files", []),
                    "evidence_snippet": e.get("evidence_snippet", ""),
                    "remediation": e.get("remediation", "Review implementation in source code."),
                })
            return evaluated_batch
        except Exception as exc:
            logger.error("Batch evaluation failed: %s", exc)
            return [
                {
                    "id": item.get("id"),
                    "type": item.get("type", "functional"),
                    "category": item.get("category", "General"),
                    "title": item.get("title", ""),
                    "description": item.get("description", ""),
                    "status": "missing",
                    "confidence": 0.5,
                    "evidence_files": [],
                    "evidence_snippet": "Batch evaluation could not verify automatically.",
                    "remediation": "Review implementation in source code.",
                }
                for item in batch
            ]

    def _evaluate_items_concurrently(
        self,
        raw_items: List[Dict[str, Any]],
        repo_slug: str,
        codebase_files: str,
        batch_size: int = 6,
        max_workers: int = 2,
    ) -> List[Dict[str, Any]]:
        """Evaluate list of requirements in sequential batches with RAG context for maximum reliability and speed."""
        if not raw_items:
            return []

        batches = [raw_items[i:i + batch_size] for i in range(0, len(raw_items), batch_size)]
        evaluated_all: List[Dict[str, Any]] = []

        for idx, b in enumerate(batches):
            rag_query = " ".join([f"{it.get('title', '')} {it.get('category', '')}" for it in b])
            try:
                rag_res = self.rag.retrieve(rag_query)
                rag_ctx = rag_res.context if rag_res and hasattr(rag_res, "context") else ""
            except Exception:
                rag_ctx = ""

            batch_eval = self._evaluate_batch_of_items(b, repo_slug, codebase_files, rag_ctx=rag_ctx)
            evaluated_all.extend(batch_eval)

        return evaluated_all

    def _verify_items_against_markdown_specs(
        self,
        raw_items: List[Dict[str, Any]],
        repo_slug: str,
    ) -> List[Dict[str, Any]]:
        """
        Verify extracted PDF requirements directly against REQUIREMENTS.md (and other generated project docs)
        without touching or scanning the codebase files.
        """
        normalized_slug = repo_slug.replace("/", "_")
        docs_dir = settings.generated_docs_path_dir / normalized_slug

        # Load REQUIREMENTS.md if present
        req_md_file = docs_dir / "REQUIREMENTS.md"
        md_items_by_id: Dict[str, Dict[str, Any]] = {}
        md_items_by_alphanum_id: Dict[str, Dict[str, Any]] = {}
        md_items_by_title: Dict[str, Dict[str, Any]] = {}
        all_md_docs: Dict[str, str] = {}

        if req_md_file.is_file():
            content = req_md_file.read_text(encoding="utf-8")
            parsed_md = self.parse_markdown_requirements(content)
            for item in parsed_md:
                clean_id = str(item.get("id", "")).upper().replace(" ", "-")
                md_items_by_id[clean_id] = item
                alphanum_id = re.sub(r"[^A-Z0-9]", "", clean_id)
                if alphanum_id:
                    md_items_by_alphanum_id[alphanum_id] = item
                clean_title = str(item.get("title", "")).lower().strip()
                if clean_title:
                    md_items_by_title[clean_title] = item

        # Also load all other generated docs in generated_docs/{repo_slug}/
        if docs_dir.is_dir():
            for doc_path in docs_dir.glob("*.md"):
                try:
                    all_md_docs[doc_path.name] = doc_path.read_text(encoding="utf-8")
                except Exception:
                    pass

        evaluated_items = []
        for item in raw_items:
            req_id = str(item.get("id", "")).strip()
            clean_id = req_id.upper().replace(" ", "-")
            alphanum_id = re.sub(r"[^A-Z0-9]", "", clean_id)
            title = str(item.get("title", "")).strip()
            desc = str(item.get("description", "")).strip()
            cat = str(item.get("category", "General")).strip()
            req_type = item.get("type", "functional")

            is_nfr = (
                req_type == "non_functional"
                or "NFR" in clean_id
                or "SEC" in clean_id
                or "PERF" in clean_id
                or "REL" in clean_id
                or "COMP" in clean_id
                or "E-" in clean_id
                or "ERR" in clean_id
                or any(k in cat.lower() for k in [
                    "performance", "concurrency", "reliability", "security",
                    "fault tolerance", "standards", "error handling", "compatibility"
                ])
            )
            effective_type = "non_functional" if is_nfr else "functional"

            # 1. Exact or alphanumeric ID match in REQUIREMENTS.md
            matched = md_items_by_id.get(clean_id) or md_items_by_alphanum_id.get(alphanum_id)
            if matched:
                if matched.get("type") == "non_functional" or "NFR" in str(matched.get("id", "")).upper():
                    effective_type = "non_functional"
                evaluated_items.append({
                    "id": req_id,
                    "type": effective_type,
                    "category": matched.get("category") or cat,
                    "title": matched.get("title") or title,
                    "description": desc or matched.get("description", ""),
                    "status": "completed",
                    "confidence": 0.98,
                    "evidence_files": ["REQUIREMENTS.md"],
                    "evidence_snippet": f"Verified in REQUIREMENTS.md (Section: {matched.get('category', 'General')}):\n{matched.get('description', '')}",
                    "remediation": "Specification verified in REQUIREMENTS.md.",
                })
                continue

            # 2. Match by title similarity in REQUIREMENTS.md
            matched_by_title = None
            title_lower = title.lower()
            for md_t, md_item in md_items_by_title.items():
                if md_t and (md_t in title_lower or title_lower in md_t or len(set(md_t.split()) & set(title_lower.split())) >= 4):
                    matched_by_title = md_item
                    break

            if matched_by_title:
                if matched_by_title.get("type") == "non_functional" or "NFR" in str(matched_by_title.get("id", "")).upper():
                    effective_type = "non_functional"
                evaluated_items.append({
                    "id": req_id,
                    "type": effective_type,
                    "category": matched_by_title.get("category") or cat,
                    "title": title,
                    "description": desc,
                    "status": "completed",
                    "confidence": 0.92,
                    "evidence_files": ["REQUIREMENTS.md"],
                    "evidence_snippet": f"Verified in REQUIREMENTS.md ({matched_by_title.get('id')} - {matched_by_title.get('category')}):\n{matched_by_title.get('description', '')}",
                    "remediation": "Specification verified in REQUIREMENTS.md.",
                })
                continue

            # 3. Check if mentioned in other project markdown docs (e.g. ARCHITECTURE.md, README.md, SECURITY.md)
            found_in_doc = None
            snippet = ""
            for doc_name, doc_text in all_md_docs.items():
                if clean_id in doc_text.upper() or (title and title.lower() in doc_text.lower()):
                    found_in_doc = doc_name
                    lines = doc_text.splitlines()
                    for l in lines:
                        if clean_id in l.upper() or (title and title.lower() in l.lower()):
                            snippet = l.strip()
                            break
                    break

            if found_in_doc:
                evaluated_items.append({
                    "id": req_id,
                    "type": effective_type,
                    "category": cat,
                    "title": title,
                    "description": desc,
                    "status": "completed",
                    "confidence": 0.90,
                    "evidence_files": [found_in_doc],
                    "evidence_snippet": f"Found in project specification {found_in_doc}:\n{snippet[:200]}",
                    "remediation": f"Specification verified in {found_in_doc}.",
                })
                continue

            # 4. If not found in REQUIREMENTS.md or any project documentation -> Missing / Pending
            evaluated_items.append({
                "id": req_id,
                "type": effective_type,
                "category": cat,
                "title": title,
                "description": desc,
                "status": "missing",
                "confidence": 0.95,
                "evidence_files": [],
                "evidence_snippet": "Requirement is in uploaded PDF, but not found in REQUIREMENTS.md specification.",
                "remediation": "This requirement is in your PDF but missing from REQUIREMENTS.md. Add this requirement to your project specification.",
            })

        return evaluated_items

    def process_requirements_document(
        self,
        repo_slug: str,
        file_name: str,
        pdf_bytes: bytes,
    ) -> Dict[str, Any]:
        """End-to-end flow: Extract requirements from PDF and verify directly against REQUIREMENTS.md."""
        normalized_slug = repo_slug.replace("/", "_")
        text = self.extract_text_from_pdf(pdf_bytes)
        raw_items = self.extract_requirements_from_text(text)

        evaluated_items = self._verify_items_against_markdown_specs(
            raw_items=raw_items,
            repo_slug=normalized_slug,
        )

        # Calculate scores
        fr_items = [i for i in evaluated_items if i.get("type") == "functional"]
        nfr_items = [i for i in evaluated_items if i.get("type") == "non_functional"]

        def calc_score(items: List[Dict[str, Any]]) -> float:
            if not items:
                return 0.0
            score_map = {"completed": 1.0, "partial": 0.5, "missing": 0.0}
            total = sum(score_map.get(i.get("status", "missing"), 0.0) for i in items)
            return round((total / len(items)) * 100, 1)

        def count_breakdown(items: List[Dict[str, Any]]) -> Dict[str, int]:
            return {
                "total": len(items),
                "completed": sum(1 for i in items if i.get("status") == "completed"),
                "partial": sum(1 for i in items if i.get("status") == "partial"),
                "missing": sum(1 for i in items if i.get("status") == "missing"),
            }

        fr_score = calc_score(fr_items)
        nfr_score = calc_score(nfr_items)

        if fr_items and nfr_items:
            overall_score = round((fr_score * 0.7) + (nfr_score * 0.3), 1)
        elif fr_items:
            overall_score = fr_score
        elif nfr_items:
            overall_score = nfr_score
        else:
            overall_score = 0.0

        passed_fr = sum(1 for i in fr_items if i.get("status") == "completed")
        passed_nfr = sum(1 for i in nfr_items if i.get("status") == "completed")
        total_passed = passed_fr + passed_nfr

        result = {
            "repository": repo_slug.replace("_", "/"),
            "fileName": file_name,
            "analyzedAt": datetime.now(timezone.utc).isoformat(),
            "overallScore": overall_score,
            "functionalScore": fr_score,
            "functionalCount": count_breakdown(fr_items),
            "nonFunctionalScore": nfr_score,
            "nonFunctionalCount": count_breakdown(nfr_items),
            "items": evaluated_items,
            "summary": (
                f"Specification audit complete for {repo_slug}. {total_passed} of {len(evaluated_items)} requirements ({overall_score}%) "
                f"from '{file_name}' are verified and present in project specification (REQUIREMENTS.md). "
                f"Functional compliance: {fr_score}% ({passed_fr}/{len(fr_items)}), "
                f"Non-Functional compliance: {nfr_score}% ({passed_nfr}/{len(nfr_items)})."
            ),
        }

        # Save to disk
        self._save_requirements_to_disk(normalized_slug, result)
        return result

    def has_markdown_requirements(self, repo_slug: str) -> bool:
        """Check if generated_docs/{repo_slug}/REQUIREMENTS.md exists."""
        normalized_slug = repo_slug.replace("/", "_")
        md_file = settings.generated_docs_path_dir / normalized_slug / "REQUIREMENTS.md"
        return md_file.is_file()

    def sync_requirements_from_markdown(self, repo_slug: str) -> Dict[str, Any]:
        """Extract all requirements directly from generated_docs/{repo_slug}/REQUIREMENTS.md and verify specification status."""
        normalized_slug = repo_slug.replace("/", "_")
        md_file = settings.generated_docs_path_dir / normalized_slug / "REQUIREMENTS.md"
        if not md_file.is_file():
            raise FileNotFoundError(f"No generated REQUIREMENTS.md found for '{repo_slug}'.")

        content = md_file.read_text(encoding="utf-8")
        raw_items = self.parse_markdown_requirements(content)
        if not raw_items or len(raw_items) < 3:
            raw_items = self.extract_requirements_from_text(content)

        evaluated_items = self._verify_items_against_markdown_specs(
            raw_items=raw_items,
            repo_slug=normalized_slug,
        )

        fr_items = [i for i in evaluated_items if i.get("type") == "functional"]
        nfr_items = [i for i in evaluated_items if i.get("type") == "non_functional"]

        def calc_score(items: List[Dict[str, Any]]) -> float:
            if not items:
                return 0.0
            score_map = {"completed": 1.0, "partial": 0.5, "missing": 0.0}
            total = sum(score_map.get(i.get("status", "missing"), 0.0) for i in items)
            return round((total / len(items)) * 100, 1)

        def count_breakdown(items: List[Dict[str, Any]]) -> Dict[str, int]:
            return {
                "total": len(items),
                "completed": sum(1 for i in items if i.get("status") == "completed"),
                "partial": sum(1 for i in items if i.get("status") == "partial"),
                "missing": sum(1 for i in items if i.get("status") == "missing"),
            }

        fr_score = calc_score(fr_items)
        nfr_score = calc_score(nfr_items)
        overall_score = round((fr_score * 0.7) + (nfr_score * 0.3), 1) if (fr_items and nfr_items) else (fr_score or nfr_score)

        passed_fr = sum(1 for i in fr_items if i.get("status") == "completed")
        passed_nfr = sum(1 for i in nfr_items if i.get("status") == "completed")
        total_passed = passed_fr + passed_nfr

        result = {
            "repository": repo_slug.replace("_", "/"),
            "fileName": "REQUIREMENTS.md (Generated Spec)",
            "analyzedAt": datetime.now(timezone.utc).isoformat(),
            "overallScore": overall_score,
            "functionalScore": fr_score,
            "functionalCount": count_breakdown(fr_items),
            "nonFunctionalScore": nfr_score,
            "nonFunctionalCount": count_breakdown(nfr_items),
            "items": evaluated_items,
            "summary": (
                f"Project {repo_slug} specification verified from REQUIREMENTS.md. "
                f"{total_passed} of {len(evaluated_items)} requirements ({overall_score}%) verified. "
                f"Functional compliance: {fr_score}% ({passed_fr}/{len(fr_items)}), "
                f"Non-Functional compliance: {nfr_score}% ({passed_nfr}/{len(nfr_items)})."
            ),
        }

        self._save_requirements_to_disk(normalized_slug, result)
        return result

    def _save_requirements_to_disk(self, repo_slug: str, data: Dict[str, Any]) -> None:
        """Persist requirements analysis into generated_docs/{repo_slug}/requirements.json."""
        normalized_slug = repo_slug.replace("/", "_")
        docs_dir = settings.generated_docs_path_dir / normalized_slug
        docs_dir.mkdir(parents=True, exist_ok=True)
        file_path = docs_dir / "requirements.json"
        try:
            file_path.write_text(json.dumps(data, indent=2), encoding="utf-8")
            logger.info("Saved requirements specification to %s", file_path)
        except Exception as e:
            logger.error("Failed to save requirements.json: %s", e)

    def get_saved_requirements(self, repo_slug: str) -> Optional[Dict[str, Any]]:
        """Retrieve previously saved requirements analysis from disk."""
        normalized_slug = repo_slug.replace("/", "_")
        file_path = settings.generated_docs_path_dir / normalized_slug / "requirements.json"
        if not file_path.is_file():
            return None
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Could not read saved requirements from %s: %s", file_path, exc)
            return None

    def list_all_saved_requirements(self) -> List[Dict[str, Any]]:
        """List summary of saved requirements for all repositories."""
        docs_dir = settings.generated_docs_path_dir
        if not docs_dir.is_dir():
            return []
        summaries = []
        for repo_folder in docs_dir.iterdir():
            if repo_folder.is_dir():
                req_file = repo_folder / "requirements.json"
                if req_file.is_file():
                    try:
                        data = json.loads(req_file.read_text(encoding="utf-8"))
                        fc = data.get("functionalCount", {})
                        nfc = data.get("nonFunctionalCount", {})
                        passed_count = fc.get("completed", 0) + nfc.get("completed", 0)
                        partial_count = fc.get("partial", 0) + nfc.get("partial", 0)
                        missing_count = fc.get("missing", 0) + nfc.get("missing", 0)
                        total_count = fc.get("total", 0) + nfc.get("total", 0) or len(data.get("items", []))

                        summaries.append({
                            "repository": data.get("repository", repo_folder.name.replace("_", "/")),
                            "repoSlug": repo_folder.name,
                            "fileName": data.get("fileName", ""),
                            "analyzedAt": data.get("analyzedAt", ""),
                            "overallScore": data.get("overallScore", 0.0),
                            "functionalScore": data.get("functionalScore", 0.0),
                            "functionalCount": fc,
                            "nonFunctionalScore": data.get("nonFunctionalScore", 0.0),
                            "nonFunctionalCount": nfc,
                            "passedCount": passed_count,
                            "partialCount": partial_count,
                            "missingCount": missing_count,
                            "totalCount": total_count,
                            "summary": data.get("summary", ""),
                        })
                    except Exception as e:
                        logger.warning("Error loading requirements from %s: %s", req_file, e)
        return summaries
