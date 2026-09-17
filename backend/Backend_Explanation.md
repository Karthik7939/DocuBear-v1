# Backend — Complete Explanation

> This document explains every file and layer of the backend in simple words.
> It covers: server entry point, configuration, API endpoints, service layer,
> workflow engine, utilities, and data models.
> For the AI agent pipeline, see `agent_explanation.md`.
> For the documentation chatbot and voice assistant, see
> `../CHATBOT_AND_VOICE_ASSISTANT.md`.

---

## Project Directory Structure

```
backend/
├── app/
│   ├── main.py                  ← FastAPI app + server startup
│   ├── dependencies.py          ← Wires all services together (dependency injection)
│   ├── api/
│   │   ├── router.py            ← Registers all API routes in one place
│   │   ├── webhook.py           ← POST /webhook/github  ← main endpoint
│   │   ├── chat.py              ← POST /api/chat -- read-only documentation chatbot
│   │   ├── voice_chat.py        ← WS /api/voice-chat -- voice/agentic assistant
│   │   ├── files.py             ← On-demand single-file documentation endpoints
│   │   └── health.py            ← GET  /health
│   ├── core/
│   │   ├── config.py            ← Reads .env once and shares it everywhere
│   │   ├── settings.py          ← Defines what settings exist
│   │   ├── logger.py            ← Sets up console + file logging
│   │   └── constants.py         ← Shared string constants and enums
│   └── models/
│       ├── webhook.py           ← Pydantic model for GitHub push payloads
│       └── workflow.py          ← Pydantic model for workflow status responses
│
├── agents/                      ← AI pipeline (see agent_explanation.md)
│   ├── coordinator/             ← LangGraph orchestrator
│   ├── preprocessing/           ← Repo scanner (no AI)
│   ├── understanding/           ← LLM semantic analysis
│   ├── documentation/           ← LLM doc writer
│   ├── validation/              ← Quality checker
│   ├── revision/                ← Auto-fixer
│   ├── sync/                    ← Writes docs to disk
│   └── memory/                  ← SharedMemory (the shared whiteboard)
│
├── services/
│   ├── github_service.py        ← Receives webhook, runs the full pipeline
│   ├── git_service.py           ← Clones / pulls repositories using Git
│   ├── llm_service.py           ← LangChain-backed LLM (Groq / Gemini / OpenAI)
│   ├── parser_service.py        ← Extracts file lists and author from payload
│   ├── repository_service.py    ← Manages the repositories/ folder
│   ├── workflow_service.py      ← Saves/loads workflow state to/from disk
│   ├── chat_service.py          ← Documentation chatbot (see §12)
│   ├── doc_context_service.py   ← Shared doc/RAG context loader (see §12)
│   ├── document_store_service.py← Shared safe-write path (backup + overwrite) (see §12)
│   ├── file_doc_service.py      ← On-demand single-file documentation
│   ├── voice_session_service.py ← Gemini Live session lifecycle (see §12)
│   └── voice_tool_harness.py    ← Propose/apply-change tools + approval gate (see §12)
│
├── rag/                          ← Full RAG engine (chunking, embeddings,
│                                    retrieval, indexing) — see §7 below
│                                    and rag/RAG_WALKTHROUGH.md
│
├── workflow/
│   ├── workflow_manager.py      ← Creates, saves, loads workflow JSON files
│   └── workflow_state.py        ← In-memory dataclass for one workflow run
│
├── prompts/
│   ├── understanding_prompt.py  ← Prompts for the Understanding Agent
│   ├── documentation_prompt.py  ← Prompts for the Documentation Agent
│   ├── validation_prompt.py     ← Prompts for the Validation Agent
│   └── revision_prompt.py       ← Prompts for the Revision Agent
│
├── utils/
│   ├── file_utils.py            ← JSON read/write, directory helpers
│   ├── git_utils.py             ← Low-level Git helpers
│   └── helpers.py               ← UUID generator, timestamp helper
│
├── tests/                       ← Unit tests for every agent and service
├── generated_docs/              ← Output folder — docs written here
├── repositories/                ← Cloned repos stored here at runtime
├── logs/                        ← backend.log written here at runtime
├── .env                         ← Your API keys and settings (never commit)
├── .env.example                 ← Template showing which keys are needed
├── requirements.txt             ← All Python dependencies
├── README.md                    ← Quick-start guide
└── agent_explanation.md         ← Plain-English explanation of the AI pipeline
```

