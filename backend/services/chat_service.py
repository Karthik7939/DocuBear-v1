"""
services/chat_service.py
--------------------------
Answers user questions about a repository by routing to whichever source of
truth actually has the answer, instead of asking the LLM to guess:

  1. File history questions ("who edited X", "when was X last changed")
     -> git log via GitService.get_file_history(). Deterministic, no LLM.
  2. File content questions ("what's in X", "show me X")
     -> raw file read from the cloned repository on disk. No LLM.
  3. Everything else
     -> LLM answer grounded in the repo's generated documentation
        (README/ARCHITECTURE/WORKFLOW/SECURITY/REPORTS/CHANGELOG) plus
        top-matching RAG code chunks for the question.

Intent + filename are detected with simple regex — matching the codebase's
existing rule-based parsing style (see understanding_agent's section
parsers) rather than spending a second LLM call just to route the question.
"""

from __future__ import annotations

import logging
import os
import re
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from agents.documentation.planner_agent import IGNORED_FOLDER_NAMES
from prompts.chat_prompt import CHAT_ANSWER_PROMPT
from services.doc_context_service import load_generated_docs, retrieve_code_context
from services.git_service import GitService
from services.repository_service import RepositoryService

logger = logging.getLogger(__name__)

_MAX_FILE_PREVIEW_CHARS = 6_000

# Backtick-quoted token wins outright (`app/page.tsx`); otherwise fall back
# to any bare word containing a dotted extension.
_FILENAME_PATTERN = re.compile(
    r"`([^`]+\.[A-Za-z0-9]{1,6})`|\b([\w][\w\-./\\]*\.[A-Za-z0-9]{1,6})\b"
)

_HISTORY_KEYWORDS = re.compile(
    r"\bwho\b.*\b(edit|edited|change|changed|modif|wrote|write|author|touch|touched|commit|committed)\b"
    r"|\bhistory of\b|\bcommit history\b"
    r"|\blast (edited|changed|modified)\b"
    r"|\bwhen was\b.*\b(changed|edited|modified|created|added)\b",
    re.IGNORECASE,
)
_CONTENT_KEYWORDS = re.compile(
    r"\bwhat(?:'s| is| does)?\b.*\b(in|inside|contain)\b"
    r"|\bshow me\b|\bcontents? of\b|\bwhat's inside\b",
    re.IGNORECASE,
)


@dataclass
class ChatMessage:
    """One turn in the conversation, as supplied by the frontend."""

    role: str      # "user" | "assistant"
    content: str


@dataclass
class ChatAnswer:
    """Result returned by ChatService.answer()."""

    answer: str
    intent: str
    sources: list[str] = field(default_factory=list)


