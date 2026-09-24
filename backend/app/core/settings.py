"""
app/core/settings.py
---------------------
Application settings model.

Responsibilities:
- Declare every configurable value with its type and default
- Read values from environment variables (or .env file via python-dotenv)
- Expose computed path properties for the repository root, workflow dir, and log file
"""

import os
from pathlib import Path

from dotenv import load_dotenv

# Load .env file into os.environ before any field is evaluated.
load_dotenv()


class Settings:
    """Application configuration resolved from environment variables.

    Attributes:
        github_secret:    Optional HMAC secret used to verify GitHub webhook
                          signatures.  Leave empty to skip signature
                          verification (not recommended for production).
        repository_root:  Directory where cloned repositories are stored.
        workflow_path:    Directory where workflow JSON files are persisted.
        log_level:        Python logging level string (DEBUG, INFO, WARNING …).
        log_file:         Path to the rotating log file.
    """

    def __init__(self) -> None:
        self.github_secret: str = os.getenv("GITHUB_SECRET", "")
        self.repository_root: str = os.getenv("REPOSITORY_ROOT", "repositories")
        self.workflow_path: str = os.getenv("WORKFLOW_PATH", "workflow")
        self.generated_docs_path: str = os.getenv("GENERATED_DOCS_PATH", "generated_docs")
        self.log_level: str = os.getenv("LOG_LEVEL", "INFO").upper()
        self.log_file: str = os.getenv("LOG_FILE", "logs/backend.log")

    # ------------------------------------------------------------------
    # Computed path helpers
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_backend_path(path_str: str) -> Path:
        p = Path(path_str)
        if p.is_absolute():
            return p
        if p.exists():
            return p.resolve()
        backend_dir = Path(__file__).resolve().parent.parent.parent
        candidate = backend_dir / p
        if candidate.exists():
            return candidate.resolve()
        return candidate

    @property
    def repository_root_path(self) -> Path:
        """Return the repository root as a Path object."""
        return self._resolve_backend_path(self.repository_root)

    @property
    def workflow_path_dir(self) -> Path:
        """Return the workflow directory as a Path object."""
        return self._resolve_backend_path(self.workflow_path)

    @property
    def generated_docs_path_dir(self) -> Path:
        """Return the root directory containing generated Markdown documents."""
        return self._resolve_backend_path(self.generated_docs_path)

    @property
    def log_file_path(self) -> Path:
        """Return the log file location as a Path object."""
        return self._resolve_backend_path(self.log_file)

    # ------------------------------------------------------------------
    # Convenience
    # ------------------------------------------------------------------

    @property
    def signature_verification_enabled(self) -> bool:
        """Return True if a GitHub secret has been configured."""
        return bool(self.github_secret)

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"Settings("
            f"repository_root={self.repository_root!r}, "
            f"workflow_path={self.workflow_path!r}, "
            f"log_level={self.log_level!r}, "
            f"log_file={self.log_file!r}, "
            f"signature_verification_enabled={self.signature_verification_enabled}"
            f")"
        )