---

## 1. Entry Point — `app/main.py`

**What it is:** The root of the entire application. Creates and configures
the FastAPI server.

**What it does when you start the server:**

1. Creates the FastAPI app with metadata (title, version, docs URL at `/docs`).
2. Adds **CORS middleware** — allows requests from any origin so Postman and
   frontends can call the API without browser security errors.
3. Registers all API routes from `app/api/router.py`.
4. On **startup** (runs once when the server starts):
   - Sets up logging to the console and to `logs/backend.log`.
   - Creates the `repositories/` and `workflow/` folders if they don't exist.
   - Logs the current configuration so you can see what settings are active.
5. On **shutdown**: logs a goodbye message.

**How to start the server:**
```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

## 2. Configuration — `app/core/`

This folder contains everything related to settings, logging, and shared constants.

---

### `settings.py` — The Settings Class

**What it is:** A simple class that reads your `.env` file and makes the
values available everywhere in the app.

```python
class Settings:
    github_secret   = os.getenv("GITHUB_SECRET", "")
    repository_root = os.getenv("REPOSITORY_ROOT", "repositories")
    workflow_path   = os.getenv("WORKFLOW_PATH", "workflow")
    log_level       = os.getenv("LOG_LEVEL", "INFO")
    log_file        = os.getenv("LOG_FILE", "logs/backend.log")
```

| Setting | What it does | Default |
|---|---|---|
| `GITHUB_SECRET` | HMAC key to verify GitHub webhook signatures | `""` (skip verification) |
| `REPOSITORY_ROOT` | Folder where cloned repos are stored | `repositories` |
| `WORKFLOW_PATH` | Folder where workflow JSON files are saved | `workflow` |
| `LOG_LEVEL` | How much detail to log (DEBUG/INFO/WARNING) | `INFO` |
| `LOG_FILE` | Path to the log file | `logs/backend.log` |
| `GROQ_API_KEY` | API key for Groq LLM (used by `LLMService`) | required for LLM |
| `LLM_MODEL` | Which LLM model to use | `llama-3.3-70b-versatile` |

---

### `config.py` — Singleton Loader

**What it is:** Makes sure the `.env` file is read **only once** at startup,
not on every single request.

```python
@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()

settings = get_settings()   # shared instance used by all modules
```

Every other module just does:
```python
from app.core.config import settings
```

---

### `logger.py` — Logging Setup

**What it is:** Configures the Python root logger to write logs in two places.

- **Console handler** — prints logs to the terminal in real time.
- **Rotating file handler** — writes to `logs/backend.log`. When the file
  hits 10 MB it starts a new file; keeps 5 backups.
- **Log format:** `2026-07-21T00:15:00 | INFO | app.api.webhook | Webhook received`

Every module creates its own named logger:
```python
logger = logging.getLogger(__name__)
```

---

### `constants.py` — Enums and Constants

**What it is:** Central place for all fixed string values — prevents typos.

```python
class WorkflowStatus(str, Enum):
    PENDING     = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED   = "completed"
    FAILED      = "failed"

class GitHubEvent(str, Enum):
    PUSH = "push"
    PING = "ping"
```

- `WorkflowStatus` — the four possible states of a processing run.
- `GitHubEvent` — only `push` is processed; `ping` is acknowledged but ignored.
- HTTP header names like `x-github-event` and `x-hub-signature-256` are also
  stored here so they're never typed as raw strings.

---

## 3. Dependency Injection — `app/dependencies.py`

**What it is:** The file that wires every service together so FastAPI endpoints
don't have to build their own objects.

FastAPI uses **dependency injection**: you declare a factory function and FastAPI
calls it before running your endpoint:

```python
async def receive_webhook(
    github_service: GitHubService = Depends(get_github_service)
):
    ...
