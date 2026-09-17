"""
app/api/voice_chat.py
------------------------
WebSocket endpoint for the documentation chatbot's voice assistant.

WS /api/voice-chat?document_id=...&repository_name=...

Opens one Gemini Live session (via VoiceSessionService) scoped to exactly
the one document named by `document_id`, and relays browser <-> Gemini
messages for the life of the connection. See the WebSocket protocol section
of the voice-assistant plan for the exact client/server message shapes.

No business logic here beyond connection setup/teardown and the JSON<->dict
boundary -- delegates entirely to VoiceSessionService / VoiceToolHarness.
"""

import logging
import os
from typing import Any, AsyncIterator

from fastapi import APIRouter, WebSocket, WebSocketDisconnect

from app.core.config import settings
from services.document_store_service import DocumentNotFoundError, resolve_document_path
from services.voice_session_service import VoiceSessionService

logger = logging.getLogger(__name__)

router = APIRouter()

# WebSocket close codes (private-use range 4000-4999, per RFC 6455 sec 7.4.2)
_CLOSE_DOCUMENT_NOT_FOUND = 4404
_CLOSE_MISSING_API_KEY = 4500
_CLOSE_SESSION_ERROR = 4500


async def _receive_json_stream(websocket: WebSocket) -> AsyncIterator[dict[str, Any]]:
    """Yield JSON messages from the client until it disconnects."""
    while True:
        try:
            yield await websocket.receive_json()
        except WebSocketDisconnect:
            return


@router.websocket("")
async def voice_chat(websocket: WebSocket) -> None:
    document_id = websocket.query_params.get("document_id", "")
    repository_name = websocket.query_params.get("repository_name", "")

    if not document_id:
        await websocket.close(code=_CLOSE_DOCUMENT_NOT_FOUND, reason="document_id is required")
        return
    if not repository_name:
        await websocket.close(code=_CLOSE_DOCUMENT_NOT_FOUND, reason="repository_name is required")
        return

    root = settings.generated_docs_path_dir.resolve()
    try:
        document_path = resolve_document_path(root, document_id)
    except DocumentNotFoundError:
        await websocket.close(code=_CLOSE_DOCUMENT_NOT_FOUND, reason="Document not found")
        return

    if not os.getenv("GEMINI_API_KEY", "").strip():
        await websocket.close(
            code=_CLOSE_MISSING_API_KEY,
            reason="Voice assistant is not configured (GEMINI_API_KEY missing).",
        )
        return

    try:
        document_content = document_path.read_text(encoding="utf-8")
    except OSError as exc:
        logger.error("voice_chat: could not read %s: %s", document_path, exc)
        await websocket.close(code=_CLOSE_DOCUMENT_NOT_FOUND, reason="Could not read document")
        return

    await websocket.accept()
    logger.info(
        "voice_chat: session starting for repo=%s document=%s",
        repository_name, document_path,
    )

    async def on_event(event: dict[str, Any]) -> None:
        await websocket.send_json(event)

    service = VoiceSessionService(repository_name, document_path, document_content, on_event)
    try:
        await service.run(_receive_json_stream(websocket))
    except Exception as exc:
        logger.exception("voice_chat: session error for %s", document_path)
        try:
            await websocket.send_json({"type": "error", "message": f"Voice session failed: {exc}"})
        except Exception:
            pass
        try:
            await websocket.close(code=_CLOSE_SESSION_ERROR, reason="Voice session failed")
        except Exception:
            pass
        return

    logger.info("voice_chat: session ended for %s", document_path)
    try:
        await websocket.close(code=1000, reason="Session ended")
    except Exception:
        pass
