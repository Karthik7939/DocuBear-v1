"""
agents/documentation/documentation_agent.py
---------------------------------------------
Documentation Agent — generates project-wide documentation files:

  1. README.md          — Overview, setup, usage, API reference
  2. ARCHITECTURE.md    — System design, components, data flow, dependencies
  3. REQUIREMENTS.md    — Functional and non-functional requirements specification
  4. WORKFLOW.md        — End-to-end process flowcharts (Mermaid)
  5. CHANGELOG.md       — Commit history (new entries prepended, old entries preserved)
  6. SECURITY.md        — Security model, risks, and recommendations
  7. REPORTS.md         — Circular dependencies + unreferenced components,
                           computed deterministically (no LLM call)

Incremental update strategy:
  - README, ARCHITECTURE, REQUIREMENTS, WORKFLOW, SECURITY: the agent reads the existing
    file from disk and passes it to the LLM with instructions to update ONLY
    the sections affected by the current push. Unchanged sections are copied
    word-for-word, minimising diff noise in the frontend review view.
  - CHANGELOG: the LLM generates ONLY the new entry for this push. The agent
    prepends it to the existing file so old entries are never touched.
  - REPORTS: fully regenerated every run from the current dependency graph
    (agents/documentation/code_reports.py) — no incremental merge needed
    since it's a pure function of current state, not narrative text.

All generated files are stored in shared_memory.documentation.file_docs with .md
keys so the SyncAgent writes them as flat files at the repo documentation root.
"""

from __future__ import annotations

import logging
import time
from datetime import datetime
from pathlib import Path
from typing import List, Optional

from agents.coordinator.coordinator import AgentResult
from agents.memory.shared_memory import SharedMemory, GeneratedDocumentation
from agents.documentation.markdown_formatter import sanitize_markdown
from agents.documentation.context_slicer import ContextSlicer
from agents.documentation.code_reports import render_reports_markdown
from prompts.documentation_prompt import (
    REPO_OVERVIEW_PROMPT,
    REPO_ARCHITECTURE_PROMPT,
    REPO_REQUIREMENTS_PROMPT,
    REPO_WORKFLOW_PROMPT,
    CHANGELOG_ENTRY_PROMPT,
    SECURITY_DOC_PROMPT,
)

logger = logging.getLogger(__name__)

# Root folder where SyncAgent writes generated docs
_OUTPUT_ROOT = Path("generated_docs")


