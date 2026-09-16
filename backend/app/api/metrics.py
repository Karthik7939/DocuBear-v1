"""
app/api/metrics.py
--------------------
Read-only API for the analytics dashboard.

Combines two sources, both already on disk — no LLM calls, no recomputation:
  - metrics.json: a run-level KPI snapshot written by the Coordinator after
    each documentation generation (see agents/coordinator/run_metrics.py).
  - CHANGELOG.md: parsed on read for commit/contributor counts, since those
    accumulate across every push rather than reflecting a single run.
"""

import json
import logging
import re
from pathlib import Path
from typing import Optional

from fastapi import APIRouter, HTTPException, status
from pydantic import BaseModel

from app.core.config import settings

logger = logging.getLogger(__name__)

router = APIRouter()

_COMMIT_HEADER_RE = re.compile(r"^## \[([0-9a-fA-F]{6,40})\]", re.MULTILINE)
_AUTHOR_LINE_RE = re.compile(r"^\*\*Author:\*\*\s*(.+?)\s*$", re.MULTILINE)


class RunMetrics(BaseModel):
    """Snapshot from the most recent documentation generation run."""

    workflow_id: str = ""
    generated_at: str = ""
    quality_score: float = 0.0
    faithfulness_score: float = 0.0
    faithfulness_notes: str = ""
    generation_time_seconds: float = 0.0
    documents_generated: int = 0
    average_time_per_document_seconds: float = 0.0
    test_files: int = 0
    source_files: int = 0
    test_coverage_ratio: float = 0.0


class RepositoryMetrics(BaseModel):
    """Combined analytics payload for one repository."""

    repository: str
    has_run_metrics: bool
    run_metrics: Optional[RunMetrics] = None
    commits_documented: int = 0
    contributors_tracked: int = 0
    contributors: list[str] = []


def _docs_root() -> Path:
    return settings.generated_docs_path_dir.resolve()


def _parse_changelog(changelog_path: Path) -> tuple[int, list[str]]:
    """Return (commits_documented, contributors) from a CHANGELOG.md.

    Counts '## [sha]' entry headers and unique '**Author:**' values. Works
    across both changelog formats this codebase has produced (with/without
    the Date/Time/Commit Message fields added later) since both share these
    two markers.
    """
    if not changelog_path.is_file():
        return 0, []
    try:
        content = changelog_path.read_text(encoding="utf-8")
    except OSError:
        return 0, []

    commits = len(_COMMIT_HEADER_RE.findall(content))
    authors_raw = _AUTHOR_LINE_RE.findall(content)
    contributors = list(dict.fromkeys(a.strip() for a in authors_raw if a.strip()))
    return commits, contributors


@router.get("/{repo_slug}", response_model=RepositoryMetrics)
async def get_repository_metrics(repo_slug: str) -> RepositoryMetrics:
    """Return combined analytics metrics for one repository.

    Args:
        repo_slug: The folder name under generated_docs/ (underscored form),
                   e.g. 'Blrm123_Navayatra'.
    """
    # Accept both owner/repo and owner_repo formats
    normalized_slug = repo_slug.replace("/", "_")
    if ".." in normalized_slug:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid repository slug")

    root = _docs_root()
    repo_dir = (root / normalized_slug).resolve()

    repository_name = normalized_slug.replace("_", "/", 1)

    if root not in repo_dir.parents or not repo_dir.is_dir():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Repository not found")

    run_metrics: Optional[RunMetrics] = None
    metrics_path = repo_dir / "metrics.json"
    if metrics_path.is_file():
        try:
            raw = json.loads(metrics_path.read_text(encoding="utf-8"))
            run_metrics = RunMetrics(**raw)
        except (OSError, ValueError, TypeError) as exc:
            logger.warning("metrics: could not parse metrics.json for %s: %s", repo_slug, exc)

    commits_documented, contributors = _parse_changelog(repo_dir / "CHANGELOG.md")

    return RepositoryMetrics(
        repository=repository_name,
        has_run_metrics=run_metrics is not None,
        run_metrics=run_metrics,
        commits_documented=commits_documented,
        contributors_tracked=len(contributors),
        contributors=contributors,
    )
