"""
app/api/gitbook.py
-------------------
FastAPI routes for GitBook REST API integration.
"""

from typing import List, Optional, Dict, Any
from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from services.gitbook_service import GitBookService

router = APIRouter(prefix="/api/gitbook", tags=["GitBook"])
gitbook_service = GitBookService()


class TestConnectionRequest(BaseModel):
    space_id: str = Field(description="GitBook Space ID (e.g. 'space_xxx' or Space slug)")
    api_token: Optional[str] = Field(default="", description="Optional GitBook Developer API token")


class PublishDocumentRequest(BaseModel):
    space_id: str = Field(description="GitBook Space ID")
    filename: str = Field(description="Filename e.g. 'README.md'")
    content: str = Field(description="Markdown content string")
    api_token: Optional[str] = Field(default="", description="Optional GitBook Developer API token")


class PublishRepoRequest(BaseModel):
    repository_name: str = Field(description="Repository name e.g. 'owner/repo'")
    space_id: str = Field(description="Target GitBook Space ID")
    api_token: Optional[str] = Field(default="", description="Optional GitBook Developer API token")
    public_base_url: str = Field(description="Public base URL (e.g. ngrok) where the backend is reachable — used for GitBook's URL import")
    files: Optional[List[str]] = Field(
        default=None,
        description=(
            "Paths relative to generated_docs/<repo_slug>/ to publish, e.g. "
            "['README.md', 'app/api/webhook.py.md']. Omit to publish the "
            "standard doc suite (README, ARCHITECTURE, WORKFLOW, CHANGELOG, "
            "SECURITY, REPORTS) for backward compatibility."
        ),
    )


@router.post("/test-connection")
async def test_connection(data: TestConnectionRequest):
    """
    Test connection to a GitBook Space.
    """
    if not data.space_id.strip():
        raise HTTPException(status_code=400, detail="space_id is required")

    result = gitbook_service.test_connection(
        space_id=data.space_id.strip(),
        token=data.api_token.strip() if data.api_token else None,
    )
    return result


@router.post("/publish-document")
async def publish_document(data: PublishDocumentRequest):
    """
    Publish a single Markdown document to a GitBook Space.
    """
    if not data.space_id.strip():
        raise HTTPException(status_code=400, detail="space_id is required")
    if not data.content.strip():
        raise HTTPException(status_code=400, detail="content is required")

    result = gitbook_service.publish_document(
        space_id=data.space_id.strip(),
        filename=data.filename.strip() or "DOCUMENT.md",
        content=data.content,
        token=data.api_token.strip() if data.api_token else None,
    )
    return result


@router.post("/publish-repo")
async def publish_repo(data: PublishRepoRequest):
    """
    Publish all generated documentation files for a repository to GitBook.
    """
    if not data.repository_name.strip():
        raise HTTPException(status_code=400, detail="repository_name is required")
    if not data.space_id.strip():
        raise HTTPException(status_code=400, detail="space_id is required")

    filenames = [f.strip() for f in data.files if f.strip()] if data.files is not None else gitbook_service.STANDARD_DOC_FILES

    result = gitbook_service.publish_documents(
        repo_name=data.repository_name.strip(),
        space_id=data.space_id.strip(),
        token=data.api_token.strip() if data.api_token else None,
        public_base_url=data.public_base_url.rstrip("/"),
        filenames=filenames,
    )
    return result
