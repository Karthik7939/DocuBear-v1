# DocuBear Backend

A FastAPI backend that receives GitHub push webhooks and automatically
generates, validates, and publishes repository documentation. It combines
a Retrieval-Augmented Generation (RAG) engine — for grounding the LLM in
actual repository content — with a 7-stage LangGraph multi-agent pipeline
that writes, checks, and revises the docs, then syncs them to GitBook.

For deeper detail than this quick-start covers, see:
- **`agent_explanation.md`** — plain-English walkthrough of every agent
  in the documentation pipeline.
- **`Backend_Explanation.md`** — file-by-file explanation of the FastAPI
  app, config, services, and workflow layers.
- **`rag/RAG_WALKTHROUGH.md`** — plain-English, workflow-by-workflow
  explanation of the RAG engine (bootstrap, incremental updates,
  retrieval, and how it connects to the agents).
- **`../CHATBOT_AND_VOICE_ASSISTANT.md`** — how the documentation chatbot
  and the voice assistant (Gemini Live, propose/approve/apply editing)
  work, backend and frontend.
- **`rag_fix_plan.md`** / **`fix_plan.md`** — known issues found and
  fixed in the RAG pipeline and agent pipeline, with the reasoning
  behind each decision.

---

## Features

- ✅ GitHub push webhook receiver with HMAC-SHA256 signature verification
- ✅ RAG-backed code context retrieval — hybrid vector (Pinecone/FAISS) +
  BM25 keyword + dependency-graph search, fused via Reciprocal Rank
  Fusion, reranked with a cross-encoder
- ✅ 7-agent LangGraph pipeline: Preprocessing → Understanding → Planner →
  Documentation → Validation → Revision → Sync
- ✅ Incremental indexing on every push (only changed files are re-chunked
  and re-embedded)
- ✅ Human-in-the-loop review before docs are published
- ✅ GitBook synchronization for the final rendered docs — either the
  standard doc suite or a hand-picked selection including per-file docs
- ✅ On-demand single-file documentation (generate/regenerate a doc for any
  one source file, independent of the push-triggered pipeline)
- ✅ Documentation chatbot grounded in the repo's docs + RAG code context
- ✅ Voice assistant (Gemini Live) that can also draft documentation edits,
  gated behind explicit human approval before anything is written — see
  `../CHATBOT_AND_VOICE_ASSISTANT.md`
- ✅ Knowledge Base UI endpoints for connecting/managing indexed repos
- ✅ Fully typed with Pydantic v2
- ✅ pytest unit tests with mocks

---

## Folder Structure

```
backend/
├── app/
│   ├── main.py                  # FastAPI app factory
│   ├── dependencies.py          # Dependency injection wiring
│   ├── api/
│   │   ├── router.py            # Route registration
│   │   ├── webhook.py           # POST /webhook/github
│   │   ├── rag.py               # RAG bootstrap/retrieve/knowledge-base endpoints
│   │   ├── documents.py         # Generated documentation endpoints
│   │   ├── files.py             # On-demand single-file documentation endpoints
│   │   ├── chat.py              # POST /api/chat -- read-only documentation chatbot
│   │   ├── voice_chat.py        # WS /api/voice-chat -- voice/agentic assistant
│   │   ├── gitbook.py           # GitBook sync endpoints
│   │   ├── debug.py             # Debug/inspection endpoints
│   │   └── health.py            # GET /health
│   ├── core/                    # Settings, logging, constants
│   └── models/                  # Pydantic request/response models
├── agents/                      # 7-stage LangGraph documentation pipeline
│   ├── coordinator/              # Orchestrator (LangGraph StateGraph)
│   ├── preprocessing/            # Repo scanner (no AI)
│   ├── understanding/            # LLM semantic analysis (RAG-grounded)
│   ├── documentation/            # Planner + LLM doc writer
│   ├── validation/                # Quality checker (rules + LLM)
│   ├── revision/                  # Auto-fixer
│   ├── sync/                      # Writes docs to disk
│   └── memory/                    # SharedMemory (the shared whiteboard)
├── rag/                          # RAG engine — see rag/RAG_WALKTHROUGH.md
│   ├── chunking/                  # AST-based semantic chunking (Tree-sitter)
│   ├── embeddings/                 # sentence-transformers + caching
│   ├── retrieval/                  # Vector store, BM25, dependency graph, reranker
│   ├── indexing/                   # Bootstrap + incremental indexing
│   ├── pipeline/                   # Bootstrap/retrieval pipeline orchestration
│   ├── preprocessing/               # Commit-diff query building + LLM query refinement
│   └── config/                      # RAG settings
├── services/                     # github_service, git_service, rag_service, etc.
│   ├── chat_service.py            # Documentation chatbot (intent routing + RAG-grounded Q&A)
│   ├── doc_context_service.py     # Shared doc/RAG context loader (chat + voice assistant)
│   ├── document_store_service.py  # Shared safe-write path (backup .prev.md then overwrite)
│   ├── file_doc_service.py        # On-demand single-file documentation generation
│   ├── voice_session_service.py   # Gemini Live session lifecycle
│   └── voice_tool_harness.py      # propose/apply-change tools + human approval gate
├── workflow/                     # Workflow JSON persistence
├── prompts/                      # Prompt templates for every LLM-calling agent
├── utils/                        # JSON/Git/UUID helpers
├── scripts/                      # Standalone maintenance scripts (e.g. run_index_repo.py)
├── repositories/                 # Cloned repositories (runtime)
├── generated_docs/               # Output folder — docs written here (runtime)
├── logs/                         # Application log files (runtime)
├── tests/                        # pytest suite
├── .env                          # Your API keys and settings (never commit)
└── requirements.txt              # All Python dependencies
```

