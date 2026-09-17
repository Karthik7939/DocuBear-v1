"""
services/document_store_service.py
------------------------------------
Single source of truth for resolving generated-documentation file paths and
safely overwriting their content.

Both the Documentation page's "Request Changes" flow (app/api/documents.py
revise_document) and the voice assistant's approved-change apply step
(services/voice_tool_harness.py) need to do the exact same two things before
writing an LLM-produced revision to disk:

  1. Resolve an opaque document id back to a real file under generated_docs/,
     rejecting anything malformed or attempting path traversal.
  2. Back up the file's current content to a `.prev.md` sidecar *before*
     overwriting it, so the frontend's diff view has something to diff
     against.

Keeping this in one place means there is exactly one sidecar-backup
invariant to reason about, instead of a second copy drifting out of sync.

Note: app/api/documents.py's `save_document` (manual textarea edits) has
different, intentionally-conditional sidecar semantics -- it only backs up
if no sidecar exists yet, to preserve the original diff baseline across
repeated manual edits. That endpoint is left untouched; this module only
covers the "unconditionally back up, then overwrite" case used by
LLM-driven revisions.
"""

from __future__ import annotations

import base64
from pathlib import Path


class DocumentNotFoundError(Exception):
    """Raised when a document id/path doesn't resolve to a real file under
    generated_docs/ (malformed id, path traversal, or missing file)."""


def document_id(relative_path: Path) -> str:
    """Encode a path relative to generated_docs/ as an opaque, URL-safe id."""
    encoded = base64.urlsafe_b64encode(relative_path.as_posix().encode("utf-8"))
    return encoded.decode("ascii").rstrip("=")


def relative_path_from_id(doc_id: str) -> Path:
    """Decode an id produced by document_id() back to a relative Path.

    Raises:
        DocumentNotFoundError: if the id is malformed, absolute, escapes its
            root via '..', or doesn't end in '.md'.
    """
    try:
        padded = doc_id + "=" * (-len(doc_id) % 4)
        decoded = base64.urlsafe_b64decode(padded.encode("ascii")).decode("utf-8")
    except (UnicodeDecodeError, ValueError) as exc:
        raise DocumentNotFoundError(f"Malformed document id: {doc_id!r}") from exc

    path = Path(decoded)
    if path.is_absolute() or ".." in path.parts or path.suffix.lower() != ".md":
        raise DocumentNotFoundError(f"Document id resolves outside generated_docs/: {doc_id!r}")
    return path


def sidecar_path(doc_path: Path) -> Path:
    """Return the .prev.md sidecar path for a given .md document."""
    return doc_path.with_suffix(".prev.md")


def resolve_document_path(root: Path, doc_id: str) -> Path:
    """Resolve a document id to an absolute, existing path under root.

    Args:
        root: generated_docs/ root, already resolved (absolute).
        doc_id: opaque id as produced by document_id().

    Raises:
        DocumentNotFoundError: if the id is malformed, resolves outside
            root, or no file exists there.
    """
    relative_path = relative_path_from_id(doc_id)
    doc_path = (root / relative_path).resolve()
    if root not in doc_path.parents or not doc_path.is_file():
        raise DocumentNotFoundError(f"No document on disk for id: {doc_id!r}")
    return doc_path


def backup_and_write(doc_path: Path, new_content: str) -> str:
    """Back up doc_path's current content to a .prev.md sidecar, then
    overwrite doc_path with new_content.

    Always backs up the immediate pre-change content, even if a sidecar
    already exists — an LLM-driven overwrite should always diff against
    exactly what was there a moment ago, matching revise_document's
    pre-existing behaviour.

    Args:
        doc_path: absolute path to an existing .md document.
        new_content: content to write.

    Returns:
        str: the content that was just overwritten (the new "previous_content").

    Raises:
        OSError: if the sidecar or the document itself can't be written.
    """
    current_content = doc_path.read_text(encoding="utf-8")
    sidecar_path(doc_path).write_text(current_content, encoding="utf-8")
    doc_path.write_text(new_content, encoding="utf-8")
    return current_content
