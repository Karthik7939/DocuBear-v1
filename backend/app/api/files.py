"""
app/api/files.py
-------------------
On-demand, single-file documentation API.

Complements /api/documents (which serves whatever the whole-repo Coordinator
pipeline already wrote) with two endpoints that operate on one file at a
time, backed by FileDocumentationService:

  GET  /api/files/tree/{repository_name}   -- folder/file tree for the UI sidebar
  POST /api/files/generate-doc             -- get-or-generate one file's doc
"""

import logging

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from app.dependencies import get_file_doc_service
from services.file_doc_service import (
    FileDocumentationService,
    FileNotFoundInRepoError,
    RepositoryNotClonedError,
)

logger = logging.getLogger(__name__)

router = APIRouter()


class GenerateFileDocRequest(BaseModel):
    repository_name: str
    path: str
    force: bool = False


class FileDocSummaryResponse(BaseModel):
    id: str
    repo_id: str
    title: str
    source_path: str
    created_at: str
    has_changes: bool = False


class FileDocumentResponse(BaseModel):
    id: str
    repo_id: str
    title: str
    source_path: str
    status: str = "pending_review"
    created_at: str
    has_changes: bool = False
    content: str
    previous_content: str | None = None
    warnings: list[str] = []
    imports: list[str] = []
    exports: list[str] = []


@router.get("/tree/{repository_name:path}")
async def get_file_tree(
    repository_name: str,
    service: FileDocumentationService = Depends(get_file_doc_service),
) -> dict:
    """Return a nested folder/file tree for a repository's local clone.

    Args:
        repository_name: Full repo name, e.g. 'owner/repo'.
    """
    try:
        return service.list_tree(repository_name)
    except RepositoryNotClonedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc


@router.get("/docs/{repository_name:path}", response_model=list[FileDocSummaryResponse])
async def list_file_docs(
    repository_name: str,
    service: FileDocumentationService = Depends(get_file_doc_service),
) -> list[FileDocSummaryResponse]:
    """List all previously generated file docs for a repository.

    Lets the frontend show what's already been documented (surviving a page
    refresh) without regenerating anything.

    Args:
        repository_name: Full repo name, e.g. 'owner/repo'.
    """
    return [FileDocSummaryResponse(**entry) for entry in service.list_generated_docs(repository_name)]


@router.post("/generate-doc", response_model=FileDocumentResponse)
async def generate_file_doc(
    body: GenerateFileDocRequest,
    service: FileDocumentationService = Depends(get_file_doc_service),
) -> FileDocumentResponse:
    """Get-or-generate documentation for a single file.

    If a generated doc already exists on disk and ``force`` is False, it is
    returned as-is (no LLM call). Otherwise the file is (re)documented and
    written to generated_docs/<repo_slug>/<path>.md, with the prior content
    (if any) preserved in a .prev.md sidecar for the diff viewer.
    """
    try:
        result = service.generate_file_doc(
            repository_name=body.repository_name,
            relative_path=body.path,
            force=body.force,
        )
    except RepositoryNotClonedError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except FileNotFoundInRepoError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        logger.exception("File doc generation failed for %s:%s", body.repository_name, body.path)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Documentation generation failed: {exc}",
        ) from exc

    return FileDocumentResponse(
        id=result.id,
        repo_id=result.repo_id,
        title=result.title,
        source_path=result.source_path,
        status=result.status,
        created_at=result.created_at,
        has_changes=result.has_changes,
        content=result.content,
        previous_content=result.previous_content,
        warnings=result.warnings,
        imports=result.imports,
        exports=result.exports,
    )
