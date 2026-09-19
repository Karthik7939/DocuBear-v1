"""
app/api/webhook.py
-------------------
GitHub webhook receive endpoint.

Responsibilities:
- Accept POST /webhook/github
- Validate the X-GitHub-Event header (only 'push' is supported)
- Validate the X-Hub-Signature-256 header when a secret is configured
- Parse and validate the request body using the WebhookPayload model
- Acknowledge GitHub immediately (HTTP 202) to avoid the 10-second timeout
- Delegate all heavy processing to GitHubService in a background thread

No Git logic. No parsing logic. No filesystem logic.
"""

import asyncio
import logging
from concurrent.futures import ThreadPoolExecutor

from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from fastapi.responses import JSONResponse

from app.core.constants import (
    HEADER_GITHUB_EVENT,
    HEADER_GITHUB_SIGNATURE,
    SUPPORTED_GITHUB_EVENTS,
    GitHubEvent,
    ResponseMessage,
)
from app.dependencies import get_github_service
from app.models.webhook import WebhookPayload
from services.github_service import GitHubService
from utils.helpers import build_error_response, build_success_response

logger = logging.getLogger(__name__)

router = APIRouter()

# Thread pool used to run the blocking agentic pipeline off the event loop.
# Two workers allow concurrent processing for different repos.
_pipeline_executor = ThreadPoolExecutor(max_workers=2, thread_name_prefix="pipeline")


def _run_pipeline(github_service: GitHubService, payload: WebhookPayload) -> None:
    """Execute the full push-event pipeline in a worker thread.

    Errors are caught and logged here so the background task never raises
    an unhandled exception into the event loop.

    Args:
        github_service: Service that orchestrates clone, parse, and doc generation.
        payload:        Validated webhook payload.
    """
    try:
        result = github_service.process_push_event(payload)
        logger.info(
            "Pipeline completed in background: workflow_id=%s  repo=%s  branch=%s",
            result.workflow_id,
            result.repository,
            result.branch,
        )
    except Exception as exc:
        logger.error(
            "Background pipeline failed for repo=%s branch=%s: %s",
            payload.repository.full_name,
            payload.branch,
            exc,
            exc_info=True,
        )


@router.post(
    "/webhook/github",
    status_code=status.HTTP_202_ACCEPTED,
    summary="Receive GitHub Push Webhook",
    description=(
        "Accepts a GitHub push event, validates it, then immediately returns 202 Accepted. "
        "The repository sync and documentation generation run asynchronously in the background."
    ),
    tags=["Webhook"],
)
@router.post(
    "/",
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
@router.post(
    "/api/webhook/github",
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
@router.post(
    "/api/v1/webhook/github",
    status_code=status.HTTP_202_ACCEPTED,
    include_in_schema=False,
)
async def receive_github_webhook(
    request: Request,
    x_github_event: str = Header(..., alias="x-github-event"),
    x_hub_signature_256: str = Header("", alias="x-hub-signature-256"),
    github_service: GitHubService = Depends(get_github_service),
) -> JSONResponse:
    """Handle an incoming GitHub push webhook.

    Validates the request synchronously (fast), then offloads the agentic
    pipeline to a background thread and returns 202 Accepted immediately.
    This prevents GitHub from timing out while the LLM-based pipeline runs.

    Args:
        request:               The raw FastAPI Request object (used to read raw body bytes).
        x_github_event:        Value of the ``X-GitHub-Event`` header.
        x_hub_signature_256:   Value of the ``X-Hub-Signature-256`` header.
        github_service:        Injected GitHubService orchestrator.

    Returns:
        JSONResponse 202: Accepted — pipeline running in background.

    Raises:
        HTTPException 400: If the event type is not supported or the signature is invalid.
        HTTPException 422: If the payload fails Pydantic validation.
    """
    logger.info("Webhook received: event=%s", x_github_event)

    # ------------------------------------------------------------------ #
    # 1. Validate event type
    # ------------------------------------------------------------------ #
    if x_github_event not in SUPPORTED_GITHUB_EVENTS:
        logger.warning("Unsupported GitHub event: %s", x_github_event)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=build_error_response(ResponseMessage.UNSUPPORTED_EVENT),
        )

    # ------------------------------------------------------------------ #
    # 2. Read raw body (needed for signature verification)
    # ------------------------------------------------------------------ #
    raw_body: bytes = await request.body()

    # ------------------------------------------------------------------ #
    # 3. Validate webhook signature
    # ------------------------------------------------------------------ #
    if not github_service.verify_signature(raw_body, x_hub_signature_256):
        logger.warning("Invalid webhook signature — request rejected")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=build_error_response(ResponseMessage.INVALID_SIGNATURE),
        )

    # ------------------------------------------------------------------ #
    # 4. Handle GitHub ping event
    # ------------------------------------------------------------------ #
    if x_github_event == GitHubEvent.PING or x_github_event == "ping":
        logger.info("GitHub ping event received — returning 200 Pong")
        return JSONResponse(
            status_code=status.HTTP_200_OK,
            content={"status": "ok", "message": "Pong! Webhook connected successfully"},
        )

    # ------------------------------------------------------------------ #
    # 5. Parse and validate the payload
    # ------------------------------------------------------------------ #
    try:
        payload = WebhookPayload.model_validate_json(raw_body)
    except Exception as exc:
        logger.error("Payload validation failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=build_error_response(ResponseMessage.INVALID_PAYLOAD),
        ) from exc

    logger.info(
        "Payload validated: repo=%s  branch=%s",
        payload.repository.full_name,
        payload.branch,
    )

    # ------------------------------------------------------------------ #
    # 5. Fire-and-forget — run the blocking pipeline in a thread pool.
    #    GitHub receives 202 immediately (well within the 10-second limit).
    # ------------------------------------------------------------------ #
    loop = asyncio.get_running_loop()
    loop.run_in_executor(_pipeline_executor, _run_pipeline, github_service, payload)

    logger.info(
        "Webhook acknowledged — pipeline dispatched to background: repo=%s  branch=%s",
        payload.repository.full_name,
        payload.branch,
    )

    # ------------------------------------------------------------------ #
    # 6. Return 202 immediately — GitHub sees success, no timeout
    # ------------------------------------------------------------------ #
    return JSONResponse(
        status_code=status.HTTP_202_ACCEPTED,
        content=build_success_response(
            {
                "message": "Webhook accepted — documentation pipeline running in background",
                "repository": payload.repository.full_name,
                "branch": payload.branch,
            }
        ),
    )
