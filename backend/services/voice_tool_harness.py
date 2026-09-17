"""
services/voice_tool_harness.py
--------------------------------
The approval-gate state machine for the voice assistant's document-editing
tools.

This is the one place that decides whether a proposed documentation change
is allowed to be written to disk. The rule is architectural, not a prompt
convention: `apply_document_change` only succeeds if a matching
`approve_proposal()` call already happened -- and that method is only ever
invoked by the WebSocket route in direct response to an explicit UI button
click from the human, never by anything the model says. A spoken or typed
"yes, apply it" can make the model *attempt* the tool call, but the harness
rejects it with `not_yet_approved` until the click arrives.

One harness instance is created per WebSocket connection (per voice
session), scoped to exactly one already-open document.
"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Optional

from google.genai import types

from services.document_store_service import backup_and_write

logger = logging.getLogger(__name__)


@dataclass
class Proposal:
    """One drafted-but-not-yet-applied documentation change."""

    id: str
    summary: str
    rationale: str
    new_content: str
    previous_content: str  # the doc's content at propose-time, for the diff view


@dataclass
class ToolEvent:
    """One thing the harness wants the WS route to push down to the browser,
    independent of the tool's return value to Gemini (which continues the
    model's turn; this is what the human sees)."""

    type: str
    payload: dict[str, Any] = field(default_factory=dict)


# Tool schemas for Gemini's function-calling config (LiveConnectConfig.tools).
# Neither tool accepts a file path or document id -- the harness binds
# `document_path` from the WebSocket's own connect params, not from anything
# the model provides, so there is no channel for the model to name a
# different file than the one currently open in the viewer.
PROPOSE_DOCUMENT_CHANGE = types.FunctionDeclaration(
    name="propose_document_change",
    description=(
        "Propose a change to the single documentation file currently open "
        "in the viewer. Does NOT write to disk. Always call this before "
        "apply_document_change, and wait for the human to click Approve in "
        "the UI before ever calling apply_document_change."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "summary": {
                "type": "string",
                "description": "One-sentence human-readable summary of the change.",
            },
            "rationale": {
                "type": "string",
                "description": "Why this addresses the user's request.",
            },
            "new_content": {
                "type": "string",
                "description": "Full new Markdown content of the document (a complete replacement, not a diff).",
            },
        },
        "required": ["summary", "new_content"],
    },
)

APPLY_DOCUMENT_CHANGE = types.FunctionDeclaration(
    name="apply_document_change",
    description=(
        "Write a previously proposed change to disk. Only call this after "
        "the human has clicked Approve in the UI for this exact proposal_id. "
        "A spoken or typed 'yes' / 'apply it' is NOT sufficient -- if the "
        "human has only said so, tell them to click Approve instead. "
        "Calling before approval returns an error."
    ),
    parameters_json_schema={
        "type": "object",
        "properties": {
            "proposal_id": {
                "type": "string",
                "description": "The proposal_id returned by the prior propose_document_change call.",
            },
        },
        "required": ["proposal_id"],
    },
)

TOOLS = [types.Tool(function_declarations=[PROPOSE_DOCUMENT_CHANGE, APPLY_DOCUMENT_CHANGE])]


class VoiceToolHarness:
    """Owns the propose/approve/apply state for one voice session."""

    def __init__(self, document_path: Path) -> None:
        self._document_path = document_path
        self._pending: Optional[Proposal] = None
        self._approved: set[str] = set()

    # ------------------------------------------------------------------
    # Called by voice_session_service when Gemini emits a tool_call
    # ------------------------------------------------------------------

    def execute(self, name: str, args: dict[str, Any]) -> tuple[dict[str, Any], list[ToolEvent]]:
        """Run a tool the model called.

        Returns:
            (result, events): `result` is sent back to Gemini via
            send_tool_response; `events` are pushed down to the browser over
            the WebSocket so the UI can render the proposal/outcome.
        """
        if name == "propose_document_change":
            return self._propose(args)
        if name == "apply_document_change":
            return self._apply(args)
        return {"error": f"Unknown tool: {name}"}, []

    def _propose(self, args: dict[str, Any]) -> tuple[dict[str, Any], list[ToolEvent]]:
        summary = str(args.get("summary", "")).strip()
        rationale = str(args.get("rationale", "")).strip()
        new_content = args.get("new_content")

        if not summary or not new_content:
            return {"error": "summary and new_content are required"}, []

        try:
            current_content = self._document_path.read_text(encoding="utf-8")
        except OSError as exc:
            logger.error("voice_tool_harness: could not read %s: %s", self._document_path, exc)
            return {"error": "could_not_read_document"}, []

        # Only one pending proposal at a time -- a new one replaces any
        # earlier unapplied proposal, and the UI is told the old one is dead
        # so it doesn't show a stale Approve button.
        events: list[ToolEvent] = []
        if self._pending is not None:
            events.append(ToolEvent("proposal_rejected", {"proposal_id": self._pending.id}))
            self._approved.discard(self._pending.id)

        proposal = Proposal(
            id=uuid.uuid4().hex,
            summary=summary,
            rationale=rationale,
            new_content=new_content,
            previous_content=current_content,
        )
        self._pending = proposal
        logger.info("voice_tool_harness: proposed change %s for %s: %s", proposal.id, self._document_path, summary)

        events.append(ToolEvent("proposal", {
            "proposal_id": proposal.id,
            "summary": proposal.summary,
            "rationale": proposal.rationale,
            "diff": {"before": proposal.previous_content, "after": proposal.new_content},
        }))

        return {"status": "awaiting_human_approval", "proposal_id": proposal.id}, events

    def _apply(self, args: dict[str, Any]) -> tuple[dict[str, Any], list[ToolEvent]]:
        proposal_id = str(args.get("proposal_id", ""))

        if self._pending is None or self._pending.id != proposal_id:
            return {"error": "unknown_or_stale_proposal_id"}, []

        if proposal_id not in self._approved:
            logger.info("voice_tool_harness: apply attempt for %s rejected -- not yet approved", proposal_id)
            return {
                "error": "not_yet_approved",
                "message": "The human has not clicked Approve for this proposal yet. Do not assume verbal confirmation is enough -- ask them to click Approve in the UI.",
            }, []

        proposal = self._pending
        try:
            backup_and_write(self._document_path, proposal.new_content)
        except OSError as exc:
            logger.error("voice_tool_harness: write failed for %s: %s", self._document_path, exc)
            return {"error": "write_failed", "message": str(exc)}, []

        logger.info("voice_tool_harness: applied change %s to %s", proposal.id, self._document_path)
        self._pending = None
        self._approved.discard(proposal_id)

        event = ToolEvent("proposal_applied", {
            "proposal_id": proposal.id,
            "new_content": proposal.new_content,
            "previous_content": proposal.previous_content,
        })
        return {"status": "applied"}, [event]

    # ------------------------------------------------------------------
    # Called by the WS route directly when the human clicks a button --
    # never reachable from model output.
    # ------------------------------------------------------------------

    def approve_proposal(self, proposal_id: str) -> bool:
        """Mark a proposal as human-approved. Returns False if it's not the
        current pending proposal (e.g. stale UI state after a new proposal
        replaced it)."""
        if self._pending is None or self._pending.id != proposal_id:
            return False
        self._approved.add(proposal_id)
        return True

    def reject_proposal(self, proposal_id: str) -> bool:
        """Discard a pending proposal the human declined."""
        if self._pending is None or self._pending.id != proposal_id:
            return False
        self._pending = None
        self._approved.discard(proposal_id)
        return True