```

**What each factory function builds:**

| Function | Returns | Depends on |
|---|---|---|
| `get_settings()` | `Settings` | reads `.env` |
| `get_logger()` | `logging.Logger` | none |
| `get_repository_service()` | `RepositoryService` | settings |
| `get_git_service()` | `GitService` | settings |
| `get_workflow_manager()` | `WorkflowManager` | settings |
| `get_workflow_service()` | `WorkflowService` | WorkflowManager |
| `get_parser_service()` | `ParserService` | none |
| `get_github_service()` | `GitHubService` | all of the above + Coordinator |

**`get_github_service()` is where the AI pipeline is wired:**
```python
llm_service   = LLMService()           # LangChain ChatGroq
preprocessing = PreprocessingAgent()
understanding = UnderstandingAgent(rag_service=None, llm_client=llm_service)
documentation = DocumentationAgent(llm_client=llm_service)
validation    = ValidationAgent(llm_client=llm_service)
revision      = RevisionAgent(llm_client=llm_service)
sync          = SyncAgent(output_dir="generated_docs")
coordinator   = Coordinator(...)       # LangGraph StateGraph
```

> `rag_service=None` means the Understanding Agent reasons from metadata only.
> The RAG service will be plugged in here when it is ready.

---

## 4. API Layer — `app/api/`

### `router.py` — Route Registry

Registers all API routes into one central router:

```python
api_router.include_router(health.router)   # GET  /health
api_router.include_router(webhook.router)  # POST /webhook/github
```

---

### `health.py` — Health Check

**Endpoint:** `GET /health`

```json
{ "status": "healthy" }
```

Simple check used by monitoring tools to verify the server is running.

---

### `webhook.py` — GitHub Webhook Endpoint

**Endpoint:** `POST /webhook/github`

This is where everything starts. GitHub calls this URL every time someone
pushes code to a configured repository.

**The 6 steps it runs:**

**Step 1 — Check event type:**
Only `push` events are processed. Anything else gets HTTP 400.

**Step 2 — Read the raw request body:**
The raw bytes are needed for HMAC signature verification.

**Step 3 — Verify the webhook signature:**
Checks the `X-Hub-Signature-256` header using HMAC-SHA256 against
`GITHUB_SECRET`. If the secret is empty in `.env`, this check is skipped
(good for local development).

**Step 4 — Parse the payload:**
Uses Pydantic to convert the JSON body into a typed `WebhookPayload` object.
If the JSON is malformed, returns HTTP 422 automatically.

**Step 5 — Hand off to GitHubService:**
```python
result = github_service.process_push_event(payload)
```
All business logic runs inside `GitHubService`, not in the endpoint.

**Step 6 — Return a response:**
```json
{
  "status": "success",
  "workflow_id": "3fa85f64-...",
  "repository": "Hello-World",
  "branch": "main"
}
```

**Error responses:**

| Code | Reason |
|---|---|
| 400 | Unsupported event type (not a push) |
| 400 | Invalid webhook signature |
| 422 | Malformed JSON payload |
| 500 | Unexpected server error |

> The endpoint responds **202 Accepted** immediately and runs the pipeline in
> a **background thread** — this prevents GitHub from timing out while waiting.

---

## 5. Data Models — `app/models/`

### `webhook.py` — GitHub Payload Models

Pydantic models that represent what GitHub sends us:

```python
class WebhookPayload:
    ref: str              # e.g. "refs/heads/main"
    repository: Repository
    pusher: Pusher        # who pushed
    commits: list[Commit] # list of commits in this push

class Commit:
    id: str               # commit SHA
    added: list[str]      # newly added files
    modified: list[str]   # changed files
    removed: list[str]    # deleted files
    timestamp: str        # when this commit happened
```

### `workflow.py` — Workflow Response Models

Pydantic models for the API response:

```python
class WebhookResponse:
    status: str           # "success" or "error"
    workflow_id: str      # UUID for this run
    repository: str       # repo name
    branch: str           # branch name
    message: str          # human-readable description