---

## Installation

### Prerequisites

- Python 3.11+
- Git
- A Pinecone account + index (or configure the FAISS local backend instead)
- An LLM provider API key (Gemini, Groq, or a locally-running Ollama)

### Steps

```bash
# 1. Clone this repository
git clone <your-repo-url>
cd backend

# 2. Create and activate a virtual environment
python -m venv .venv
# Windows
.venv\Scripts\activate
# macOS / Linux
source .venv/bin/activate

# 3. Install dependencies
pip install -r requirements.txt

# 4. Configure environment
cp .env.example .env
# Edit .env — set your LLM provider key(s), Pinecone key/index, and
# RAG_* settings. See rag/config/settings.py for what each does.
```

---

## Running Locally

**Use `start.ps1` instead of running `uvicorn` directly on Windows** — it
restricts `--reload`'s file watcher to source directories only. Running
plain `uvicorn --reload` watches the whole project, including
`repositories/`, so a webhook-triggered `git clone` can trigger a reload
mid-pipeline and kill an in-progress documentation run.

```powershell
.venv\Scripts\activate
.\start.ps1
```

(On macOS/Linux, or if you don't need the restricted watch, plain
`uvicorn app.main:app --reload --host 0.0.0.0 --port 8000` works too.)

- Swagger UI docs: http://localhost:8000/docs
- Health check: http://localhost:8000/health

### Index a repository before it can be documented

The RAG engine needs a repository indexed before retrieval returns useful
context. Either:
- `POST /api/rag/index-repo` with `{"repository_name": "owner/repo"}` —
  clones (if needed) and bootstraps the index in one call, or
- `POST /api/rag/bootstrap` if the repo is already cloned locally.

### Receive GitHub webhooks locally

Since GitHub webhooks need a public HTTPS URL, use ngrok (or similar) to
tunnel to your local server:

```bash
ngrok http 8000
```

Then in your repository's GitHub settings → Webhooks → Add Webhook:
1. **Payload URL**: `https://<your-ngrok-url>/webhook/github`
2. **Content type**: `application/json`
3. **Secret**: matches `GITHUB_SECRET` in `.env` (optional — signature
   verification is skipped if left empty)
4. **Which events**: "Just the push event"

Every push after that will trigger: repo sync → incremental RAG indexing
→ the full agent pipeline → docs written to `generated_docs/<repo>/`.

---

## API Documentation

### GET /health
Returns `{"status": "healthy"}`.

### POST /webhook/github
Receives a GitHub push event. Requires `X-GitHub-Event: push` and, if
`GITHUB_SECRET` is set, a valid `X-Hub-Signature-256` header. Returns
`202 Accepted` immediately — the pipeline runs in a background thread so
GitHub doesn't see a timeout.

### RAG endpoints (`/api/rag/*`)
`bootstrap`, `index-repo`, `retrieve`, `status/{repository_name}`,
`knowledge-base` (list/delete indexed repos), `repos` (list local repos +
index status). See the Swagger UI for full request/response shapes.

### Document & GitBook endpoints (`/api/documents/*`, `/api/gitbook/*`)
List generated docs, fetch a specific doc, and sync approved docs to a
connected GitBook space (the whole standard suite, or a specific selection
including per-file docs).

### On-demand file documentation (`/api/files/*`)
Generate or regenerate documentation for a single source file, independent
of the push-triggered pipeline. Also lists a repository's file tree and its
history of previously generated file docs.

### Documentation chatbot (`POST /api/chat`)
Read-only Q&A grounded in the repo's generated docs + RAG code context. See
`../CHATBOT_AND_VOICE_ASSISTANT.md`.

### Voice / agentic assistant (`WS /api/voice-chat`)
WebSocket session (Gemini Live) that can also draft and, after explicit
human approval, apply changes to the one document currently open in the
viewer. Query params: `document_id`, `repository_name`. Requires
`GEMINI_API_KEY`. Full protocol and architecture:
`../CHATBOT_AND_VOICE_ASSISTANT.md`.

Full interactive schema for every REST endpoint: http://localhost:8000/docs
(WebSocket routes aren't included in the OpenAPI schema.)

---

## Testing Instructions

```bash
# Run all tests
pytest tests/ -v

# Run a specific test file
pytest tests/test_agents/test_coordinator.py -v

# Run with coverage
pytest tests/ --cov=app --cov=agents --cov=rag --cov=services -v
```

---

## Development Guidelines

- **No business logic in API routes** — routes delegate entirely to
  services/agents.
- **Use GitPython** — never execute raw shell commands for Git operations.
- **All endpoints return JSON** — no HTML responses.
- **Agents only talk through `SharedMemory`** — never directly to each
  other. The Coordinator is the only thing that runs agents.
- **The Coordinator must not** call LLMs, parse files, generate docs, or
  touch the vector database directly — see `agents/coordinator/coordinator.py`.
- **Log every significant operation** using the module-level logger.
- **Never expose stack traces** in API responses.
