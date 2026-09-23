"""
agents/documentation/planner_agent.py
---------------------------------------
Documentation Planning Agent (Agent 3)

Responsibility:
Decides WHAT documentation should exist dynamically based on repository structure,
architecture, and folder classifications. Does NOT hardcode folder names.

Output:
Populates ``shared_memory.plan`` with folder classifications, list of module docs,
list of file docs, repository docs, and reports.
"""

from __future__ import annotations

import logging
import os
from typing import Dict, List, Set

from agents.memory.shared_memory import SharedMemory, DocumentationPlan

logger = logging.getLogger(__name__)

# Folders to strictly ignore and skip documentation generation for
IGNORED_FOLDER_NAMES: Set[str] = {
    "node_modules",
    "dist",
    "build",
    ".cache",
    ".git",
    "__pycache__",
    ".venv",
    "venv",
    "env",
    "tmp",
    "coverage",
    "logs",
    "vendor",
    ".next",
    ".idea",
    ".vscode",
    "bin",
    "obj",
    "target",
    ".pytest_cache",
    ".mypy_cache",
    "generated_docs",
}

# Standard source file extensions to generate file docs for
SOURCE_EXTENSIONS: Set[str] = {
    ".py", ".js", ".ts", ".tsx", ".jsx", ".java", ".go", ".rs",
    ".cpp", ".c", ".h", ".cs", ".php", ".rb", ".kt", ".swift", ".sh"
}


class DocumentationPlanningAgent:
    """
    Documentation Planning Agent (Agent 3).

    Analyzes repository directory structure, classifies every folder dynamically,
    and constructs a targeted DocumentationPlan.
    """

    def __init__(self) -> None:
        pass

    def run(self, shared_memory: SharedMemory) -> None:
        """
        Execute the planning agent.

        Reads:  shared_memory.repository, shared_memory.metadata, shared_memory.understanding
        Writes: shared_memory.plan
        """
        repo_path = shared_memory.repository.path
        logger.info("Documentation Planning Agent started for repo at '%s'", repo_path)

        folder_classifications: Dict[str, str] = {}
        module_docs: List[str] = []
        file_docs: List[str] = []

        if repo_path and os.path.exists(repo_path):
            folder_classifications, module_docs, file_docs = self._analyze_workspace(repo_path)
        else:
            logger.warning("Repository path invalid or empty. Building default plan.")

        plan = DocumentationPlan(
            folder_classifications=folder_classifications,
            repository_docs=[
                "README.md",
                "ARCHITECTURE.md",
                "REQUIREMENTS.md",
                "WORKFLOW.md",
                "CHANGELOG.md",
                "SECURITY.md",
                "REPORTS.md"
            ],
            module_docs=module_docs,
            file_docs=file_docs,
            reports=[
                "dependency",
                "quality",
                "complexity",
                "coverage",
                "health",
                "security",
                "dead_code",
                "circular_deps"
            ],
        )

        shared_memory.plan = plan
        logger.info(
            "Documentation Planning complete: Classified %d folder(s), planned %d module doc(s), %d file doc(s).",
            len(folder_classifications),
            len(module_docs),
            len(file_docs),
        )

    def _analyze_workspace(self, repo_path: str) -> tuple[Dict[str, str], List[str], List[str]]:
        folder_classifications: Dict[str, str] = {}
        module_docs: List[str] = []
        file_docs: List[str] = []

        for root, dirs, files in os.walk(repo_path):
            # Exclude ignored directories in-place
            dirs[:] = [d for d in dirs if d.lower() not in IGNORED_FOLDER_NAMES and not d.startswith(".")]

            rel_root = os.path.relpath(root, repo_path)
            if rel_root == ".":
                classification = "Project Root"
            else:
                classification = self._classify_folder(rel_root, files)

            folder_classifications[rel_root] = classification

            # Decide if module doc should be generated for this directory
            source_files_in_dir = [f for f in files if os.path.splitext(f)[1].lower() in SOURCE_EXTENSIONS]
            
            if classification not in ("Ignored", "Temporary", "Generated") and (
                len(source_files_in_dir) >= 3 or (rel_root != "." and classification in (
                    "API", "Authentication", "Services", "Database", "RAG / AI",
                    "Feature Module", "Application Layer", "Infrastructure"
                ))
            ):
                module_docs.append(rel_root)

            # Record source files for file-level documentation
            for file_name in source_files_in_dir:
                rel_file_path = os.path.join(rel_root, file_name) if rel_root != "." else file_name
                file_docs.append(rel_file_path.replace("\\", "/"))

        return folder_classifications, module_docs, file_docs

    def _classify_folder(self, rel_path: str, files: List[str]) -> str:
        parts = rel_path.replace("\\", "/").lower().split("/")
        last_part = parts[-1]

        if last_part in ("api", "routes", "controllers", "endpoints", "handlers"):
            return "API"
        if last_part in ("auth", "authentication", "jwt", "oauth"):
            return "Authentication"
        if last_part in ("database", "db", "models", "schemas", "repositories", "migrations"):
            return "Database"
        if last_part in ("services", "usecases", "business"):
            return "Services"
        if last_part in ("rag", "embeddings", "llm", "agents", "prompts", "retrieval"):
            return "RAG / AI"
        if last_part in ("utils", "helpers", "common", "core", "lib"):
            return "Utilities"
        if last_part in ("infra", "infrastructure", "docker", "k8s", "config"):
            return "Infrastructure"
        if last_part in ("tests", "test", "spec", "e2e"):
            return "Testing"
        if last_part in ("app", "src"):
            return "Application Layer"
        if last_part in ("components", "views", "pages", "hooks", "widgets"):
            return "UI Components"

        return "Feature Module"