```

---

## 6. Service Layer — `services/`

### `github_service.py` — The Top-Level Orchestrator

**What it does:**
1. Receives the parsed `WebhookPayload` from the webhook endpoint.
2. Verifies the HMAC signature.
3. Extracts which files were added/modified and who pushed them.
4. Clones or pulls the repository to the local `repositories/` folder.
5. Calls `coordinator.start_workflow(...)` to run the AI pipeline.
6. Saves the final workflow status to disk via `WorkflowService`.

This service is the bridge between the HTTP layer and the AI pipeline.

---

### `git_service.py` — Repository Cloning

**What it does:**
- If the repository has never been cloned: runs `git clone`.
- If it was cloned before: runs `git pull` to get the latest changes.
- Uses `GitPython` (the `git` Python library) — no subprocess calls.
- Stores all repos under `repositories/<owner>_<repo>/`.

---

### `llm_service.py` — LangChain LLM

**What it does:** The single place where all LLM communication happens.
All agents call `llm_service.generate(prompt)`.

**How it picks the LLM provider** (checks in this order):
1. `GROQ_API_KEY` set → uses **`ChatGroq`** from `langchain-groq`
2. `GEMINI_API_KEY` set → uses **`ChatGoogleGenerativeAI`** from `langchain-google-genai`
3. `OPENAI_API_KEY` set → uses **`ChatOpenAI`** from `langchain-openai`
4. No key → returns a placeholder message and logs a warning

**LangChain chain used:**
```python
chain = ChatGroq(model="llama-3.3-70b-versatile") | StrOutputParser()
response = chain.invoke([HumanMessage(content=prompt)])
```

**Key package:** `langchain-groq>=0.3.0` with `groq>=0.11.0,<1.0.0`
(groq 0.9.0 was incompatible with httpx 0.28 — see `requirements.txt` comment)

---

### `parser_service.py` — Payload Parser

**What it does:** Extracts the useful data from the raw webhook payload:
- `added_files` — list of new files in this push
- `modified_files` — list of changed files in this push
- `author` — GitHub username of the developer who pushed
- `push_timestamp` — ISO-8601 timestamp of the push

This is pure Python — no external libraries needed.

---

### `repository_service.py` — Repository Folder Manager

**What it does:** Handles the `repositories/` directory:
- Builds the local path for a given repository name
- Creates the directory if it doesn't exist
- Lists all currently cloned repositories
- Deletes a repository folder when cleanup is needed

---

### `workflow_service.py` — Workflow State Persistence

**What it does:** Saves and loads workflow run status to disk (in `workflow/`):
- Each workflow run gets a UUID-named JSON file.
- The file tracks: status (pending/in_progress/completed/failed), timing,
  which repo, which branch, error messages.
- Old completed workflow files are cleaned up automatically.

---

## 7. RAG Service — `rag/` + `services/rag_service.py`

**Status: fully built and connected.** (This section previously described
an early prototype — 100-line keyword-overlap chunking — that no longer
exists. The real system is substantially larger: AST-based semantic
chunking via Tree-sitter, sentence-transformers embeddings, a hybrid
retriever combining Pinecone/FAISS vector search + BM25 keyword search +
dependency-graph traversal via Reciprocal Rank Fusion, a cross-encoder
reranker, and MMR-based context diversity. `UnderstandingAgent` is wired
to it via `rag_service`/`shared_memory.rag_context_package` as described
in `agent_explanation.md`.)

For the full workflow-by-workflow walkthrough (bootstrap, incremental
updates, retrieval, and how it all connects to the agents — in plain
words), see `rag/RAG_WALKTHROUGH.md`.
For the RAG pipeline's known issues, fixes, and design decisions made
along the way, see `rag_fix_plan.md`.

---

## 8. Workflow Engine — `workflow/`

### `workflow_manager.py` — Lifecycle Manager

Manages JSON state files in the `workflow/` folder:

- `create_workflow(repo, branch)` — creates a new JSON file with `status=pending`
- `update_workflow(id, status, ...)` — updates the file with new status
- `get_workflow(id)` — reads and returns a workflow's state
- `list_workflows()` — returns all workflow runs
- `delete_workflow(id)` — removes the JSON file

### `workflow_state.py` — In-Memory State

A simple Python dataclass that holds one workflow run's data in memory
during processing (before it is written to disk):

```python
@dataclass
class WorkflowState:
    workflow_id: str
    repository_name: str
    branch: str
    status: str     # pending / in_progress / completed / failed
    created_at: str
    updated_at: str
