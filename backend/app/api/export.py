"""
app/api/export.py
--------------------
FastAPI routes for the Publish page's "Export" section: bundling a chosen
set of a repository's generated Markdown documents into one downloadable
PDF, and listing/serving previously generated exports.
"""

from typing import List, Optional

from fastapi import APIRouter, HTTPException, Query, status
from fastapi.responses import FileResponse
from pydantic import BaseModel, Field

from app.core.config import settings
from services.pdf_export_service import (
    ExportNotFoundError,
    NoDocumentsSelectedError,
    PdfExportService,
)

router = APIRouter(prefix="/api/export", tags=["Export"])
export_service = PdfExportService(settings.generated_docs_path_dir)


class GenerateExportRequest(BaseModel):
    repository_name: str = Field(description="Repository name e.g. 'owner/repo'")
    files: List[str] = Field(
        description=(
            "Paths relative to generated_docs/<repo_slug>/ to include, e.g. "
            "['README.md', 'app/api/webhook.py.md']."
        )
    )
    title: Optional[str] = Field(default=None, description="Optional cover-page title; defaults to repository_name")


class ExportRecordResponse(BaseModel):
    id: str
    repository_name: str
    repo_slug: str
    download_filename: str
    title: str
    documents: List[str]
    created_at: str
    size_bytes: int


@router.post("/generate", response_model=ExportRecordResponse)
async def generate_export(data: GenerateExportRequest) -> ExportRecordResponse:
    """Render the selected documents into one PDF and record it in history."""
    if not data.repository_name.strip():
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="repository_name is required")

    try:
        record = export_service.generate(
            repository_name=data.repository_name.strip(),
            filenames=data.files,
            title=data.title,
        )
    except NoDocumentsSelectedError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
    except FileNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"PDF export failed: {exc}",
        ) from exc

    return ExportRecordResponse(**record.to_dict())


@router.get("/history", response_model=List[ExportRecordResponse])
async def list_export_history(
    repository_name: str = Query(..., description="Repository name e.g. 'owner/repo'"),
) -> List[ExportRecordResponse]:
    """List previously generated PDF exports for a repository, newest first."""
    records = export_service.list_exports(repository_name)
    return [ExportRecordResponse(**r.to_dict()) for r in records]


@router.get("/download/{repo_slug}/{export_id}")
async def download_export(repo_slug: str, export_id: str) -> FileResponse:
    """Download a previously generated export PDF by its id."""
    try:
        pdf_path = export_service.resolve_export_path(repo_slug, export_id)
    except ExportNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc

    download_filename = export_service.download_filename_for(repo_slug, export_id)
    return FileResponse(
        path=pdf_path,
        media_type="application/pdf",
        filename=download_filename,
        headers={"Access-Control-Allow-Origin": "*"},
    )
