"""
services/voice_session_service.py
------------------------------------
Owns one Gemini Live API session for the lifetime of one WebSocket
connection from the AgentSidebar. Relays browser <-> Gemini in both
directions and dispatches tool calls to VoiceToolHarness.

Not a FastAPI dependency / singleton -- a fresh instance is constructed per
WebSocket connection by app/api/voice_chat.py, since a Live session is
inherently stateful and scoped to one conversation about one open document.
"""

from __future__ import annotations

import asyncio
import base64
import logging
import os
from pathlib import Path
from typing import Any, AsyncIterator, Awaitable, Callable

from google import genai
from google.genai import types

from services.doc_context_service import load_generated_docs, retrieve_code_context
from services.voice_tool_harness import TOOLS, VoiceToolHarness

logger = logging.getLogger(__name__)

_MODEL = "gemini-3.8-live"

EventSink = Callable[[dict[str, Any]], Awaitable[None]]


def _system_instruction(
    document_name: str,
    document_content: str,
    doc_context: str,
    code_context: str,
) -> str:
    doc_context_block = doc_context or "(No other generated documentation available for this repository.)"
    code_context_block = code_context or "(No indexed source code context available.)"

    return f"""You are a documentation assistant embedded in a technical writing tool.

You have READ access to this repository's generated documentation (below) --
answer questions about ANY of these files, not just the one currently open,
e.g. "what changed in CHANGELOG.md" or "what does ARCHITECTURE.md say about
the RAG pipeline" should be answered directly from this context, not refused.

=== OTHER GENERATED DOCUMENTATION FOR THIS REPOSITORY ===
{doc_context_block}
=== END OTHER GENERATED DOCUMENTATION ===

=== RELEVANT SOURCE CODE CONTEXT ===
{code_context_block}
=== END SOURCE CODE CONTEXT ===

The user is currently viewing exactly one document open in the editor:
`{document_name}`. Its current, authoritative content is reproduced below
(this may duplicate or be newer than the same file if it also appears
above -- prefer this version for anything about the open document itself).

--- OPEN DOCUMENT CONTENT START ---
{document_content}
--- OPEN DOCUMENT CONTENT END ---

EDITING RULES (these apply only to writing changes, never to answering
questions -- you may discuss any file above freely):

You may only ever PROPOSE OR APPLY EDITS to `{document_name}`, the one
document open in the editor. You have no ability to edit any other file --
if asked to change a different file, explain that you can only edit the
document currently open, but you can still discuss or summarize that other
file's content from the context above.

If the user asks you to change the open document, follow this exact
protocol and do not deviate:

1. Call propose_document_change with a one-sentence summary, a short
   rationale, and the FULL new document content (a complete replacement,
   not a diff or partial excerpt).
2. Tell the user you've drafted the change and that they need to review it
   and click Approve in the interface before it's written anywhere -- you
   cannot apply it yourself just because they said "yes" or "do it" out loud
   or in text. That is not sufficient approval.
3. Only call apply_document_change after you have been told (via a system
   note in this conversation, or via a successful tool result) that the
   human approved it. If you call it too early you will get a
   "not_yet_approved" error -- if that happens, tell the user you're still
   waiting for them to click Approve, and do not retry until they do.
4. Never tell the user a change was saved or applied unless
   apply_document_change actually returned a success status.
"""


