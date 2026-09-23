"""
services/gitbook_service.py
----------------------------
GitBook REST API Service — adapter for publishing generated documentation to GitBook.

GitBook API Endpoint: https://api.gitbook.com/v1
Official Docs: https://developer.gitbook.com/
"""

import os
import logging
from pathlib import Path
from typing import Optional, Dict, Any, List

import httpx

logger = logging.getLogger(__name__)

_GITBOOK_API_BASE = "https://api.gitbook.com/v1"
_OUTPUT_ROOT = Path("generated_docs")


class GitBookService:
    """
    Adapter layer for publishing generated documentation directly to GitBook Spaces via REST API.
    """

    def __init__(self, default_token: Optional[str] = None) -> None:
        self._default_token = default_token or os.getenv("GITBOOK_API_TOKEN", "")

    def _get_headers(self, token: Optional[str] = None) -> Dict[str, str]:
        api_token = token or self._default_token
        if not api_token or not api_token.strip():
            raise ValueError("GitBook Developer API Token is missing. Please enter your API token above.")
        return {
            "Authorization": f"Bearer {api_token.strip()}",
            "Content-Type": "application/json",
        }

    @staticmethod
    def _clean_space_id(space_id: str) -> str:
        """Extract Space ID from a full GitBook URL or raw space_id string."""
        if not space_id:
            return ""
        s = space_id.strip()
        if "gitbook.com" in s:
            import re
            m = re.search(r'/s/([^/]+)', s)
            if m:
                return m.group(1).strip()
        return s

    @staticmethod
    def _extract_org_id(space_id: str) -> str:
        """Extract Organization ID from a full GitBook URL.

        Full URL example:
          https://app.gitbook.com/o/kubIiwLR2j4JEm0CjXFy/s/I3PsINxwWqDEXDNbGknJ/

        Returns the org ID segment, or empty string if not found.
        """
        if not space_id:
            return ""
        s = space_id.strip()
        if "gitbook.com" in s:
            import re
            m = re.search(r'/o/([^/]+)', s)
            if m:
                return m.group(1).strip()
        return ""

    def test_connection(self, space_id: str, token: Optional[str] = None) -> Dict[str, Any]:
        """
        Verify access to a GitBook space.

        Args:
            space_id: GitBook Space ID (or full space URL).
            token: Optional override API token.

        Returns:
            dict: { "success": bool, "space_title": str, "message": str }
        """
        clean_id = self._clean_space_id(space_id)
        if not clean_id:
            return {
                "success": False,
                "message": "GitBook Space ID is required.",
            }

        try:
            headers = self._get_headers(token)
        except ValueError as val_err:
            return {
                "success": False,
                "message": str(val_err),
            }

        url = f"{_GITBOOK_API_BASE}/spaces/{clean_id}"

        try:
            with httpx.Client(timeout=10.0) as client:
                response = client.get(url, headers=headers)

                if response.status_code == 200:
                    data = response.json()
                    title = data.get("title") or data.get("name") or clean_id
                    return {
                        "success": True,
                        "space_id": clean_id,
                        "space_title": title,
                        "message": f"Successfully connected to GitBook Space: '{title}'",
                    }
                elif response.status_code in (401, 403):
                    return {
                        "success": False,
                        "message": f"Authentication failed (HTTP {response.status_code}). Please verify your GitBook Developer API Token.",
                    }
                elif response.status_code == 404:
                    return {
                        "success": False,
                        "message": f"GitBook Space '{clean_id}' not found (HTTP 404). Verify your Space ID.",
                    }
                else:
                    return {
                        "success": False,
                        "message": f"GitBook API returned error {response.status_code}: {response.text[:200]}",
                    }

        except Exception as exc:
            logger.warning("GitBook test_connection exception: %s", exc)
            return {
                "success": False,
                "message": f"Connection error: {str(exc)}",
            }

    def publish_document(
        self,
        space_id: str,
        filename: str,
        content: str,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Publish a single Markdown document's raw content to a GitBook Space.

        GitBook's Content Import API only supports importing from a publicly
        reachable URL (see ``publish_document_from_url``); there is no
        endpoint that accepts inline Markdown content directly. This method
        validates the request and reports that limitation instead of
        attempting an unsupported call.

        Args:
            space_id: GitBook Space ID (or full space URL).
            filename: Filename for logging/reporting purposes.
            content: Markdown content string (validated but not sent inline).
            token: Optional API token override.

        Returns:
            dict: Result details including status and message.
        """
        clean_id = self._clean_space_id(space_id)
        if not clean_id:
            return {"success": False, "message": "GitBook Space ID is required."}

        try:
            self._get_headers(token)
        except ValueError as val_err:
            return {"success": False, "message": str(val_err)}

        logger.warning(
            "publish_document called for %s — GitBook's API only supports "
            "URL-based content import; use publish_repository_docs (which "
            "serves files via a public URL) instead.",
            filename,
        )
        return {
            "success": False,
            "filename": filename,
            "message": (
                "Direct content publish is not supported by GitBook's API. "
                "Use 'Publish Repository' instead, which imports documents "
                "via a publicly reachable URL."
            ),
        }

    def publish_document_from_url(
        self,
        space_id: str,
        org_id: str,
        filename: str,
        file_url: str,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Publish a Markdown document to a GitBook Space by having GitBook import
        it from a publicly-accessible URL.

        GitBook API (from official OpenAPI spec):
          POST /org/{organizationId}/imports

        Body (ContentImportSource type="website" + ContentImportTarget):
          {
            "source": {"type": "website", "url": "<public URL>"},
            "target": {"space": "<spaceId>"},
            "enhance": false
          }

        The source URL must be publicly accessible (e.g. via ngrok).

        Args:
            space_id: GitBook Space ID (clean, not full URL).
            org_id: GitBook Organization ID (from the /o/... segment of the URL).
            filename: Filename for logging/reporting purposes.
            file_url: Fully-qualified public URL to the raw markdown file.
            token: Optional API token override.

        Returns:
            dict: Result details including status and message.
        """
        headers = self._get_headers(token)

        # Correct endpoint from GitBook's own OpenAPI spec
        url = f"{_GITBOOK_API_BASE}/org/{org_id}/imports"

        payload = {
            "source": {
                "type": "website",
                "url": file_url,
            },
            "target": {
                "space": space_id,
            },
            "enhance": False,  # Skip AI enhancement to keep content as-is
        }

        try:
            with httpx.Client(timeout=60.0) as client:
                response = client.post(url, headers=headers, json=payload)

                if response.status_code in (200, 201, 202):
                    return {
                        "success": True,
                        "filename": filename,
                        "message": f"Successfully queued {filename} for import into GitBook Space.",
                    }
                else:
                    error_detail = ""
                    try:
                        resp_json = response.json()
                        error_detail = (
                            resp_json.get("error", {}).get("message")
                            or resp_json.get("message")
                            or response.text[:400]
                        )
                    except Exception:
                        error_detail = response.text[:400]

                    logger.warning(
                        "GitBook import HTTP %s for %s (url=%s): %s",
                        response.status_code,
                        filename,
                        file_url,
                        error_detail,
                    )
                    return {
                        "success": False,
                        "filename": filename,
                        "message": (
                            f"GitBook API returned {response.status_code} for {filename}: {error_detail}"
                        ),
                    }

        except Exception as exc:
            logger.warning("GitBook import failed for %s: %s", filename, exc)
            return {
                "success": False,
                "filename": filename,
                "message": f"Failed importing {filename}: {str(exc)}",
            }

    STANDARD_DOC_FILES = [
        "README.md", "ARCHITECTURE.md", "REQUIREMENTS.md", "WORKFLOW.md",
        "CHANGELOG.md", "SECURITY.md", "REPORTS.md"
    ]

    def publish_documents(
        self,
        repo_name: str,
        space_id: str,
        public_base_url: str,
        filenames: List[str],
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Publish a chosen set of generated documentation files for a repository
        to GitBook by having GitBook import each file from a public URL.

        Unlike ``publish_repository_docs`` (which always publishes the fixed
        standard suite), this accepts any file path under the repo's
        generated_docs/<repo_slug>/ folder — including per-file, on-demand
        docs written by FileDocumentationService, which live at nested paths
        mirroring their source file (e.g. ``app/api/webhook.py.md``) — so the
        frontend can let the user pick exactly which documents to publish.

        Uses GitBook OpenAPI-spec endpoint:
          POST /org/{organizationId}/imports

        The org ID and space ID are both extracted from the full GitBook URL
        (e.g. https://app.gitbook.com/o/ORG_ID/s/SPACE_ID/).

        Args:
            repo_name: Full repository name (e.g. 'owner/repo').
            space_id: GitBook Space ID or full GitBook URL (org + space extracted automatically).
            public_base_url: Publicly-reachable base URL of this backend,
                e.g. ``https://abc123.ngrok-free.app`` (no trailing slash).
            filenames: Paths relative to generated_docs/<repo_slug>/ to publish,
                e.g. ``["README.md", "app/api/webhook.py.md"]``.
            token: Optional API token override.

        Returns:
            dict: Summary of published documents and status.
        """
        # Extract both IDs from the full URL if provided
        clean_space_id = self._clean_space_id(space_id)
        org_id = self._extract_org_id(space_id)

        if not clean_space_id:
            return {
                "success": False,
                "message": "Could not determine GitBook Space ID.",
                "published_count": 0,
            }

        if not org_id:
            return {
                "success": False,
                "message": (
                    "Could not determine GitBook Organization ID. "
                    "Please paste the full GitBook space URL "
                    "(e.g. https://app.gitbook.com/o/ORG_ID/s/SPACE_ID/) "
                    "into the Space ID field."
                ),
                "published_count": 0,
            }

        if not public_base_url:
            return {
                "success": False,
                "message": "A public base URL (e.g. your ngrok URL) is required so GitBook can fetch the files.",
                "published_count": 0,
            }

        if not filenames:
            return {
                "success": False,
                "message": "No documents were selected to publish.",
                "published_count": 0,
            }

        repo_slug = repo_name.replace("/", "_")
        repo_out_dir = (_OUTPUT_ROOT / repo_slug).resolve()

        if not repo_out_dir.exists():
            return {
                "success": False,
                "message": f"No generated documentation folder found for '{repo_name}'. Please generate documentation first.",
                "published_count": 0,
            }

        published_results: List[Dict[str, Any]] = []

        for raw_filename in filenames:
            filename = raw_filename.replace("\\", "/").lstrip("/")
            file_path = (repo_out_dir / filename).resolve()

            if repo_out_dir not in file_path.parents or not file_path.is_file():
                published_results.append({
                    "success": False,
                    "filename": filename,
                    "message": "File not found on disk — generate documentation first.",
                })
                continue

            file_url = f"{public_base_url}/api/documents/serve/{repo_slug}/{filename}"
            logger.info("Publishing %s via URL import: %s", filename, file_url)
            result = self.publish_document_from_url(
                space_id=clean_space_id,
                org_id=org_id,
                filename=filename,
                file_url=file_url,
                token=token,
            )
            published_results.append(result)

        success_count = sum(1 for r in published_results if r.get("success"))

        return {
            "success": success_count > 0,
            "repository": repo_name,
            "space_id": clean_space_id,
            "published_count": success_count,
            "total_files": len(filenames),
            "results": published_results,
            "message": f"Published {success_count}/{len(filenames)} selected documentation file(s) to GitBook Space '{clean_space_id}'.",
        }

    def publish_repository_docs(
        self,
        repo_name: str,
        space_id: str,
        public_base_url: str,
        token: Optional[str] = None,
    ) -> Dict[str, Any]:
        """Publish the fixed standard documentation suite (README, ARCHITECTURE,
        WORKFLOW, CHANGELOG, SECURITY, REPORTS) — kept for backward compatibility
        with callers that don't pass an explicit file selection."""
        return self.publish_documents(
            repo_name=repo_name,
            space_id=space_id,
            public_base_url=public_base_url,
            filenames=self.STANDARD_DOC_FILES,
            token=token,
        )

