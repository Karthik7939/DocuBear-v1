"""
app/api/requirements.py
-------------------------
API endpoints for uploading Requirements PDF documents, extracting Functional
and Non-Functional requirements, evaluating codebase completion, and returning
the traceability matrix.
"""

import logging
from typing import Any, Dict, Optional

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from pydantic import BaseModel

from services.requirements_service import RequirementsService

logger = logging.getLogger(__name__)

router = APIRouter()
requirements_service = RequirementsService()


@router.post("/upload")
async def upload_requirements_pdf(
    file: UploadFile = File(...),
    repository: str = Form(...),
) -> Dict[str, Any]:
    """Upload a PDF of Functional and Non-Functional Requirements and analyze completion."""
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Only PDF files are supported for requirement analysis.",
        )

    try:
        pdf_bytes = await file.read()
        if len(pdf_bytes) == 0:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Uploaded PDF file is empty.",
            )

        result = requirements_service.process_requirements_document(
            repo_slug=repository,
            file_name=file.filename,
            pdf_bytes=pdf_bytes,
        )
        return result
    except ValueError as val_err:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(val_err),
        )
    except Exception as exc:
        logger.error("Failed to process requirements PDF: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"An error occurred while analyzing the requirements: {str(exc)}",
        )


@router.get("")
@router.get("/")
@router.get("/summary/all")
async def list_all_requirements() -> list[Dict[str, Any]]:
    """List saved requirements summaries for all repositories."""
    return requirements_service.list_all_saved_requirements()


@router.get("/has-markdown/{repo_slug:path}")
async def check_has_markdown(repo_slug: str) -> Dict[str, Any]:
    """Check if generated REQUIREMENTS.md exists for this repository."""
    normalized_slug = repo_slug.replace("/", "_")
    has_md = requirements_service.has_markdown_requirements(normalized_slug)
    return {"repository": repo_slug, "hasMarkdown": has_md}


@router.post("/sync-markdown/{repo_slug:path}")
async def sync_markdown_requirements(repo_slug: str) -> Dict[str, Any]:
    """Import and analyze requirements directly from the generated REQUIREMENTS.md."""
    normalized_slug = repo_slug.replace("/", "_")
    if not requirements_service.has_markdown_requirements(normalized_slug):
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No generated REQUIREMENTS.md found for repository '{repo_slug}'.",
        )

    try:
        result = requirements_service.sync_requirements_from_markdown(normalized_slug)
        return result
    except Exception as exc:
        logger.error("Failed to sync from REQUIREMENTS.md: %s", exc, exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to extract requirements from REQUIREMENTS.md: {str(exc)}",
        )


@router.post("/reanalyze/{repo_slug:path}")
async def reanalyze_requirements(repo_slug: str) -> Dict[str, Any]:
    """Re-evaluate the existing requirements specification directly against latest REQUIREMENTS.md without touching codebase."""
    normalized_slug = repo_slug.replace("/", "_")
    data = requirements_service.get_saved_requirements(normalized_slug)
    
    if not data:
        if requirements_service.has_markdown_requirements(normalized_slug):
            return requirements_service.sync_requirements_from_markdown(normalized_slug)
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No requirements found for '{repo_slug}' to re-analyze. Please upload a PDF first.",
        )

    existing_items = data.get("items", [])
    if not existing_items and requirements_service.has_markdown_requirements(normalized_slug):
        return requirements_service.sync_requirements_from_markdown(normalized_slug)

    evaluated_items = requirements_service._verify_items_against_markdown_specs(
        raw_items=existing_items,
        repo_slug=normalized_slug,
    )

    fr_items = [i for i in evaluated_items if i.get("type") == "functional"]
    nfr_items = [i for i in evaluated_items if i.get("type") == "non_functional"]

    def calc_score(items):
        if not items:
            return 0.0
        score_map = {"completed": 1.0, "partial": 0.5, "missing": 0.0}
        total = sum(score_map.get(i.get("status", "missing"), 0.0) for i in items)
        return round((total / len(items)) * 100, 1)

    def count_breakdown(items):
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

    data.update({
        "overallScore": overall_score,
        "functionalScore": fr_score,
        "functionalCount": count_breakdown(fr_items),
        "nonFunctionalScore": nfr_score,
        "nonFunctionalCount": count_breakdown(nfr_items),
        "items": evaluated_items,
        "summary": (
            f"Requirements specification re-verified against latest REQUIREMENTS.md. "
            f"{total_passed} of {len(evaluated_items)} requirements ({overall_score}%) verified. "
            f"Functional: {fr_score}% ({passed_fr}/{len(fr_items)}), "
            f"Non-Functional: {nfr_score}% ({passed_nfr}/{len(nfr_items)})."
        ),
    })

    requirements_service._save_requirements_to_disk(normalized_slug, data)
    return data


@router.get("/{repo_slug:path}")
async def get_requirements(repo_slug: str) -> Dict[str, Any]:
    """Get the latest requirements analysis for a repository."""
    normalized_slug = repo_slug.replace("/", "_")
    if ".." in normalized_slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid repository slug")

    data = requirements_service.get_saved_requirements(normalized_slug)
    if not data:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No requirements document has been uploaded for repository '{repo_slug}'.",
        )
    return data

