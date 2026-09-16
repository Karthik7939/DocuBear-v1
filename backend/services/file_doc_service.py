"""
services/file_doc_service.py
-------------------------------
On-demand, single-file documentation generation.

Unlike the full Coordinator pipeline (agents/coordinator/coordinator.py),
which is designed for whole-repo / push-triggered runs across a LangGraph
StateGraph, this service answers one narrow question fast: "generate (or
re-generate) accurate documentation for exactly one file in a repository."

Design:
- File tree + file content are read directly from the local clone
  (repositories/<owner>_<repo>/), the same location every other service
  already reads from (see ChatService._resolve_file / _answer_file_content).
- Imports/exports are extracted deterministically (AST for Python, regex for
  JS/TS) rather than asked of the LLM, so that part of the "accurate
  documentation" requirement never depends on model behaviour.
- RAG context is scoped to the target file via the same ContextSlicer /
  RetrievalPipeline pattern ChatService._retrieve_code_context uses, and
  degrades gracefully (empty context) if the repo hasn't been RAG-indexed.
- Output is written to generated_docs/<repo_slug>/<relative_path>.md using
  the exact same path convention as SyncAgent._file_doc_path, and the same
  `.prev.md` sidecar-on-overwrite behaviour as SyncAgent._write_file, so the
  existing /api/documents/* endpoints (content/save/approve/revise) work on
  these files without any changes.
"""

from __future__ import annotations

import ast
import base64
import logging
import re
import time
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Optional

from agents.documentation.context_slicer import ContextSlicer
from agents.documentation.file_extractor import FileContentExtractor
from agents.documentation.markdown_formatter import sanitize_markdown
from agents.documentation.planner_agent import IGNORED_FOLDER_NAMES
from agents.validation.validation_agent import ValidationAgent
from prompts.documentation_prompt import FILE_DOCUMENTATION_PROMPT
from services.repository_service import RepositoryService

logger = logging.getLogger(__name__)

_OUTPUT_ROOT = Path("generated_docs")

# Binary/asset extensions that never get a generated doc — mirrors the asset
# filter DocumentationAgent._clean_directory_tree already applies to keep
# noise out of the ARCHITECTURE.md directory tree.
NON_DOCUMENTABLE_EXTENSIONS: set[str] = {
    ".png", ".jpg", ".jpeg", ".gif", ".ico", ".svg", ".webp", ".bmp",
    ".pkl", ".woff", ".woff2", ".ttf", ".eot", ".otf",
    ".mp3", ".mp4", ".mov", ".avi", ".zip", ".tar", ".gz", ".7z",
    ".pdf", ".exe", ".dll", ".so", ".dylib", ".bin", ".lock",
}

_JS_LIKE_EXTENSIONS = {".js", ".jsx", ".ts", ".tsx", ".mjs", ".cjs"}

# The whole-repo Coordinator pipeline (DocumentationAgent) writes exactly
# these top-level files per repository (see documentation_agent.py). They
# live in the same generated_docs/<repo_slug>/ folder as on-demand file docs,
# so list_generated_docs() must exclude them by name — otherwise they'd show
# up as if they were per-file documentation on the /file-docs History panel.
_STANDARD_DOC_NAMES = {
    "README.md",
    "ARCHITECTURE.md",
    "WORKFLOW.md",
    "CHANGELOG.md",
    "SECURITY.md",
    "REPORTS.md",
}


class RepositoryNotClonedError(Exception):
    """Raised when a repository has no local clone under repositories/."""


class FileNotFoundInRepoError(Exception):
    """Raised when the requested relative path doesn't exist in the clone."""


@dataclass
class FileDocumentResult:
    """Everything the /api/files/generate-doc endpoint needs to respond with."""

    id: str
    repo_id: str
    title: str
    source_path: str
    status: str
    created_at: str
    has_changes: bool
    content: str
    previous_content: Optional[str]
    warnings: list[str] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    exports: list[str] = field(default_factory=list)


