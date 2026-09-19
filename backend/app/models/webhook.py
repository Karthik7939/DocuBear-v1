"""
app/models/webhook.py
----------------------
Pydantic models for incoming GitHub webhook payloads.

These models validate the structure of the JSON body sent by GitHub on a
push event.  Only the fields this service actually needs are declared;
additional fields in the payload are silently ignored.
"""

from typing import Optional

from pydantic import BaseModel, Field


class Owner(BaseModel):
    """Represents the owner of a GitHub repository."""

    name: Optional[str] = Field(None, description="GitHub username or organisation name.")
    login: Optional[str] = Field(None, description="GitHub login username.")
    email: Optional[str] = Field(None, description="Owner's email address (may be absent).")


class Repository(BaseModel):
    """Represents a GitHub repository as reported in a push webhook."""

    id: Optional[int] = Field(None, description="GitHub's internal numeric repository ID.")
    name: str = Field(..., description="Repository name without the owner prefix.")
    full_name: str = Field(..., description="Full repository name, e.g. 'owner/repo'.")
    clone_url: Optional[str] = Field(None, description="HTTPS URL used for cloning.")
    default_branch: Optional[str] = Field(None, description="Default branch of the repository.")
    owner: Optional[Owner] = Field(None, description="Owner information.")

    @property
    def owner_repo_slug(self) -> str:
        """Return a filesystem-safe slug derived from the full repository name."""
        return self.full_name.replace("/", "_")

    @property
    def git_clone_url(self) -> str:
        """Return the clone URL, falling back to HTTPS github URL."""
        return self.clone_url or f"https://github.com/{self.full_name}.git"


class Commit(BaseModel):
    """Represents a single commit included in a push event."""

    id: str = Field(..., description="Full SHA of the commit.")
    message: str = Field("", description="Commit message.")
    timestamp: str = Field("", description="ISO-8601 commit timestamp.")
    added: list[str] = Field(default_factory=list, description="Files added in this commit.")
    modified: list[str] = Field(default_factory=list, description="Files modified in this commit.")
    removed: list[str] = Field(default_factory=list, description="Files removed in this commit.")

    class Config:
        populate_by_name = True


class Pusher(BaseModel):
    """Represents the GitHub user who performed the push."""

    name: Optional[str] = Field(None, description="GitHub username of the pusher.")
    email: Optional[str] = Field(None, description="Pusher's email address.")


class WebhookPayload(BaseModel):
    """Top-level model for a GitHub push webhook payload."""

    ref: str = Field(..., description="Full Git ref that was pushed, e.g. 'refs/heads/main'.")
    before: Optional[str] = Field(None, description="SHA of the most recent commit before the push.")
    after: Optional[str] = Field(None, description="SHA of the most recent commit after the push.")
    repository: Repository = Field(..., description="Repository metadata.")
    pusher: Optional[Pusher] = Field(None, description="User who triggered the push.")
    commits: list[Commit] = Field(default_factory=list, description="List of commits in this push.")
    head_commit: Optional[Commit] = Field(None, description="The HEAD commit after the push.")

    @property
    def branch(self) -> str:
        """Extract the short branch name from the ref string."""
        return self.ref.removeprefix("refs/heads/")
