# Documentation Chatbot & Voice Assistant

> This document explains how DocuBear's documentation chatbot and voice
> assistant work — architecture, the WebSocket protocol, the human-approval
> gate for edits, and the frontend pieces that make it feel like a single,
> persistent assistant. For the push-webhook documentation pipeline, see
> `backend/agent_explanation.md`; for the RAG engine, see
> `backend/rag/RAG_WALKTHROUGH.md`.

---

## 1. What it is

A single assistant, shown as a collapsible right-hand sidebar in the
frontend, that does two things:

1. **Answers questions** about a repository — grounded in its generated
   documentation (README, ARCHITECTURE, WORKFLOW, SECURITY, REPORTS,
   CHANGELOG) and RAG-retrieved source code context. Works from any page.
2. **Edits documentation on request** — when a document is open in the
   viewer, the assistant can draft a change to *that one document*, show the
   user a diff of exactly what it wants to change, and only write it to disk
   after the user explicitly clicks **Approve**. This mirrors how coding
   agents in IDEs (Cursor, Copilot) gate file writes behind a human click,
   not a model's own judgment of "the user seems to have agreed."

It also supports voice: hold the mic button to speak instead of typing, and
the same propose → approve → apply flow works identically whether the
request was typed or spoken.

The sidebar is mounted **once**, in the root layout (`frontend/app/layout.tsx`),
not inside individual pages — so it persists (open/closed state, chat
history, and its live connection) as the user navigates between pages,
rather than being torn down and rebuilt on every route change.

---

## 2. Two backends, one UI

| | Plain chat | Assistant session |
|---|---|---|
| Transport | `POST /api/chat` (JSON) | `WebSocket /api/voice-chat` |
| Backend | `ChatService` | `VoiceSessionService` + `VoiceToolHarness` |
| LLM | `gemini-3.5-flash-lite` via LangChain (`LLMService`) | `gemini-3.8-live` via the Gemini Live API (`google-genai` SDK) |
| Can edit documents? | No — read-only | Yes, scoped to the one open document |
| Voice in/out? | No | Yes (also handles typed text) |
| When used | No document is open (nothing to scope an edit to) | Automatically, as soon as a document is open and the sidebar is visible |

The assistant session is not an opt-in "voice mode" — it's the default,
tool-enabled backend for the sidebar whenever there's a document to edit.
Voice is a separate, optional layer on top of it (the mic button); typing
into the same session works the same way and gets the same edit
capability. The plain REST chat only remains as a fallback for the one case
where there's genuinely no document to scope an edit to (e.g. no file
selected yet on the File Docs page).

This two-tier design exists because early testing showed that gating edit
capability behind a separate "Start Assistant" click was confusing — people
would type a change request into what looked like one unified chat box and
get a hard "I can't edit files" refusal from the read-only backend. The fix
was to auto-connect the tool-enabled session as soon as there's a document
to scope edits to, so typing an edit request never silently falls back to
the read-only path.

---

## 3. Backend architecture

### `services/chat_service.py` — the plain-text chatbot

`ChatService.answer()` routes each question by regex-detected intent before
ever calling an LLM:

1. **`file_history`** ("who edited X", "when was X last changed") →
   `GitService.get_file_history()`. Deterministic, no LLM call.
2. **`file_content`** ("what's in X", "show me X") → raw file read from the
   cloned repository on disk. No LLM call.
3. **`general`** (everything else) → an LLM call grounded in
   `doc_context_service.load_generated_docs()` (all 6 standard docs) plus
   `doc_context_service.retrieve_code_context()` (top RAG-matched code
   chunks for the question).

No streaming, no tool-calling — one `POST /api/chat` request, one JSON
response (`app/api/chat.py`).

### `services/doc_context_service.py` — shared "what does the LLM know" loader

Extracted so both `ChatService` and `VoiceSessionService` are grounded in
the *same* repository-wide context, instead of drifting into two different
answers to "what's in CHANGELOG.md" depending on which one you ask.

```python
load_generated_docs(repository_name) -> (doc_context, sources)
retrieve_code_context(repository_name, query_text) -> code_context
```

`retrieve_code_context` calls the RAG `RetrievalPipeline` synchronously — it
does blocking network I/O (Pinecone/FAISS). `ChatService` calls it directly
(fine for a one-shot REST request); `VoiceSessionService` wraps the call in
`asyncio.to_thread(...)` since blocking the event loop inside a live
WebSocket session would stall every other connection FastAPI is serving —
see §7 for the incident this was caught by.

### `services/document_store_service.py` — the one safe-write path

```python
resolve_document_path(root, doc_id) -> Path       # decode + validate an opaque doc id
backup_and_write(doc_path, new_content) -> str     # backup current content to .prev.md, then overwrite
```

