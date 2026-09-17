"""
services/doc_context_service.py
----------------------------------
Shared "what does the LLM know about this repository" context loader.

Used by both the read-only text chatbot (ChatService, via POST /api/chat)
and the voice assistant (VoiceSessionService, via the /api/voice-chat
WebSocket) so a question like "what changed in CHANGELOG.md" gets answered
consistently regardless of which one is asked -- both are meant to be
grounded in the *whole* repository's generated documentation, not just
whichever single document happens to be open in the viewer.

(Edit capability is intentionally scoped tighter than read/answer capability
-- the voice assistant may only ever propose/apply changes to the one open
document, per services/voice_tool_harness.py. This module only concerns
what the model is allowed to *read and talk about*.)
"""

from __future__ import annotations

import logging

from app.core.config import settings

logger = logging.getLogger(__name__)

_MAX_DOC_CHARS_EACH = 2_500

DOC_FILENAMES = [
    "README.md", "ARCHITECTURE.md", "WORKFLOW.md",
    "SECURITY.md", "REPORTS.md", "CHANGELOG.md",
]


def load_generated_docs(repository_name: str) -> tuple[str, list[str]]:
    """Load every standard generated doc for a repository, truncated per-file
    to keep prompts bounded.

    Returns:
        (doc_context, sources): doc_context is the concatenated Markdown
        (each file under a "### filename" heading), sources is the list of
        filenames that were actually found and included.
    """
    slug = repository_name.replace("/", "_")
    repo_docs_dir = settings.generated_docs_path_dir / slug

    blocks: list[str] = []
    sources: list[str] = []
    for filename in DOC_FILENAMES:
        doc_path = repo_docs_dir / filename
        if not doc_path.is_file():
            continue
        try:
            content = doc_path.read_text(encoding="utf-8")
        except OSError:
            continue
        blocks.append(f"### {filename}\n{content[:_MAX_DOC_CHARS_EACH]}")
        sources.append(filename)

    return "\n\n".join(blocks), sources


def retrieve_code_context(repository_name: str, query_text: str) -> str:
    """Retrieve RAG-matched source code chunks relevant to query_text.

    Degrades gracefully (returns "") if the repo hasn't been RAG-indexed or
    retrieval otherwise fails -- callers should treat an empty result as
    "no matching code context", not an error.
    """
    try:
        from agents.documentation.context_slicer import ContextSlicer
        from rag.pipeline.retrieval_pipeline import RetrievalPipeline
        from rag.schemas.query import SemanticQuery

        query = SemanticQuery(
            repository=repository_name,
            commit_sha="HEAD",
            query_text=query_text,
            top_k=8,
        )
        pipeline = RetrievalPipeline(repository=repository_name)
        context_package = pipeline.retrieve(query)
        return ContextSlicer().get_global_context(context_package)
    except Exception as exc:
        logger.warning("doc_context_service: code RAG retrieval failed/unavailable: %s", exc)
        return ""
