"""
app/api/router.py
------------------
Central API router — registers all sub-routers.

Responsibilities:
- Import each feature router
- Attach them to the main APIRouter with appropriate prefixes / tags
- Nothing else; no business logic, no middleware
"""

from fastapi import APIRouter

from app.api import chat, debug, documents, files, gitbook, health, metrics, rag, webhook

# Main router that is registered on the FastAPI app in main.py
api_router = APIRouter()

# Health check — no prefix so the endpoint is at /health
api_router.include_router(health.router)

# GitHub webhook — no additional prefix; endpoint is at /webhook/github
api_router.include_router(webhook.router)

# RAG endpoints — prefix /api/rag; endpoints at /api/rag/bootstrap and /api/rag/retrieve
api_router.include_router(rag.router, prefix="/api/rag", tags=["RAG"])

# Generated documentation — endpoints at /api/documents
api_router.include_router(documents.router, prefix="/api/documents", tags=["Documents"])

# GitBook Integration — endpoints at /api/gitbook
api_router.include_router(gitbook.router)

# RAG workflow telemetry — endpoint at /api/debug/snapshot
api_router.include_router(debug.router, prefix="/api/debug", tags=["Debug"])

# Documentation chatbot — endpoint at /api/chat
api_router.include_router(chat.router, prefix="/api/chat", tags=["Chat"])

# Analytics dashboard — endpoint at /api/metrics/{repo_slug}
api_router.include_router(metrics.router, prefix="/api/metrics", tags=["Metrics"])

# On-demand single-file documentation — endpoints at /api/files/tree and /api/files/generate-doc
api_router.include_router(files.router, prefix="/api/files", tags=["Files"])