class FileDocumentationService:
    """Generates and serves documentation for a single file on demand."""

    def __init__(self, repository_service: RepositoryService, llm_client) -> None:
        self._repos = repository_service
        self._llm = llm_client
        self._extractor = FileContentExtractor()
        self._slicer = ContextSlicer()
        self._validator = ValidationAgent(llm_client=None)

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def list_tree(self, repository_name: str) -> dict:
        """Return a nested {name, path, type, children} tree for a repo.

        Args:
            repository_name: Full repository name, e.g. 'owner/repo'.

        Returns:
            dict: Root tree node.

        Raises:
            RepositoryNotClonedError: If the repo has no local clone.
        """
        slug = repository_name.replace("/", "_")
        root = Path(self._repos.get_repository_path(slug))
        if not root.is_dir():
            raise RepositoryNotClonedError(
                f"Repository '{repository_name}' is not cloned locally yet."
            )

        return {
            "name": root.name,
            "path": "",
            "type": "dir",
            "children": self._build_tree(root, root),
        }

    def list_generated_docs(self, repository_name: str) -> list[dict]:
        """List all previously generated file docs for a repository.

        Scans generated_docs/<repo_slug>/ for *.md files (excluding .prev.md
        sidecars) so the frontend can show what's already been documented
        without re-reading source files or calling the LLM.

        Args:
            repository_name: Full repository name, e.g. 'owner/repo'.

        Returns:
            list[dict]: One entry per generated doc, newest first.
        """
        slug = repository_name.replace("/", "_")
        repo_out_dir = _OUTPUT_ROOT / slug
        if not repo_out_dir.is_dir():
            return []

        entries: list[dict] = []
        for doc_path in repo_out_dir.rglob("*.md"):
            if doc_path.name.endswith(".prev.md"):
                continue
            if doc_path.name in _STANDARD_DOC_NAMES:
                continue
            relative_path = doc_path.relative_to(repo_out_dir).as_posix()
            if relative_path.endswith(".md"):
                relative_path = relative_path[: -len(".md")]

            stat = doc_path.stat()
            doc_relative = Path(slug) / f"{relative_path}.md"
            sidecar = doc_path.with_suffix(".prev.md")
            entries.append({
                "id": self._document_id(doc_relative),
                "repo_id": slug,
                "title": doc_relative.with_suffix("").as_posix(),
                "source_path": relative_path,
                "created_at": datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
                "has_changes": sidecar.is_file(),
            })

        entries.sort(key=lambda e: e["created_at"], reverse=True)
        return entries

    def generate_file_doc(
        self,
        repository_name: str,
        relative_path: str,
        force: bool = False,
    ) -> FileDocumentResult:
        """Get-or-generate documentation for one file.

        Args:
            repository_name: Full repository name, e.g. 'owner/repo'.
            relative_path:   File path relative to the repo root.
            force:           If True, always regenerate (moving any existing
                              content to a .prev.md sidecar for diffing). If
                              False, an existing generated doc is returned
                              as-is without calling the LLM.

        Returns:
            FileDocumentResult

        Raises:
            RepositoryNotClonedError: If the repo has no local clone.
            FileNotFoundInRepoError:  If relative_path doesn't exist in the clone.
        """
        slug = repository_name.replace("/", "_")
        repo_root = Path(self._repos.get_repository_path(slug)).resolve()
        if not repo_root.is_dir():
            raise RepositoryNotClonedError(
                f"Repository '{repository_name}' is not cloned locally yet."
            )

        normalised = relative_path.replace("\\", "/").lstrip("/")
        source_path = (repo_root / normalised).resolve()
        if repo_root != source_path and repo_root not in source_path.parents:
            raise FileNotFoundInRepoError(f"'{relative_path}' escapes the repository root.")
        if not source_path.is_file():
            raise FileNotFoundInRepoError(f"'{relative_path}' does not exist in the repository.")

        repo_out_dir = _OUTPUT_ROOT / slug
        doc_path = self._doc_path(repo_out_dir, normalised)

        if not force and doc_path.is_file():
            return self._read_existing(slug, normalised, doc_path, source_path)

        return self._generate(repository_name, slug, normalised, source_path, doc_path)

    # ------------------------------------------------------------------
    # Tree building
    # ------------------------------------------------------------------

    def _build_tree(self, directory: Path, repo_root: Path) -> list[dict]:
        entries: list[dict] = []
        try:
            children = sorted(
                directory.iterdir(), key=lambda p: (p.is_file(), p.name.lower())
            )
        except OSError as exc:
            logger.warning("Could not list directory %s: %s", directory, exc)
            return entries

        for child in children:
            if child.is_dir():
                if child.name.lower() in IGNORED_FOLDER_NAMES or child.name.startswith("."):
                    continue
                entries.append({
                    "name": child.name,
                    "path": child.relative_to(repo_root).as_posix(),
                    "type": "dir",
                    "children": self._build_tree(child, repo_root),
                })
            elif child.is_file():
                ext = child.suffix.lower()
                entries.append({
                    "name": child.name,
                    "path": child.relative_to(repo_root).as_posix(),
                    "type": "file",
                    "documentable": ext not in NON_DOCUMENTABLE_EXTENSIONS,
                })

        return entries

    # ------------------------------------------------------------------
    # Read-existing path (force=False, doc already on disk)
    # ------------------------------------------------------------------

    def _read_existing(
        self, slug: str, relative_path: str, doc_path: Path, source_path: Path
    ) -> FileDocumentResult:
        content = doc_path.read_text(encoding="utf-8")
        previous_content = None
        sidecar = doc_path.with_suffix(".prev.md")
        if sidecar.is_file():
            try:
                previous_content = sidecar.read_text(encoding="utf-8")
            except OSError:
                previous_content = None

        # Recompute imports/exports from the current source file (cheap,
        # deterministic — no LLM call) so the dependency chips are populated
        # even on a cache hit, not only right after a fresh generation.
        imports: list[str] = []
        exports: list[str] = []
        try:
            source_content = source_path.read_text(encoding="utf-8", errors="replace")
            imports, exports = self._extract_dependencies(relative_path, source_content)
        except OSError as exc:
            logger.warning("Could not re-read source for dependency chips %s: %s", source_path, exc)

        stat = doc_path.stat()
        doc_relative = Path(slug) / f"{relative_path}.md"
        return FileDocumentResult(
            id=self._document_id(doc_relative),
            repo_id=slug,
            title=doc_relative.with_suffix("").as_posix(),
            source_path=relative_path,
            status="pending_review",
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            has_changes=previous_content is not None,
            content=content,
            previous_content=previous_content,
            imports=imports,
            exports=exports,
        )

    # ------------------------------------------------------------------
    # Generation path
    # ------------------------------------------------------------------

    def _generate(
        self,
        repository_name: str,
        slug: str,
        relative_path: str,
        source_path: Path,
        doc_path: Path,
    ) -> FileDocumentResult:
        start = time.monotonic()

        try:
            content = source_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            raise FileNotFoundInRepoError(f"Could not read '{relative_path}': {exc}") from exc

        skeleton = self._extractor.extract(relative_path, content)
        imports, exports = self._extract_dependencies(relative_path, content)

        rag_context = self._retrieve_rag_context(repository_name, relative_path)

        existing_content = doc_path.read_text(encoding="utf-8") if doc_path.is_file() else None

        prompt = FILE_DOCUMENTATION_PROMPT.format(
            repository_name=repository_name,
            file_path=relative_path,
            language=Path(relative_path).suffix.lstrip(".") or "text",
            file_skeleton=skeleton or "(No skeleton could be extracted for this file.)",
            imports="\n".join(f"- `{i}`" for i in imports) or "- None detected",
            exports="\n".join(f"- `{e}`" for e in exports) or "- None detected",
            rag_context=rag_context or "[No RAG context available]",
            existing_content=existing_content or "(No existing documentation — generating for the first time.)",
        )

        generated = self._llm_call(prompt, relative_path)

        # Move the previous version to a .prev.md sidecar before overwriting,
        # exactly like SyncAgent._write_file, so /api/documents/* diffing works.
        previous_content: Optional[str] = None
        if doc_path.is_file():
            previous_content = doc_path.read_text(encoding="utf-8")
            sidecar = doc_path.with_suffix(".prev.md")
            try:
                sidecar.write_text(previous_content, encoding="utf-8")
            except OSError as exc:
                logger.warning("Could not write .prev.md sidecar for %s: %s", doc_path, exc)

        doc_path.parent.mkdir(parents=True, exist_ok=True)
        doc_path.write_text(generated, encoding="utf-8")

        doc_key = f"{relative_path}"  # contains "/" for most files -> per-file validation rules apply
        validation = self._validator._validate_structure(doc_key, generated)
        warnings = list(validation.warnings) + [
            f"Missing section: {m}" for m in validation.missing_sections
        ]

        duration = time.monotonic() - start
        logger.info(
            "FileDocumentationService: generated doc for %s (%s) in %.2fs",
            relative_path, repository_name, duration,
        )

        doc_relative = Path(slug) / f"{relative_path}.md"
        stat = doc_path.stat()
        return FileDocumentResult(
            id=self._document_id(doc_relative),
            repo_id=slug,
            title=doc_relative.with_suffix("").as_posix(),
            source_path=relative_path,
            status="pending_review",
            created_at=datetime.fromtimestamp(stat.st_mtime, tz=timezone.utc).isoformat(),
            has_changes=previous_content is not None,
            content=generated,
            previous_content=previous_content,
            warnings=warnings,
            imports=imports,
            exports=exports,
        )

    def _llm_call(self, prompt: str, relative_path: str) -> str:
        if self._llm and hasattr(self._llm, "generate"):
            try:
                raw = self._llm.generate(prompt)
                if raw and raw.strip():
                    return sanitize_markdown(raw)
            except Exception as exc:
                logger.warning("LLM call failed for file doc %s: %s", relative_path, exc)

        return sanitize_markdown(
            f"# {relative_path}\n\n## Overview\nDocumentation could not be generated "
            f"automatically for this file.\n\n## Change Summary\nNot evident from the "
            f"available source.\n\n## Key Components\nNot evident from the available "
            f"source.\n\n## Dependencies & Imports\nNot evident from the available "
            f"source.\n\n## Exports / Public API\nNot evident from the available "
            f"source.\n"
        )

    def _retrieve_rag_context(self, repository_name: str, relative_path: str) -> str:
        try:
            from rag.pipeline.retrieval_pipeline import RetrievalPipeline
            from rag.schemas.query import SemanticQuery

            query = SemanticQuery(
                repository=repository_name,
                commit_sha="HEAD",
                query_text=f"Implementation details and usage of {relative_path}",
                top_k=8,
            )
            pipeline = RetrievalPipeline(repository=repository_name)
            context_package = pipeline.retrieve(query)
            return self._slicer.get_chunks_for_file(relative_path, context_package)
        except Exception as exc:
            logger.warning(
                "RAG retrieval unavailable for %s (%s): %s", repository_name, relative_path, exc
            )
            return ""

    # ------------------------------------------------------------------
    # Deterministic import/export extraction
    # ------------------------------------------------------------------

    @staticmethod
    def _extract_dependencies(relative_path: str, content: str) -> tuple[list[str], list[str]]:
        ext = Path(relative_path).suffix.lower()

        if ext == ".py":
            return FileDocumentationService._extract_python_dependencies(content)
        if ext in _JS_LIKE_EXTENSIONS:
            return FileDocumentationService._extract_js_dependencies(content)
        return [], []

    @staticmethod
    def _extract_python_dependencies(content: str) -> tuple[list[str], list[str]]:
        imports: list[str] = []
        exports: list[str] = []
        try:
            tree = ast.parse(content)
        except SyntaxError:
            return imports, exports

        for node in tree.body:
            if isinstance(node, ast.Import):
                for alias in node.names:
                    imports.append(alias.name)
            elif isinstance(node, ast.ImportFrom):
                module = node.module or ""
                names = ", ".join(alias.name for alias in node.names)
                imports.append(f"from {module} import {names}")
            elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                if not node.name.startswith("_"):
                    exports.append(node.name)
            elif isinstance(node, ast.ClassDef):
                if not node.name.startswith("_"):
                    exports.append(node.name)

        return imports, exports

    @staticmethod
    def _extract_js_dependencies(content: str) -> tuple[list[str], list[str]]:
        imports: list[str] = []
        exports: list[str] = []

        for m in re.finditer(r"^\s*import\s+.+?\s+from\s+['\"]([^'\"]+)['\"]", content, re.MULTILINE):
            imports.append(m.group(0).strip().rstrip(";"))
        for m in re.finditer(r"^\s*import\s+['\"]([^'\"]+)['\"]", content, re.MULTILINE):
            imports.append(m.group(0).strip().rstrip(";"))
        for m in re.finditer(r"require\(\s*['\"]([^'\"]+)['\"]\s*\)", content):
            imports.append(f"require('{m.group(1)}')")

        for m in re.finditer(r"^\s*export\s+default\s+(?:function|class)\s+(\w+)", content, re.MULTILINE):
            exports.append(f"default {m.group(1)}")
        for m in re.finditer(r"^\s*export\s+(?:const|let|var|function|class|interface|type)\s+(\w+)", content, re.MULTILINE):
            exports.append(m.group(1))
        for m in re.finditer(r"^\s*export\s*\{([^}]+)\}", content, re.MULTILINE):
            names = [n.strip().split(" as ")[0].strip() for n in m.group(1).split(",") if n.strip()]
            exports.extend(names)

        # Deduplicate while preserving order
        imports = list(dict.fromkeys(imports))
        exports = list(dict.fromkeys(exports))
        return imports, exports

    # ------------------------------------------------------------------
    # Path / id helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _doc_path(repo_output_dir: Path, relative_path: str) -> Path:
        """Same convention as SyncAgent._file_doc_path: mirror source path + '.md'."""
        normalised = relative_path.replace("\\", "/")
        return repo_output_dir / f"{normalised}.md"

    @staticmethod
    def _document_id(relative_path: Path) -> str:
        """Same base64 id scheme as app/api/documents.py's _document_id, so the
        returned id is interchangeable with /api/documents/* endpoints."""
        encoded = base64.urlsafe_b64encode(relative_path.as_posix().encode("utf-8"))
        return encoded.decode("ascii").rstrip("=")
