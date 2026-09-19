"""
app/core/constants.py
----------------------
Application-wide constants.

Contains:
- Workflow status values
- GitHub event names
- Standard response messages
- HTTP header names
- Directory / file naming conventions
- Signature verification constants
"""

from enum import Enum


# ---------------------------------------------------------------------------
# Workflow Statuses
# ---------------------------------------------------------------------------

class WorkflowStatus(str, Enum):
    """All possible lifecycle states of a workflow execution."""

    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"


# ---------------------------------------------------------------------------
# GitHub Event Names
# ---------------------------------------------------------------------------

class GitHubEvent(str, Enum):
    """Recognised GitHub webhook event identifiers."""

    PUSH = "push"
    PING = "ping"


# Events this service will process; all others are rejected with HTTP 400.
SUPPORTED_GITHUB_EVENTS: frozenset[str] = frozenset({GitHubEvent.PUSH, GitHubEvent.PING})


# ---------------------------------------------------------------------------
# HTTP Header Names (lowercase — FastAPI normalises headers to lowercase)
# ---------------------------------------------------------------------------

HEADER_GITHUB_EVENT: str = "x-github-event"
HEADER_GITHUB_SIGNATURE: str = "x-hub-signature-256"
HEADER_CONTENT_TYPE: str = "content-type"


# ---------------------------------------------------------------------------
# Response Messages
# ---------------------------------------------------------------------------

class ResponseMessage(str, Enum):
    """Standard human-readable messages returned in API responses."""

    SUCCESS = "success"
    ERROR = "error"
    HEALTHY = "healthy"
    UNHEALTHY = "unhealthy"

    UNSUPPORTED_EVENT = "Unsupported GitHub event"
    INVALID_SIGNATURE = "Invalid webhook signature"
    INVALID_PAYLOAD = "Invalid webhook payload"
    CLONE_FAILED = "Repository clone failed"
    PULL_FAILED = "Repository pull failed"
    WORKFLOW_SAVE_FAILED = "Workflow save failed"


# ---------------------------------------------------------------------------
# Directory / File Naming
# ---------------------------------------------------------------------------

REPOSITORIES_DIR: str = "repositories"
WORKFLOW_DIR: str = "workflow"
LOGS_DIR: str = "logs"
WORKFLOW_FILE_EXTENSION: str = ".json"


# ---------------------------------------------------------------------------
# Signature Verification
# ---------------------------------------------------------------------------

SIGNATURE_PREFIX: str = "sha256="
HMAC_ALGORITHM: str = "sha256"