class DocumentationAgent:
    """
    Documentation Generation Agent.

    Generates exactly 6 project-wide Markdown files:
      README.md, ARCHITECTURE.md, WORKFLOW.md, CHANGELOG.md, SECURITY.md, REPORTS.md

    Uses incremental update: reads existing files from disk and passes them
    to the LLM so only changed sections are rewritten.
    """

    def __init__(self, llm_client) -> None:
        self._llm = llm_client
        self._slicer = ContextSlicer()

    def run(self, shared_memory: SharedMemory) -> AgentResult:
        """
        Generate / update the 4 documentation files.

        Reads:  shared_memory.understanding, shared_memory.metadata,
                shared_memory.repository, shared_memory.rag_context_package
                + existing files from disk (for incremental updates)
        Writes: shared_memory.documentation.file_docs
        """
        start = time.monotonic()

        und = shared_memory.understanding
        if not und or not und.project_summary:
            return AgentResult(
                success=False,
                message="Understanding section is empty in shared memory",
                recoverable=False,
            )

        docs = shared_memory.documentation or GeneratedDocumentation()
        warnings: List[str] = []
        ctx_pkg = getattr(shared_memory, "rag_context_package", None)

        # Global RAG context — top-ranked chunks, budgeted to ~4 000 chars
        global_ctx = self._slicer.get_global_context(ctx_pkg) or "[No RAG context available]"

        meta = shared_memory.metadata
        repo = shared_memory.repository

        # Repo output directory on disk — mirrors SyncAgent output path
        repo_slug = (repo.full_name or repo.name).replace("/", "_")
        repo_out_dir = _OUTPUT_ROOT / repo_slug

        # Shared context strings
        langs_str = (
            ", ".join(f"{l.language} ({l.percentage:.1f}%)" for l in meta.languages)
            or "Unknown"
        )
        frameworks_str = ", ".join(meta.frameworks) or "N/A"
        deps_str = ", ".join(meta.dependencies[:40]) or "N/A"
        entry_points_str = ", ".join(meta.entry_points) or "N/A"
        modules_str = self._format_modules(und)
        services_str = self._format_services(und)
        dep_graph_str = self._format_dependency_graph(und)
        data_flow_str = self._format_data_flow(und)
        apis_str = self._format_apis(und)
        coding_style_str = self._format_coding_style(und)

        repo_full = repo.full_name or repo.name
        repo_short = repo.name or repo_full

        # Changed files for incremental update context
        changed_files_str = "\n".join(
            f"- `{f}` (added)" for f in repo.added_files
        ) + "\n" + "\n".join(
            f"- `{f}` (modified)" for f in repo.modified_files
        )
        if not changed_files_str.strip():
            changed_files_str = "- (no specific files listed)"

        # ------------------------------------------------------------------
        # 1. README.md  — incremental update
        # ------------------------------------------------------------------
        existing_readme = self._read_existing(repo_out_dir, "README.md")
        readme_fallback = (
            f"# {repo_short}\n\n"
            f"## Overview\n{und.project_summary or 'N/A'}\n\n"
            f"## Purpose\n{und.project_purpose or 'N/A'}\n\n"
            f"## Tech Stack\n- Languages: {langs_str}\n- Frameworks: {frameworks_str}\n"
        )
        readme = self._llm_call(
            REPO_OVERVIEW_PROMPT.format(
                repository_name=repo_full,
                repo_name=repo_short,
                branch=repo.branch or "main",
                languages=langs_str,
                frameworks=frameworks_str,
                author=repo.author or "Unknown",
                changed_files=changed_files_str,
                project_summary=und.project_summary or "N/A",
                project_purpose=und.project_purpose or "N/A",
                architecture_type=und.architecture_type or "Unknown",
                modules=modules_str,
                entry_points=entry_points_str,
                dependencies=deps_str,
                apis=apis_str,
                data_flow=data_flow_str,
                existing_content=existing_readme or "(No existing README — generate from scratch)",
                rag_context=global_ctx,
            ),
            fallback=readme_fallback,
            doc_name="README.md",
            warnings=warnings,
        )
        docs.file_docs["README.md"] = readme

        # ------------------------------------------------------------------
        # 2. ARCHITECTURE.md  — incremental update
        # ------------------------------------------------------------------
        existing_arch = self._read_existing(repo_out_dir, "ARCHITECTURE.md")
        arch_fallback = (
            f"# Architecture — {repo_short}\n\n"
            f"## Architecture Style\n{und.architecture_type or 'Unknown'}\n\n"
            f"## System Components\n{modules_str}\n\n"
            f"## Data Flow\n{data_flow_str}\n"
        )
        architecture = self._llm_call(
            REPO_ARCHITECTURE_PROMPT.format(
                repository_name=repo_full,
                repo_name=repo_short,
                architecture_type=und.architecture_type or "Unknown",
                directory_tree=self._clean_directory_tree(meta.directory_tree) or "N/A",
                changed_files=changed_files_str,
                modules=modules_str,
                services=services_str,
                dependency_graph=dep_graph_str,
                data_flow=data_flow_str,
                coding_style=coding_style_str,
                apis=apis_str,
                existing_content=existing_arch or "(No existing ARCHITECTURE.md — generate from scratch)",
                rag_context=global_ctx,
            ),
            fallback=arch_fallback,
            doc_name="ARCHITECTURE.md",
            warnings=warnings,
        )
        docs.file_docs["ARCHITECTURE.md"] = architecture

        # ------------------------------------------------------------------
        # 3. REQUIREMENTS.md  — incremental update
        # ------------------------------------------------------------------
        existing_req = self._read_existing(repo_out_dir, "REQUIREMENTS.md")
        req_fallback = (
            f"# Requirements Specification — {repo_short}\n\n"
            f"## 1. Functional Requirements (FR)\n\n"
            f"### 1.1 Core Capabilities\n"
            f"- **FR-1.1.1**: The system must provide {und.project_summary or 'core functionality'}.\n"
            f"- **FR-1.1.2**: The system must implement the following key modules: {modules_str[:200]}.\n\n"
            f"## 2. Non-Functional Requirements (NFR)\n\n"
            f"### 2.1 Architecture & Performance\n"
            f"- **NFR-2.1.1**: The system architecture must adhere to {und.architecture_type or 'standard'} conventions.\n\n"
            f"## 3. Error Handling & Protocols\n"
            f"- The system must validate inputs and gracefully handle operational errors.\n"
        )
        requirements = self._llm_call(
            REPO_REQUIREMENTS_PROMPT.format(
                repository_name=repo_full,
                repo_name=repo_short,
                architecture_type=und.architecture_type or "Unknown",
                changed_files=changed_files_str,
                project_summary=und.project_summary or "N/A",
                project_purpose=und.project_purpose or "N/A",
                modules=modules_str,
                services=services_str,
                apis=apis_str,
                data_flow=data_flow_str,
                existing_content=existing_req or "(No existing REQUIREMENTS.md — generate from scratch)",
                rag_context=global_ctx,
            ),
            fallback=req_fallback,
            doc_name="REQUIREMENTS.md",
            warnings=warnings,
        )
        docs.file_docs["REQUIREMENTS.md"] = requirements

        # ------------------------------------------------------------------
        # 4. WORKFLOW.md  — incremental update
        # ------------------------------------------------------------------
        existing_workflow = self._read_existing(repo_out_dir, "WORKFLOW.md")
        process_signal_files_str = self._format_process_signal_files(meta.configuration_files)
        commit_history_excerpt_str = self._format_commit_history_excerpt(
            self._read_existing(repo_out_dir, "CHANGELOG.md")
        )
        workflow_fallback = (
            f"# Workflow — {repo_short}\n\n"
            f"## Overview\n{und.project_summary or 'N/A'}\n\n"
            f"## End-to-End Flow\n```mermaid\nflowchart TD\n"
            f"    A[Entry Point] --> B[Processing]\n    B --> C[Output]\n```\n"
        )
        workflow = self._llm_call(
            REPO_WORKFLOW_PROMPT.format(
                repository_name=repo_full,
                repo_name=repo_short,
                architecture_type=und.architecture_type or "Unknown",
                entry_points=entry_points_str,
                changed_files=changed_files_str,
                modules=modules_str,
                services=services_str,
                apis=apis_str,
                data_flow=data_flow_str,
                dependency_graph=dep_graph_str,
                process_signal_files=process_signal_files_str,
                commit_history_excerpt=commit_history_excerpt_str,
                existing_content=existing_workflow or "(No existing WORKFLOW.md — generate from scratch)",
                rag_context=global_ctx,
            ),
            fallback=workflow_fallback,
            doc_name="WORKFLOW.md",
            warnings=warnings,
        )
        docs.file_docs["WORKFLOW.md"] = workflow

        # ------------------------------------------------------------------
        # 4. CHANGELOG.md  — prepend new entry, never overwrite old entries
        # ------------------------------------------------------------------
        added_files_str = "\n".join(f"- `{f}`" for f in repo.added_files) or "- None"
        modified_files_str = "\n".join(f"- `{f}`" for f in repo.modified_files) or "- None"
        commit_sha = repo.commit_sha or "HEAD"
        commit_sha_short = commit_sha[:8]
        push_date, push_time = self._format_push_datetime(repo.push_timestamp)
        commit_message = (repo.commit_message or "No commit message provided").strip()
        commit_message_summary = commit_message.splitlines()[0][:72]

        new_entry_fallback = (
            f"## [{commit_sha_short}] {commit_message_summary}\n"
            f"**Date:** {push_date}  **Time:** {push_time}\n"
            f"**Author:** {repo.author or 'Unknown'}\n"
            f"**Branch:** `{repo.branch or 'main'}`\n"
            f"**Commit Message:** {commit_message}\n\n"
            f"### Added\n{added_files_str}\n\n"
            f"### Changed\n{modified_files_str}\n\n---\n"
        )
        new_entry = self._llm_call(
            CHANGELOG_ENTRY_PROMPT.format(
                repository_name=repo_full,
                branch=repo.branch or "main",
                commit_sha=commit_sha,
                commit_sha_short=commit_sha_short,
                commit_message=commit_message,
                commit_message_summary=commit_message_summary,
                author=repo.author or "Unknown",
                push_timestamp=repo.push_timestamp or "N/A",
                push_date=push_date,
                push_time=push_time,
                added_files=added_files_str,
                modified_files=modified_files_str,
                project_summary=und.project_summary or "N/A",
                rag_context=global_ctx,
            ),
            fallback=new_entry_fallback,
            doc_name="CHANGELOG.md (new entry)",
            warnings=warnings,
        )

        # Prepend new entry to existing changelog
        existing_changelog = self._read_existing(repo_out_dir, "CHANGELOG.md")
        if existing_changelog:
            # Strip any leading "# Changelog" header from the new entry to avoid duplication
            entry_body = new_entry.lstrip()
            if entry_body.startswith("# Changelog"):
                entry_body = "\n".join(entry_body.splitlines()[1:]).lstrip()
            changelog = f"# Changelog\n\n{entry_body}\n\n{existing_changelog.replace('# Changelog', '').lstrip()}"
        else:
            changelog = f"# Changelog\n\n{new_entry}"

        changelog = sanitize_markdown(changelog)
        docs.file_docs["CHANGELOG.md"] = changelog

        # ------------------------------------------------------------------
        # 5. SECURITY.md  — incremental update
        # ------------------------------------------------------------------
        existing_security = self._read_existing(repo_out_dir, "SECURITY.md")
        security_fallback = (
            f"# Security — {repo_short}\n\n"
            f"## Overview\nSecurity analysis based on automated code review.\n\n"
            f"## Dependencies\n{deps_str}\n\n"
            f"## Reporting Vulnerabilities\n"
            f"*To report a security vulnerability, please contact the repository owner directly.*\n"
        )
        security = self._llm_call(
            SECURITY_DOC_PROMPT.format(
                repository_name=repo_full,
                repo_name=repo_short,
                architecture_type=und.architecture_type or "Unknown",
                frameworks=frameworks_str,
                dependencies=deps_str,
                changed_files=changed_files_str,
                apis=apis_str,
                existing_content=existing_security or "(No existing SECURITY.md — generate from scratch)",
                rag_context=global_ctx,
            ),
            fallback=security_fallback,
            doc_name="SECURITY.md",
            warnings=warnings,
        )
        docs.file_docs["SECURITY.md"] = security

        # ------------------------------------------------------------------
        # 6. REPORTS.md  — deterministic, code-derived (no LLM call)
        # ------------------------------------------------------------------
        docs.file_docs["REPORTS.md"] = render_reports_markdown(
            repo_name=repo_short,
            dependency_graph=und.dependency_graph or {},
            entry_points=meta.entry_points or [],
        )

        shared_memory.documentation = docs
        duration = time.monotonic() - start
        doc_count = len([k for k in docs.file_docs if docs.file_docs[k]])
        logger.info(
            "DocumentationAgent completed in %.2fs: %d doc(s) generated",
            duration, doc_count,
        )

        return AgentResult(
            success=True,
            message=f"Documentation generation completed: {doc_count} document(s)",
            execution_time=duration,
            warnings=warnings,
        )

    # ------------------------------------------------------------------
    # Disk helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_push_datetime(push_timestamp: Optional[str]) -> tuple[str, str]:
        """Split an ISO-8601 push timestamp into a ('Date', 'Time') pair.

        Falls back to the current UTC date/time if the timestamp is missing
        or unparseable, so the changelog never shows a raw 'N/A'.
        """
        if push_timestamp:
            ts = push_timestamp.strip().replace("Z", "+00:00")
            try:
                dt = datetime.fromisoformat(ts)
                return dt.strftime("%Y-%m-%d"), dt.strftime("%H:%M:%S")
            except ValueError:
                pass
        now = datetime.utcnow()
        return now.strftime("%Y-%m-%d"), now.strftime("%H:%M:%S")

    @staticmethod
    def _read_existing(repo_out_dir: Path, filename: str) -> Optional[str]:
        """Read an existing documentation file from disk if it exists."""
        path = repo_out_dir / filename
        if path.exists() and path.is_file():
            try:
                content = path.read_text(encoding="utf-8")
                logger.info("DocumentationAgent: loaded existing %s (%d chars)", filename, len(content))
                return content
            except OSError as exc:
                logger.warning("DocumentationAgent: could not read %s: %s", filename, exc)
        return None

    # ------------------------------------------------------------------
    # LLM Helper
    # ------------------------------------------------------------------

    def _llm_call(
        self,
        prompt: str,
        fallback: Optional[str],
        doc_name: str,
        warnings: Optional[List[str]],
    ) -> str:
        """Call the LLM and return sanitised Markdown. Falls back on failure."""
        if self._llm and hasattr(self._llm, "generate"):
            try:
                logger.info("LLM call: doc=%s  prompt_len=%d chars", doc_name, len(prompt))
                raw = self._llm.generate(prompt)
                if raw and raw.strip():
                    return sanitize_markdown(raw)
            except Exception as exc:
                msg = f"LLM call failed for {doc_name}: {exc}"
                logger.warning(msg)
                if warnings is not None:
                    warnings.append(msg)

        if fallback is not None:
            return sanitize_markdown(fallback)
        return ""

    # ------------------------------------------------------------------
    # Formatting Helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _format_process_signal_files(configuration_files) -> str:
        """Filter configuration files down to CI/CD and process-artifact
        signals the WORKFLOW.md methodology inference can reason from."""
        if not configuration_files:
            return "No configuration files detected."
        keywords = (
            ".github/workflows", "jenkinsfile", "gitlab-ci", ".circleci",
            "azure-pipelines", "docker-compose", "contributing.md",
            "issue_template", "pull_request_template", "codeowners",
            ".pre-commit", "bitbucket-pipelines",
        )
        matches = [f for f in configuration_files if any(k in f.lower() for k in keywords)]
        if matches:
            return "\n".join(f"- `{f}`" for f in matches[:20])
        return (
            "No CI/CD or process-artifact files detected "
            "(no .github/workflows, Jenkinsfile, CONTRIBUTING.md, issue/PR templates, etc.)."
        )

    @staticmethod
    def _format_commit_history_excerpt(changelog_content: Optional[str], max_chars: int = 3000) -> str:
        """Return a truncated excerpt of the most recent CHANGELOG.md entries
        so the WORKFLOW.md methodology inference can judge commit cadence."""
        if not changelog_content or not changelog_content.strip():
            return "No commit history available yet (CHANGELOG.md not yet generated)."
        return changelog_content.strip()[:max_chars]

    @staticmethod
    def _format_modules(und) -> str:
        if not und or not und.modules:
            return "- No modules identified."
        lines = []
        for m in und.modules[:30]:
            deps = ", ".join(m.dependencies[:5]) if m.dependencies else "None"
            lines.append(f"- **{m.name}**: {m.responsibility} (deps: {deps})")
        return "\n".join(lines)

    @staticmethod
    def _format_services(und) -> str:
        if not und or not und.services:
            return "- No services identified."
        lines = []
        for s in und.services[:20]:
            lines.append(f"- **{s.name}**: {s.purpose}")
        return "\n".join(lines)

    @staticmethod
    def _format_apis(und) -> str:
        if not und or not und.apis:
            return "| Method | Route | Description | Request Body | Response |\n|---|---|---|---|---|\n| - | - | No API endpoints identified | - | - |"
        lines = [
            "| Method | Route | Description | Request Body | Response |",
            "|---|---|---|---|---|",
        ]
        for ep in und.apis[:40]:
            req = ep.request_model or "None"
            res = ep.response_model or "None"
            lines.append(f"| **{ep.method}** | `{ep.route}` | {ep.purpose} | `{req}` | `{res}` |")
        return "\n".join(lines)

    @staticmethod
    def _format_dependency_graph(und) -> str:
        if not und or not und.dependency_graph:
            return "No dependency relationships identified."
        lines = []
        for comp, deps in list(und.dependency_graph.items())[:30]:
            if deps:
                for dep in (deps[:5] if isinstance(deps, list) else [deps]):
                    lines.append(f"{comp} → {dep}")
        return "\n".join(lines) if lines else "No relationships identified."

    @staticmethod
    def _format_data_flow(und) -> str:
        if not und or not und.data_flow:
            return "Data flow not identified."
        if isinstance(und.data_flow, list):
            return "\n".join(f"{i + 1}. {step}" for i, step in enumerate(und.data_flow[:20]))
        return str(und.data_flow)[:1000]

    @staticmethod
    def _format_coding_style(und) -> str:
        if not und or not und.coding_style:
            return "No coding style information available."
        lines = []
        for key, val in list(und.coding_style.items())[:10]:
            lines.append(f"- **{key}**: {val}")
        return "\n".join(lines) if lines else "No coding style information available."

    @staticmethod
    def _clean_directory_tree(tree_str: str) -> str:
        """Filter out repetitive image and asset noise from directory tree."""
        if not tree_str:
            return ""
        lines = []
        for line in tree_str.splitlines():
            if any(asset in line for asset in (".svg", ".png", ".jpg", ".jpeg", ".ico", ".gif", ".webp", ".pkl")):
                continue
            lines.append(line)
        return "\n".join(lines[:80])
