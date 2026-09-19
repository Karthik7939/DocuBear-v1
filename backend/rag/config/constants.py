"""
Global constants used throughout the RAG system.

These values are static and should not be modified at runtime.
"""

from pathlib import Path

# Supported Languages
SUPPORTED_LANGUAGES: dict[str, str] = {
    ".py": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".tsx": "tsx",
    ".jsx": "jsx",
    ".java": "java",
    ".cpp": "cpp",
    ".cc": "cpp",
    ".c": "c",
    ".h": "c",
    ".cs": "csharp",
    ".go": "go",
    ".rs": "rust",
    ".rb": "ruby",
    ".php": "php",
    ".swift": "swift",
    ".kt": "kotlin",
    ".scala": "scala",
}


# Documentation Files
DOCUMENTATION_EXTENSIONS = {
    ".md",
    ".txt",
    ".rst",
}

# Ignored Directories
IGNORED_DIRECTORIES = {
    ".git",
    ".idea",
    ".vscode",
    "__pycache__",
    "node_modules",
    "venv",
    ".venv",
    "env",
    "dist",
    "build",
    "coverage",
    ".pytest_cache",
    ".mypy_cache",
}


# Ignored File Extensions
IGNORED_EXTENSIONS = {
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".ico",
    ".pdf",
    ".zip",
    ".tar",
    ".gz",
    ".7z",
    ".exe",
    ".dll",
    ".so",
    ".obj",
    ".o",
    ".class",
    ".pyc",
}


# Chunk Metadata
DEFAULT_CHUNK_TYPE = "code"

DEFAULT_DOC_TYPE = "documentation"


# Retrieval
DEFAULT_TOP_K = 10

DEFAULT_RRF_K = 60

# Hash Algorithm
HASH_ALGORITHM = "sha256"

# FAISS
FAISS_INDEX_FILENAME = "faiss.index"

METADATA_FILENAME = "metadata.json"


# Dependency Graph
DEPENDENCY_GRAPH_FILENAME = "dependency_graph.json"


# BM25
BM25_FILENAME = "bm25.pkl"

# Default Storage Directories
FAISS_DIRECTORY = Path("storage/faiss")

BM25_DIRECTORY = Path("storage/bm25")

GRAPH_DIRECTORY = Path("storage/dependency_graph")

# Embeddings
EMBEDDING_CACHE_DIRECTORY = Path("storage/embeddings")

EMBEDDING_CACHE_FILENAME = "embedding_cache.json"