Both `app/api/documents.py`'s `revise_document` (the Documentation page's
"Request Changes" flow) and the voice assistant's `apply_document_change`
tool call `backup_and_write` — one sidecar-backup invariant, not two copies
that could drift apart. (`save_document`, the manual-edit textarea path, has
intentionally different conditional-backup semantics and is left alone.)

### `services/voice_session_service.py` — the Gemini Live session

One instance per WebSocket connection (not a shared singleton — a Live
session is inherently a stateful conversation about one specific document).
On connect:

```python
config = types.LiveConnectConfig(
    response_modalities=["AUDIO"],
    system_instruction=<repo docs + RAG context + the open document's content + editing rules>,
    tools=TOOLS,  # propose_document_change, apply_document_change
    input_audio_transcription=types.AudioTranscriptionConfig(),
    output_audio_transcription=types.AudioTranscriptionConfig(),
)
async with client.aio.live.connect(model="gemini-3.8-live", config=config) as session:
    ...
```

Two things worth knowing if you touch this file:

- **`session.receive()` yields messages for exactly one model turn and then
  its async generator ends** — it must be re-invoked (`while True: async for
  message in session.receive(): ...`) for every subsequent turn, or the
  relay silently stops responding after the first reply. This is easy to
  get wrong because the SDK's own docstring reads ambiguously.
- **Audio is always requested from Gemini for every turn**, whether the
  triggering input was typed or spoken — the Live API's `response_modalities`
  is a session-level setting, not per-turn. Whether a typed question still
  gets a *spoken* reply is decided client-side (see §5) — the frontend
  simply doesn't play back the audio chunks for turns that started as text.

