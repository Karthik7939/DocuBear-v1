"""
app/dependencies.py
--------------------
FastAPI shared dependency providers.

Responsibilities:
- Provide the Settings / configuration object via FastAPI Depends
- Provide a module-level logger
- Construct and provide fully wired service instances
- Keep all wiring in one place so the API layer remains free of
  construction logic

LangChain / LangGraph wiring:
- LLMService uses LangChain ChatGroq internally (no raw httpx calls)
- Coordinator is a LangGraph StateGraph (same start_workflow() API)
- RAGService wraps the rag/ module pipelines and is injected into both
  UnderstandingAgent (for on-demand retrieval) and GitHubService (for
  commit-level incremental indexing + retrieval)
"""

import logging

from app.core.config import settings
from app.core.settings import Settings
from services.git_service import GitService
from services.github_service import GitHubService
from services.parser_service import ParserService
from services.repository_service import RepositoryService
from services.workflow_service import WorkflowService
from workflow.workflow_manager import WorkflowManager

# LangChain-backed LLM service
from services.llm_service import LLMService

# RAG service — bridges the rag/ module to the agent pipeline
from services.rag_service import RAGService

# Documentation chatbot
from services.chat_service import ChatService

# On-demand single-file documentation
from services.file_doc_service import FileDocumentationService

# Agents
from agents.preprocessing.preprocessing_agent import PreprocessingAgent
from agents.understanding.understanding_agent import UnderstandingAgent
from agents.documentation.documentation_agent import DocumentationAgent
from agents.validation.validation_agent import ValidationAgent
from agents.revision.revision_agent import RevisionAgent
from agents.sync.sync_agent import SyncAgent

# LangGraph-based Coordinator
from agents.coordinator.coordinator import Coordinator


# ---------------------------------------------------------------------------
# Logger dependency
# ---------------------------------------------------------------------------

def get_logger(name: str = "app") -> logging.Logger:
    """Return a named logger instance.

    Args:
        name: Logger namespace; defaults to 'app'.

    Returns:
        logging.Logger: The logger for the given namespace.
    """
    return logging.getLogger(name)


# ---------------------------------------------------------------------------
# Settings dependency
# ---------------------------------------------------------------------------

def get_settings() -> Settings:
    """Return the application settings singleton.

    This is exposed as a FastAPI dependency so endpoints can receive
    configuration via ``Depends(get_settings)``.

    Returns:
        Settings: The application configuration object.
    """
    return settings


# ---------------------------------------------------------------------------
# Service factories
# ---------------------------------------------------------------------------

def get_repository_service() -> RepositoryService:
    """Construct and return a RepositoryService instance.

    Returns:
        RepositoryService: Configured with the repository root from settings.
    """
    return RepositoryService(repository_root=settings.repository_root)


def get_git_service() -> GitService:
    """Construct and return a GitService instance.

    Returns:
        GitService: Configured with the repository root from settings.
    """
    return GitService(repository_root=settings.repository_root)


def get_workflow_manager() -> WorkflowManager:
    """Construct and return a WorkflowManager instance.

    Returns:
        WorkflowManager: Configured with the workflow directory from settings.
    """
    return WorkflowManager(workflow_dir=settings.workflow_path)


def get_workflow_service() -> WorkflowService:
    """Construct and return a WorkflowService instance.

    Returns:
        WorkflowService: Wrapping a fresh WorkflowManager.
    """
    return WorkflowService(workflow_manager=get_workflow_manager())


def get_parser_service() -> ParserService:
    """Construct and return a ParserService instance.

    Returns:
        ParserService: Stateless parser with no configuration.
    """
    return ParserService()


def get_rag_service() -> RAGService:
    """Construct and return a RAGService instance.

    RAGService wraps the ``rag/`` module pipelines:
    - ``index_repository()`` -> BootstrapPipeline (full index build)
    - ``retrieve()``          -> RetrievalPipeline (query-time retrieval)
    - ``run_incremental()``   -> RAGPipeline (commit-driven incremental update)

    All methods degrade gracefully: failures are logged as warnings and the
    agent pipeline continues in metadata-only mode.

    Returns:
        RAGService: Ready-to-use RAG adapter with no repository pre-bound.
    """
    return RAGService()


def get_chat_service() -> ChatService:
    """Construct and return a ChatService instance.

    Returns:
        ChatService: Wired with RepositoryService (path resolution),
        GitService (file history), and LLMService (general Q&A).
    """
    return ChatService(
        repository_service=get_repository_service(),
        git_service=get_git_service(),
        llm_client=LLMService(),
    )


def get_file_doc_service() -> FileDocumentationService:
    """Construct and return a FileDocumentationService instance.

    Returns:
        FileDocumentationService: Wired with RepositoryService (local clone
        path resolution) and LLMService (single-file doc generation).
    """
    return FileDocumentationService(
        repository_service=get_repository_service(),
        llm_client=LLMService(),
    )


def get_github_service() -> GitHubService:
    """
    Construct and return a fully wired GitHubService instance.

    Wiring summary:
      - LLMService uses LangChain ChatGroq (or Gemini/OpenAI fallback) --
        no raw httpx calls.
      - RAGService is injected into both:
          * UnderstandingAgent -- for on-demand repository retrieval when
            rag_service.index_repository() is called inside the agent.
          * GitHubService -- for commit-level incremental pipeline execution
            (RAGPipeline.run) before the coordinator graph starts. The
            resulting ContextPackage is forwarded to the coordinator and
            stored in SharedMemory for UnderstandingAgent to consume.
      - Coordinator is backed by a LangGraph StateGraph with conditional
        edges for the validation -> revision loop.

    All other callers only need ``Depends(get_github_service)``.

    Returns:
        GitHubService: Orchestrator wired with all required services.
    """
    # --- LangChain-backed LLM ---
    llm_service = LLMService()

    # --- RAG service (shared between agent and GitHub service) ---
    rag_service = get_rag_service()

    # --- Agents ---
    preprocessing = PreprocessingAgent()

    # UnderstandingAgent receives the real RAGService.
    # It will use the pre-computed ContextPackage from SharedMemory first
    # (set by GitHubService via the coordinator) and fall back to calling
    # rag_service.retrieve() directly only when no pre-computed package
    # is available (e.g. standalone invocations or bootstrap failures).
    understanding = UnderstandingAgent(
        rag_service=rag_service,
        llm_client=llm_service,
    )

    documentation = DocumentationAgent(llm_client=llm_service)
    validation    = ValidationAgent(llm_client=llm_service)
    revision      = RevisionAgent(llm_client=llm_service)
    sync          = SyncAgent(output_dir="generated_docs", overwrite=True)

    # --- LangGraph Coordinator ---
    coordinator = Coordinator(
        preprocessing_agent=preprocessing,
        understanding_agent=understanding,
        documentation_agent=documentation,
        validation_agent=validation,
        revision_agent=revision,
        sync_agent=sync,
    )

    return GitHubService(
        git_service=get_git_service(),
        parser_service=get_parser_service(),
        workflow_service=get_workflow_service(),
        repository_service=get_repository_service(),
        coordinator=coordinator,
        github_secret=settings.github_secret,
        rag_service=rag_service,  # Runs RAGPipeline on each push event
    )