class VoiceSessionService:
    """Bidirectional relay between one WebSocket connection and one Gemini
    Live session, with tool calls routed through a VoiceToolHarness."""

    def __init__(
        self,
        repository_name: str,
        document_path: Path,
        document_content: str,
        on_event: EventSink,
    ) -> None:
        self._repository_name = repository_name
        self._document_path = document_path
        self._document_content = document_content
        self._on_event = on_event
        self._harness = VoiceToolHarness(document_path)
        api_key = os.getenv("GEMINI_API_KEY", "")
        self._client = genai.Client(api_key=api_key)
        self._session: Any = None  # google.genai.live.AsyncSession, set once connected

    async def run(self, incoming: AsyncIterator[dict[str, Any]]) -> None:
        """Open the Live session and relay until `incoming` ends or the
        session itself closes (browser disconnect either way tears this
        down cleanly via the `async with` context manager)."""
        # Read access spans the whole repository's generated docs (matching
        # the plain-text chatbot's grounding) -- only the *edit* tools below
        # are scoped to the one open document.
        #
        # Both calls do blocking I/O (disk reads; retrieve_code_context also
        # makes a synchronous network call to the RAG backend). Run them in
        # a thread so they don't stall the asyncio event loop that FastAPI
        # uses to service every other connection (including other voice
        # sessions and new WebSocket handshakes) for however long they take.
        doc_context, _doc_sources = await asyncio.to_thread(load_generated_docs, self._repository_name)
        code_context = await asyncio.to_thread(
            retrieve_code_context,
            self._repository_name,
            f"Overview and implementation details relevant to {self._document_path.name}",
        )

        config = types.LiveConnectConfig(
            response_modalities=["AUDIO"],
            system_instruction=_system_instruction(
                self._document_path.name, self._document_content, doc_context, code_context
            ),
            tools=TOOLS,
            input_audio_transcription=types.AudioTranscriptionConfig(),
            output_audio_transcription=types.AudioTranscriptionConfig(),
            # The browser already tells us exactly when the user is
            # recording via explicit activity_start/activity_end signals
            # (sent from audio_start/audio_end -- see _pump_incoming below),
            # driven by the mic button being clicked. Without this, Gemini's
            # own automatic voice-activity detection runs in parallel and
            # can keep a turn "listening" past our explicit end signal (or
            # start one on its own), which is what made the assistant seem
            # to keep listening after a reply instead of waiting for the
            # next deliberate mic click.
            realtime_input_config=types.RealtimeInputConfig(
                automatic_activity_detection=types.AutomaticActivityDetection(disabled=True)
            ),
        )

        async with self._client.aio.live.connect(model=_MODEL, config=config) as session:
            self._session = session
            await self._on_event({"type": "ready"})

            sender = asyncio.create_task(self._pump_incoming(incoming))
            receiver = asyncio.create_task(self._pump_gemini())
            done, pending = await asyncio.wait(
                {sender, receiver}, return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            for task in done:
                exc = task.exception()
                if exc:
                    raise exc

    # ------------------------------------------------------------------
    # Browser -> Gemini
    # ------------------------------------------------------------------

    async def _pump_incoming(self, incoming: AsyncIterator[dict[str, Any]]) -> None:
        async for msg in incoming:
            mtype = msg.get("type")

            if mtype == "user_text":
                text = str(msg.get("text", "")).strip()
                if text:
                    await self._session.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part(text=text)])
                    )

            elif mtype == "audio_start":
                await self._session.send_realtime_input(activity_start=types.ActivityStart())

            elif mtype == "audio_chunk":
                data = base64.b64decode(msg.get("data", ""))
                await self._session.send_realtime_input(
                    audio=types.Blob(data=data, mime_type="audio/pcm;rate=16000")
                )

            elif mtype == "audio_end":
                await self._session.send_realtime_input(activity_end=types.ActivityEnd())

            elif mtype == "approve_proposal":
                proposal_id = str(msg.get("proposal_id", ""))
                if self._harness.approve_proposal(proposal_id):
                    # Nudge the model immediately rather than waiting for it
                    # to spontaneously retry apply_document_change.
                    await self._session.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part(
                            text=f"[UI event] The human clicked Approve for proposal_id={proposal_id}. "
                                 f"You may now call apply_document_change with this proposal_id."
                        )])
                    )
                else:
                    await self._on_event({
                        "type": "error",
                        "message": "That proposal is no longer active.",
                    })

            elif mtype == "reject_proposal":
                proposal_id = str(msg.get("proposal_id", ""))
                if self._harness.reject_proposal(proposal_id):
                    await self._on_event({"type": "proposal_rejected", "proposal_id": proposal_id})
                    feedback = str(msg.get("feedback", "")).strip()
                    note = f"[UI event] The human rejected proposal_id={proposal_id}."
                    if feedback:
                        note += f" Their feedback: {feedback}"
                    else:
                        note += " Ask what they'd like changed instead."
                    await self._session.send_client_content(
                        turns=types.Content(role="user", parts=[types.Part(text=note)])
                    )

            elif mtype == "end_session":
                return

    # ------------------------------------------------------------------
    # Gemini -> Browser
    # ------------------------------------------------------------------

    async def _pump_gemini(self) -> None:
        # session.receive() yields messages for exactly one model turn and
        # then its async generator ends by design (per the SDK's own
        # docstring) -- it must be re-invoked for every subsequent turn, or
        # the relay would silently stop after the first response.
        while True:
            async for message in self._session.receive():
                if message.go_away:
                    logger.warning("voice_session: Gemini sent go_away: %s", message.go_away)
                await self._handle_server_message(message)

    async def _handle_server_message(self, message: types.LiveServerMessage) -> None:
        content = message.server_content
        if content:
            if content.input_transcription and content.input_transcription.text:
                await self._on_event({
                    "type": "partial_transcript",
                    "role": "user",
                    "text": content.input_transcription.text,
                })
            if content.output_transcription and content.output_transcription.text:
                await self._on_event({
                    "type": "assistant_text_delta",
                    "text": content.output_transcription.text,
                })
            if content.model_turn and content.model_turn.parts:
                for part in content.model_turn.parts:
                    if part.inline_data and part.inline_data.data:
                        encoded = base64.b64encode(part.inline_data.data).decode("ascii")
                        await self._on_event({"type": "assistant_audio_chunk", "data": encoded})
                    elif part.text:
                        await self._on_event({"type": "assistant_text_delta", "text": part.text})
            if content.turn_complete:
                await self._on_event({"type": "assistant_turn_complete"})

        if message.tool_call and message.tool_call.function_calls:
            responses = []
            for call in message.tool_call.function_calls:
                result, events = self._harness.execute(call.name or "", call.args or {})
                for ev in events:
                    await self._on_event({"type": ev.type, **ev.payload})
                responses.append(types.FunctionResponse(id=call.id, name=call.name, response=result))
            await self._session.send_tool_response(function_responses=responses)