The system instruction explicitly separates **read scope** (the whole
repository's docs + code context — "you may discuss any file above freely")
from **edit scope** (only the one document named in the WS connection's
`document_id` — "you have no ability to edit any other file"). Getting this
distinction right mattered: an earlier version of the prompt collapsed both
into "only talk about the open document," which made the assistant wrongly
refuse to answer questions about *other* generated docs like CHANGELOG.md
even when not asked to edit anything.

### `services/voice_tool_harness.py` — the approval gate

This is the part that makes "human approval before any write" an
architectural guarantee rather than a prompting convention.

```python
PROPOSE_DOCUMENT_CHANGE = types.FunctionDeclaration(name="propose_document_change", ...)
APPLY_DOCUMENT_CHANGE   = types.FunctionDeclaration(name="apply_document_change", ...)
```

Neither tool's schema accepts a file path or document id — `document_path`
is bound once, from the WebSocket's own connect params, so the model has no
parameter through which it could name a different file even if asked to.

- **`propose_document_change(summary, rationale, new_content)`** — stores the
  proposal (at most one pending at a time; a new proposal invalidates any
  earlier unapplied one), pushes a `proposal` event to the browser, and
  returns `{"status": "awaiting_human_approval", "proposal_id": ...}`
  immediately. It never blocks waiting for the human.
- **`apply_document_change(proposal_id)`** — checks an `approved: set[str]`
  that is populated **only** by `approve_proposal()`, which is called
  directly by the WebSocket route in response to an `approve_proposal`
  *client message* — i.e. an explicit UI button click, never by anything the
  model outputs. If the proposal isn't in that set, the tool returns
  `{"error": "not_yet_approved", ...}` and the model is told to ask the user
  to click Approve. Only once approved does it call
  `document_store_service.backup_and_write(...)`.

This was verified end-to-end against the real API: asking for a change, then
saying "yes, go ahead and apply it" in the same turn, correctly produces a
`not_yet_approved` rejection — a spoken or typed "yes" cannot substitute for
the click.

### `app/api/voice_chat.py` — the WebSocket route

`WS /api/voice-chat?document_id=...&repository_name=...`

On connect: resolves `document_id` to a real file under `generated_docs/`
(reusing `document_store_service`'s id scheme, so ids are interchangeable
with `/api/documents/*`), reads its content, checks `GEMINI_API_KEY` is
configured, then hands off to `VoiceSessionService.run()`. Closes with a
4xxx code and reason string on any of these failures rather than accepting
a connection it can't service.

---

## 4. WebSocket protocol

**Client → Server**

| Type | Fields | Meaning |
|---|---|---|
| `user_text` | `text` | A typed message |
| `audio_start` | — | Push-to-talk pressed; starts a manual-VAD activity window |
| `audio_chunk` | `data` (base64 PCM16 @16kHz) | One ~200ms chunk of mic audio |
| `audio_end` | — | Push-to-talk released |
| `approve_proposal` | `proposal_id` | The only thing that can unlock `apply_document_change` |
| `reject_proposal` | `proposal_id`, `feedback?` | Discards the pending proposal |
| `end_session` | — | Graceful client-initiated close |

**Server → Client**

| Type | Fields | Meaning |
|---|---|---|
| `ready` | — | Session established |
| `partial_transcript` | `role`, `text` | Live transcription of the user's speech |
| `assistant_text_delta` | `text` | Streamed reply text (always sent, both modalities) |
| `assistant_audio_chunk` | `data` (base64 PCM16 @24kHz) | Streamed reply audio (frontend decides whether to play it) |
| `assistant_turn_complete` | — | End of one model turn |
| `proposal` | `proposal_id`, `summary`, `rationale`, `diff.{before,after}` | A drafted change awaiting approval |
| `proposal_applied` | `proposal_id`, `new_content`, `previous_content` | The write succeeded |
| `proposal_rejected` | `proposal_id` | Discarded (explicitly, or superseded by a newer proposal) |
| `error` | `message` | Something went wrong; session usually continues |
| `closed` | `reason?` | Connection ending |

---

## 5. Frontend architecture

### `frontend/lib/agentContext.tsx` — making the sidebar persistent

The sidebar is a **single instance** rendered once in `app/layout.tsx`. Pages
don't render it themselves; instead they call a hook to tell it what's
currently open:

```tsx
useRegisterOpenDocument({
  repositoryName,
  documentId: doc.id,
  documentTitle: fileName,
  documentContent: doc.content,
  onDocumentChanged: handleAssistantChange,
});
```

`AgentProvider` holds `openDocument` (the currently registered doc) and
`sidebarCollapsed` (so both the sidebar and the page-content wrapper —
`AppContent.tsx` — can react to whether it's open, without the sidebar
needing to live inside the page tree it would otherwise be covering).
Registration is keyed so that a page's unmount cleanup can't clobber a
newly-navigated-to page's registration if effect ordering races during a
transition.

### `frontend/components/AgentSidebar.tsx` — the sidebar itself

Key behaviors, each addressing a specific issue found during manual testing:

- **Auto-connects** the WebSocket session as soon as `openDocument` has a
  `documentId` and the panel is visible — no separate "Start Assistant"
  click gates editing (see §2's rationale).
- **Re-scopes silently on doc switch**: a ref tracks
  `"{repositoryName}::{documentId}"` for whatever the session is currently
  connected to. When the registered open document changes, it ends the old
  connection and opens a new one scoped to the new document — without the
  sidebar panel itself unmounting, so its collapsed/expanded state and text
  history survive the switch. (Uses `clientRef.current`, a plain ref, as the
  synchronous "is there already a connection" guard — React state updates
  are batched/async and would otherwise race an end-then-immediately-restart
  in the same effect tick.)
- **Gates audio playback by input modality**: `lastInputModeRef` records
  whether the most recent user turn was typed (`"text"`) or spoken
  (`"voice"`). The backend always streams both text and audio for every
  turn (§3), but `assistant_audio_chunk` is only actually played back when
  the last input was voice — so a typed question gets a text-only reply,
  and a spoken one gets text + speech, matching normal chat-app expectations
  rather than every reply being read aloud regardless of how it was asked.
- **Push-to-talk** via mouse/touch down-hold on a mic button placed directly
  beside the text input (not in a separate toolbar) — holding it shows an
  animated three-dot "Listening..." indicator above the input.

### `frontend/lib/audioIO.ts` + `frontend/public/audio-capture-worklet.js`

- **`PcmAudioCapture`**: `getUserMedia` → `AudioContext` → an
  `AudioWorkletNode` (not the deprecated `ScriptProcessorNode`, not
  `MediaRecorder`, which only produces compressed Opus/WebM) running
  `audio-capture-worklet.js`. The worklet does linear-interpolation
  downsampling from the browser's native sample rate to 16-bit PCM16 mono
  @16kHz — exactly what `send_realtime_input` expects — and posts ~200ms
  chunks back to the main thread.
- **`PcmAudioPlayer`**: queues incoming 24kHz PCM16 chunks (Gemini's output
  rate — different from the 16kHz input rate) into a second `AudioContext`
  via scheduled `AudioBufferSourceNode`s for gapless playback. A plain
  `<audio>` tag can't play a raw PCM stream, hence the manual scheduling.
  `stopAndClear()` supports barge-in (pressing the mic again mid-reply stops
  whatever's still playing).

### `frontend/lib/voiceChatClient.ts`

A thin `WebSocket` wrapper (`connect`, `sendText`, `sendAudioChunk`,
`approveProposal`, `rejectProposal`, `onEvent`) that talks directly to the
FastAPI backend rather than through a Next.js API route — Next's route
handlers don't support persistent WebSocket proxying, and this project
already has precedent for the frontend calling the backend directly (see
`app/gitbook/page.tsx`).

### `frontend/components/ProposalCard.tsx`

Renders inline in the chat transcript (never a modal) when a `proposal`
event arrives — summary, rationale, and a collapsible diff reusing the same
`DiffViewer`/`DiffSummary` components the Documentation page's review flow
already uses. Approve/Reject buttons call the WS client directly.

---

## 6. The approval workflow, end to end

1. User (typed or spoken): *"Remove '(App Router)' from the Frontend Layer
   line in the Architecture Style section."*
2. Gemini calls `propose_document_change` with the full new document
   content. The harness stores it, pushes a `proposal` event.
3. `AgentSidebar` renders a `ProposalCard` inline with a summary and a
   toggleable diff. The model also says (in text, and voice if the request
   was spoken) that it's drafted the change and is waiting for approval.
4. User clicks **Approve** → client sends `{"type":"approve_proposal",...}`.
5. The WS route calls `harness.approve_proposal(id)` directly (not through
   the model) and nudges the live session with a short informational note so
   the model knows to proceed.
6. Gemini calls `apply_document_change(proposal_id)`. The harness verifies
   approval, calls `backup_and_write` (content → `.prev.md` sidecar, new
   content → the file), and pushes `proposal_applied`.
7. `AgentSidebar` calls the registered page's `onDocumentChanged(newContent,
   previousContent)`, which updates that page's local state — `DocPreview`
   reflects the new content and diff immediately, no page reload.

If the user instead says "yes, apply it" out loud without clicking Approve,
step 6 still happens (the model can attempt the call), but the harness
returns `not_yet_approved` and the model relays that back — the write never
happens without step 4.

---

## 7. Notable issues found (and fixed) while building this

- **Read scope collapsed into edit scope**: the system prompt originally
  only gave the model the *open* document's content, so it correctly
  refused to edit other files but *also* refused to even discuss them
  ("I can only read and modify REPORTS.md"). Fixed by loading the full
  repo doc context (§3) — editing stays scoped to one document, answering
  does not.
- **Blocking RAG call inside the WebSocket handler**: `retrieve_code_context`
  does a synchronous network call. Calling it directly inside `async def`
  session setup stalled FastAPI's entire single-threaded event loop for the
  duration of the call — enough to time out a *different* client's
  WebSocket handshake attempt made while it was running. Fixed with
  `asyncio.to_thread(...)`.
- **`session.receive()` only covers one turn**: see §3 — omitting the outer
  `while True` made the assistant go silent after exactly one reply.
- **Editing gated behind a separate button**: see §2 — caused typed edit
  requests to silently hit the read-only REST chatbot.
- **Sidebar torn down on navigation**: it used to be mounted inside the page
  components, so the existing page-transition animation (keyed on pathname)
  unmounted it on every route change. Fixed by lifting it to the root
  layout with context-based document registration (§5).

---

## 8. Configuration

| Variable | Where | Purpose |
|---|---|---|
| `GEMINI_API_KEY` | `backend/.env` | Used by both `LLMService` (plain chat) and `VoiceSessionService` (Live API) — same key, two SDKs (`langchain-google-genai`/`google-generativeai` for the former, `google-genai` for the latter). |
| `NEXT_PUBLIC_BACKEND_URL` | frontend env (defaults to `http://localhost:8000`) | The browser needs the backend's origin directly to open the WebSocket — Next API routes can't proxy a persistent WS connection. |

`backend/requirements.txt` pins `google-genai>=2.19.0` alongside the
pre-existing `google-generativeai`/`langchain-google-genai` — separate SDK
families from the same vendor; verified with `pip check` that they coexist
without conflicting transitive dependencies.

---

## 9. Known limitations

- **No authentication** on `/api/voice-chat` or `/api/chat` — anyone who can
  reach the backend can open a session scoped to any document id they can
  guess/enumerate. Fine for local/single-user use; would need addressing
  before any multi-tenant or public deployment.
- **RAG context for voice is seeded once, generically** — at connect time,
  using a query like *"Overview and implementation details relevant to
  &lt;filename&gt;"*, not the user's actual (not-yet-known) question. The
  plain REST chatbot retrieves fresh, question-specific RAG context on every
  message; the voice assistant does not currently re-retrieve mid-session.
- **A voice/assistant session doesn't survive a document switch as the same
  conversation** — it reconnects scoped to the new document (correct, since
  edit scope must follow the open document), but that means Gemini starts a
  fresh Live session each time, losing model-side conversational state for
  that specific exchange (the visible transcript in the sidebar is also
  cleared for the ephemeral session items, though repo-scoped plain-chat
  history persists via `localStorage`).