```

---

## 9. Utilities — `utils/`

### `file_utils.py`
- `read_json(path)` — reads a JSON file and returns a dict
- `write_json(path, data)` — writes a dict to a JSON file
- `ensure_dir(path)` — creates a directory if it doesn't already exist

### `git_utils.py`
Low-level Git helper functions used by `git_service.py`:
- Check if a path is a valid Git repository
- Get the current HEAD commit SHA
- Get the current branch name

### `helpers.py`
- `generate_uuid()` — returns a new UUID string (used for workflow IDs)
- `generate_timestamp()` — returns the current UTC time as an ISO-8601 string

---

## 10. Prompts — `prompts/`

These files contain the text templates sent to the LLM.
Each template has named placeholders like `{repository_name}` and `{file_content}`
that are filled in at runtime.

| File | Used by | What it asks the LLM |
|---|---|---|
| `understanding_prompt.py` | Understanding Agent | Explain the repo architecture, modules, APIs |
| `documentation_prompt.py` | Documentation Agent | Write a Markdown doc for this file |
| `validation_prompt.py` | Validation Agent | Score this document for accuracy and completeness |
| `revision_prompt.py` | Revision Agent | Fix the issues listed in this document |

---

## 11. Tests — `tests/`

```
tests/
├── test_agents/
│   ├── test_coordinator.py      ← Tests for LangGraph pipeline
│   ├── test_preprocessing.py
│   ├── test_understanding.py
│   ├── test_documentation.py
│   ├── test_validation.py
│   ├── test_revision.py
│   ├── test_sync.py
│   └── test_shared_memory.py
├── test_git.py
├── test_github.py
└── test_webhook.py
```

Run all tests with:
```bash
pytest tests/ -v
```

---

## 12. Documentation Chatbot & Voice Assistant

**Status: fully built.** Two related but distinct capabilities, both
surfaced as one collapsible sidebar in the frontend:

- **`chat_service.py`** + `app/api/chat.py` (`POST /api/chat`) — a
  read-only chatbot. Regex-classifies each question into `file_history`
  (answered from git log), `file_content` (answered from the raw file), or
  `general` (answered by an LLM call grounded in `doc_context_service`'s
  repo-wide doc + RAG context).
- **`voice_session_service.py`** + **`voice_tool_harness.py`** +
  `app/api/voice_chat.py` (`WS /api/voice-chat`) — a Gemini Live
  (`gemini-3.8-live`) session that can also *edit* the one document
  currently open in the frontend viewer, but only after the human clicks
  Approve on a drafted proposal shown in the UI. The approval check is
  enforced in `voice_tool_harness.py`, not by asking the model nicely —
  `apply_document_change` is refused with `not_yet_approved` unless a
  matching `approve_proposal` call already arrived from an explicit UI
  button click.
- **`doc_context_service.py`** and **`document_store_service.py`** are
  small shared modules extracted so the chatbot and the voice assistant
  read from (and safely write to) documents the same way, instead of two
  copies of that logic drifting apart.

Full architecture, the WebSocket message protocol, the frontend pieces
(persistent sidebar, mic capture/playback, modality-aware audio playback),
and the issues found while building it: see
**`../CHATBOT_AND_VOICE_ASSISTANT.md`**.

---

## Environment Variables (`.env`)

```bash
# GitHub webhook signature verification
GITHUB_SECRET=your_secret_here

# Folder paths (relative to project root)
REPOSITORY_ROOT=repositories
WORKFLOW_PATH=workflow

# Logging
LOG_LEVEL=INFO
LOG_FILE=logs/backend.log

# LLM (Groq is the primary provider)
GROQ_API_KEY=gsk_...
LLM_MODEL=llama-3.3-70b-versatile
```

> Never commit your `.env` file. Use `.env.example` as a template.

---

## Key Packages in `requirements.txt`

| Package | What it does |
|---|---|
| `fastapi` | HTTP web framework — handles routing, request parsing, dependency injection |
| `uvicorn` | ASGI server that runs the FastAPI app |
| `pydantic` | Data validation — ensures JSON payloads have the right fields and types |
| `python-dotenv` | Reads the `.env` file into environment variables |
| `GitPython` | Python interface for Git — used to clone and pull repositories |
| `langchain` | Core LangChain framework — prompt templates, chains, output parsers |
| `langchain-groq` | LangChain connector for the Groq API (`ChatGroq`) |
| `langgraph` | Builds the agent pipeline as a directed graph (`StateGraph`) |
| `groq` | Official Groq API client (used internally by `langchain-groq`) |
| `httpx` | HTTP client — used by tests and some utilities |
| `pytest` | Test runner |