class ChatService:
    """Answers repository questions using git history, raw files, or RAG+docs."""

    def __init__(
        self,
        repository_service: RepositoryService,
        git_service: GitService,
        llm_client,
    ) -> None:
        self._repos = repository_service
        self._git = git_service
        self._llm = llm_client

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def answer(
        self,
        repository_name: str,
        question: str,
        history: Optional[list[ChatMessage]] = None,
    ) -> ChatAnswer:
        """Answer a single question about a repository.

        Args:
            repository_name: Full repository name, e.g. 'owner/repo'.
            question:        The user's natural-language question.
            history:         Prior turns in this conversation, oldest first.

        Returns:
            ChatAnswer: answer text, the intent that was used, and any
            source files/docs the answer was grounded in.
        """
        repo_path = self._repos.get_repository_path(repository_name.replace("/", "_"))
        intent, filename_hint = self._classify(question)

        if intent == "file_history" and filename_hint:
            resolved = self._resolve_file(repo_path, filename_hint)
            if resolved:
                return self._answer_file_history(repo_path, resolved[0])
            logger.info("chat: file_history intent but no file matched '%s' — falling back", filename_hint)

        if intent == "file_content" and filename_hint:
            resolved = self._resolve_file(repo_path, filename_hint)
            if resolved:
                return self._answer_file_content(repo_path, resolved)
            logger.info("chat: file_content intent but no file matched '%s' — falling back", filename_hint)

        return self._answer_general(repository_name, repo_path, question, history or [])

    # ------------------------------------------------------------------
    # Intent classification
    # ------------------------------------------------------------------

    @staticmethod
    def _classify(question: str) -> tuple[str, Optional[str]]:
        """Return (intent, filename_hint) for a question.

        intent is one of 'file_history', 'file_content', 'general'.
        filename_hint is the best-guess filename/path token mentioned in
        the question, or None if no dotted-extension token was found.
        """
        filename_hint: Optional[str] = None
        match = _FILENAME_PATTERN.search(question)
        if match:
            filename_hint = (match.group(1) or match.group(2)).strip(".,!?;:'\"")

        if _HISTORY_KEYWORDS.search(question):
            return "file_history", filename_hint
        if _CONTENT_KEYWORDS.search(question):
            return "file_content", filename_hint
        return "general", filename_hint

    # ------------------------------------------------------------------
    # File resolution
    # ------------------------------------------------------------------

    @staticmethod
    def _resolve_file(repo_path: str, filename_hint: str) -> list[str]:
        """Resolve a filename/path hint to repo-relative path(s) on disk.

        Returns an empty list if the repo isn't cloned locally or nothing
        matches. Exact relative-path matches are preferred; otherwise every
        file whose basename matches is returned (caller decides what to do
        with more than one candidate).
        """
        root = Path(repo_path)
        if not root.is_dir():
            return []

        hint = filename_hint.replace("\\", "/").lstrip("./")

        # Fast path: the hint is already a valid relative path.
        direct = root / hint
        if direct.is_file():
            return [hint]

        target_name = hint.split("/")[-1].lower()
        matches: list[str] = []
        for dirpath, dirnames, filenames in os.walk(root):
            dirnames[:] = [
                d for d in dirnames
                if d.lower() not in IGNORED_FOLDER_NAMES and not d.startswith(".")
            ]
            for name in filenames:
                if name.lower() == target_name:
                    rel = os.path.relpath(os.path.join(dirpath, name), root)
                    matches.append(rel.replace("\\", "/"))

        return matches

    # ------------------------------------------------------------------
    # Intent handlers
    # ------------------------------------------------------------------

    def _answer_file_history(self, repo_path: str, relative_path: str) -> ChatAnswer:
        try:
            commits = self._git.get_file_history(repo_path, relative_path)
        except RuntimeError as exc:
            return ChatAnswer(
                answer=f"Couldn't read git history for `{relative_path}`: {exc}",
                intent="file_history",
                sources=[relative_path],
            )

        if not commits:
            return ChatAnswer(
                answer=f"No commit history found for `{relative_path}`.",
                intent="file_history",
                sources=[relative_path],
            )

        lines = [f"**Commit history for `{relative_path}`:**\n"]
        for c in commits:
            date = c["date"].split("T")[0]
            lines.append(f"- `{c['sha']}` **{c['author']}** — {date} — {c['message']}")

        return ChatAnswer(answer="\n".join(lines), intent="file_history", sources=[relative_path])

    def _answer_file_content(self, repo_path: str, relative_paths: list[str]) -> ChatAnswer:
        if len(relative_paths) > 1:
            listing = "\n".join(f"- `{p}`" for p in relative_paths[:20])
            return ChatAnswer(
                answer=(
                    f"Found {len(relative_paths)} files matching that name — "
                    f"which one did you mean?\n\n{listing}"
                ),
                intent="file_content",
                sources=relative_paths,
            )

        relative_path = relative_paths[0]
        full_path = Path(repo_path) / relative_path
        try:
            content = full_path.read_text(encoding="utf-8", errors="replace")
        except OSError as exc:
            return ChatAnswer(
                answer=f"Couldn't read `{relative_path}`: {exc}",
                intent="file_content",
                sources=[relative_path],
            )

        truncated = len(content) > _MAX_FILE_PREVIEW_CHARS
        preview = content[:_MAX_FILE_PREVIEW_CHARS]
        suffix = "\n\n*(truncated — file is longer than shown)*" if truncated else ""
        lang = Path(relative_path).suffix.lstrip(".")

        answer = f"**`{relative_path}`**\n\n```{lang}\n{preview}\n```{suffix}"
        return ChatAnswer(answer=answer, intent="file_content", sources=[relative_path])

    def _answer_general(
        self,
        repository_name: str,
        repo_path: str,
        question: str,
        history: list[ChatMessage],
    ) -> ChatAnswer:
        doc_context, doc_sources = load_generated_docs(repository_name)
        code_context = retrieve_code_context(repository_name, question)

        history_block = ""
        if history:
            turns = "\n".join(f"{m.role.upper()}: {m.content}" for m in history[-6:])
            history_block = f"=== CONVERSATION SO FAR ===\n{turns}\n=== END CONVERSATION ===\n"

        prompt = CHAT_ANSWER_PROMPT.format(
            repository_name=repository_name,
            doc_context=doc_context or "(No generated documentation available yet.)",
            code_context=code_context or "(No matching code context retrieved.)",
            history_block=history_block,
            question=question,
        )

        try:
            answer = self._llm.generate(prompt)
        except Exception as exc:
            logger.error("chat: LLM call failed: %s", exc)
            answer = "I couldn't generate an answer right now — the LLM call failed. Please try again."

        return ChatAnswer(answer=answer.strip(), intent="general", sources=doc_sources)
