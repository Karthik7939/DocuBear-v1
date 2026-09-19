"""
Semantic chunking for source code files.

This module splits source code at logical symbol boundaries using the
AST parser and symbol extractor. It produces content-only chunk drafts
without metadata or embeddings.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Optional

from rag.chunking.models import ChunkDraft, ChunkType, SymbolType
from rag.config.settings import settings
from rag.parsing.ast_parser import ASTParser
from rag.parsing.language_detector import LanguageDetector
from rag.parsing.symbol_extractor import SymbolExtractor
from rag.utils import get_logger
from rag.utils.tokenizer import estimate_tokens, overlap_suffix

logger = get_logger(__name__)


@dataclass(frozen=True, slots=True)
class _ChunkCandidate:
    """
    Internal representation of a code chunk boundary.
    """

    content: str
    start_line: int
    end_line: int
    symbol_name: Optional[str]
    symbol_type: SymbolType
    parent_symbol: Optional[str]


_LANGUAGE_CHUNK_NODES: dict[str, dict[str, tuple[str, ...]]] = {
    "python": {
        "decorated": ("decorated_definition",),
        "class": ("class_definition",),
        "function": ("function_definition",),
    },
    "java": {
        "decorated": (),
        "class": ("class_declaration", "interface_declaration"),
        "function": (
            "method_declaration",
            "constructor_declaration",
        ),
    },
    "javascript": {
        "decorated": (),
        "class": ("class_declaration",),
        "function": (
            "function_declaration",
            "method_definition",
            "generator_function_declaration",
        ),
    },
    "typescript": {
        "decorated": ("decorator",),
        "class": ("class_declaration",),
        "function": (
            "function_declaration",
            "method_definition",
            "generator_function_declaration",
        ),
    },
    "jsx": {
        "decorated": (),
        "class": ("class_declaration",),
        "function": (
            "function_declaration",
            "method_definition",
            "generator_function_declaration",
        ),
    },
    "tsx": {
        "decorated": ("decorator",),
        "class": ("class_declaration",),
        "function": (
            "function_declaration",
            "method_definition",
            "generator_function_declaration",
        ),
    },
    "c": {
        "decorated": (),
        "class": (
            "struct_specifier",
            "union_specifier",
            "enum_specifier",
            "type_definition",
        ),
        "function": (
            "function_definition",
        ),
    },
}


class CodeChunker:
    """
    Split source code into semantic chunk drafts.
    """

    def __init__(
        self,
        parser: ASTParser | None = None,
        extractor: SymbolExtractor | None = None,
        max_chunk_tokens: int | None = None,
        chunk_overlap: int | None = None,
    ) -> None:
        self._parser = parser or ASTParser()
        self._extractor = extractor or SymbolExtractor(
            parser=self._parser,
        )
        self._max_chunk_tokens = (
            max_chunk_tokens or settings.max_chunk_tokens
        )
        self._chunk_overlap = (
            settings.chunk_overlap if chunk_overlap is None else chunk_overlap
        )

    def chunk(
        self,
        source: str,
        file_path: str,
    ) -> list[ChunkDraft]:
        """
        Chunk one source file.
        """
        language = LanguageDetector.detect(file_path)

        if not LanguageDetector.is_code_file(file_path):
            return []

        normalized_source = source.replace("\r\n", "\n").replace(
            "\r",
            "\n",
        )

        if not normalized_source.strip():
            return []

        if not self._parser.parser_exists(language):
            return self._fallback_whole_file(
                normalized_source,
                language,
            )

        try:
            tree = self._parser.parse(
                normalized_source,
                language,
            )
        except Exception as exc:
            logger.warning(
                "AST parsing failed for %s: %s. Falling back to "
                "symbol-based extraction.",
                file_path,
                exc,
            )
            return self._fallback_symbol_chunks(
                normalized_source,
                language,
            )

        candidates = self._collect_candidates(
            tree,
            normalized_source,
            language,
        )

        if not candidates:
            return self._fallback_symbol_chunks(
                normalized_source,
                language,
            )

        drafts = self._candidates_to_drafts(
            candidates,
            language,
        )
        drafts.extend(
            self._module_drafts(
                normalized_source,
                language,
                drafts,
            ),
        )

        return self._deduplicate_drafts(drafts)

    def _collect_candidates(
        self,
        tree,
        source: str,
        language: str,
    ) -> list[_ChunkCandidate]:
        """
        Collect chunk boundaries from a syntax tree.
        """
        node_config = _LANGUAGE_CHUNK_NODES.get(language)

        if node_config is None:
            return []

        root = self._parser.get_root_node(tree)
        candidates: list[_ChunkCandidate] = []
        seen_ranges: set[tuple[int, int, str]] = set()

        for node in self._parser.walk_tree(root):
            if node.type in node_config["decorated"]:
                candidate = self._candidate_from_node(
                    node,
                    source,
                    language,
                    parent_class=self._find_parent_class(node, source),
                )
            elif node.type in node_config["class"]:
                if self._is_wrapped_by_decorated(node):
                    continue

                candidate = self._candidate_from_node(
                    node,
                    source,
                    language,
                    parent_class=self._find_parent_class(node, source),
                )
            elif node.type in node_config["function"]:
                if self._is_wrapped_by_decorated(node):
                    continue

                candidate = self._candidate_from_node(
                    node,
                    source,
                    language,
                    parent_class=self._find_parent_class(node, source),
                )
            else:
                continue

            if candidate is None:
                continue

            key = (
                candidate.start_line,
                candidate.end_line,
                candidate.symbol_name or "",
            )

            if key in seen_ranges:
                continue

            seen_ranges.add(key)
            candidates.append(candidate)

        return sorted(
            candidates,
            key=lambda item: (item.start_line, item.end_line),
        )

    def _candidate_from_node(
        self,
        node,
        source: str,
        language: str,
        parent_class: Optional[str],
    ) -> Optional[_ChunkCandidate]:
        """
        Build one chunk candidate from an AST node.
        """
        content = self._parser.get_node_text(node, source).strip()

        if not content:
            return None

        start_line, end_line = self._parser.get_node_range(node)
        symbol_name, symbol_type = self._resolve_symbol(
            node,
            source,
            language,
            parent_class,
        )

        return _ChunkCandidate(
            content=content,
            start_line=start_line,
            end_line=end_line,
            symbol_name=symbol_name,
            symbol_type=symbol_type,
            parent_symbol=parent_class,
        )

    def _split_large_content(
        self,
        content: str,
        start_line: int,
        end_line: int,
        symbol_name: Optional[str],
        symbol_type: SymbolType,
        parent_symbol: Optional[str],
    ) -> list[_ChunkCandidate]:
        """
        Split oversized symbols while preserving line boundaries.
        """
        if estimate_tokens(content) <= self._max_chunk_tokens:
            return [
                _ChunkCandidate(
                    content=content,
                    start_line=start_line,
                    end_line=end_line,
                    symbol_name=symbol_name,
                    symbol_type=symbol_type,
                    parent_symbol=parent_symbol,
                )
            ]

        lines = content.splitlines()
        pieces: list[_ChunkCandidate] = []
        current_lines: list[str] = []
        current_start = start_line

        for index, line in enumerate(lines):
            current_lines.append(line)
            current_content = "\n".join(current_lines)

            if estimate_tokens(current_content) < self._max_chunk_tokens:
                continue

            if len(current_lines) == 1:
                pieces.append(
                    _ChunkCandidate(
                        content=line,
                        start_line=current_start,
                        end_line=current_start,
                        symbol_name=symbol_name,
                        symbol_type=symbol_type,
                        parent_symbol=parent_symbol,
                    ),
                )
                current_lines = []
                current_start = current_start + 1
                continue

            kept_lines = current_lines[:-1]
            kept_content = "\n".join(kept_lines)
            kept_end = current_start + len(kept_lines) - 1
            pieces.append(
                _ChunkCandidate(
                    content=kept_content,
                    start_line=current_start,
                    end_line=kept_end,
                    symbol_name=symbol_name,
                    symbol_type=symbol_type,
                    parent_symbol=parent_symbol,
                ),
            )
            # Seed the next piece with trailing context from the piece just
            # closed, so the hard cut doesn't lose everything right at the
            # boundary. start_line moves back to where the overlap begins.
            overlap = overlap_suffix(kept_lines, self._chunk_overlap)
            current_lines = [*overlap, line]
            current_start = kept_end - len(overlap) + 1

        if current_lines:
            pieces.append(
                _ChunkCandidate(
                    content="\n".join(current_lines),
                    start_line=current_start,
                    end_line=current_start + len(current_lines) - 1,
                    symbol_name=symbol_name,
                    symbol_type=symbol_type,
                    parent_symbol=parent_symbol,
                ),
            )

        return pieces

    def _resolve_symbol(
        self,
        node,
        source: str,
        language: str,
        parent_class: Optional[str],
    ) -> tuple[Optional[str], SymbolType]:
        """
        Resolve the symbol identity for a chunk node.
        """
        definition = self._get_definition_node(node)

        if definition.type in (
            "class_definition",
            "class_declaration",
            "interface_declaration",
            "struct_specifier",
            "union_specifier",
            "enum_specifier",
            "type_definition",
        ):
            return (
                self._node_name(definition, source),
                SymbolType.CLASS,
            )

        if definition.type in (
            "function_definition",
            "function_declaration",
            "method_definition",
            "method_declaration",
            "constructor_declaration",
            "generator_function_declaration",
        ):
            name = self._node_name(definition, source)

            if name == "<anonymous>":
                return name, SymbolType.FUNCTION

            if parent_class:
                return name, SymbolType.METHOD

            return name, SymbolType.FUNCTION

        return None, SymbolType.UNKNOWN

    def _module_drafts(
        self,
        source: str,
        language: str,
        existing: list[ChunkDraft],
    ) -> list[ChunkDraft]:
        """
        Create module chunks for lines not covered by symbol chunks.
        """
        lines = source.splitlines()
        covered = self._covered_lines(existing)
        drafts: list[ChunkDraft] = []
        range_start: Optional[int] = None

        for line_number in range(1, len(lines) + 1):
            if line_number in covered:
                if range_start is not None:
                    drafts.extend(
                        self._build_module_drafts(
                            lines,
                            range_start,
                            line_number - 1,
                            language,
                        ),
                    )
                    range_start = None
                continue

            if range_start is None:
                range_start = line_number

        if range_start is not None:
            drafts.extend(
                self._build_module_drafts(
                    lines,
                    range_start,
                    len(lines),
                    language,
                ),
            )

        return drafts

    def _build_module_drafts(
        self,
        lines: list[str],
        start_line: int,
        end_line: int,
        language: str,
    ) -> list[ChunkDraft]:
        """
        Build one or more module chunk drafts from a line range.
        """
        content = "\n".join(lines[start_line - 1:end_line]).strip()

        if not content:
            return []

        candidate = _ChunkCandidate(
            content=content,
            start_line=start_line,
            end_line=end_line,
            symbol_name=None,
            symbol_type=SymbolType.MODULE,
            parent_symbol=None,
        )
        pieces = self._split_large_content(
            candidate.content,
            candidate.start_line,
            candidate.end_line,
            candidate.symbol_name,
            candidate.symbol_type,
            candidate.parent_symbol,
        )

        return [
            ChunkDraft(
                content=piece.content,
                start_line=piece.start_line,
                end_line=piece.end_line,
                language=language,
                chunk_type=ChunkType.CODE,
                symbol_name=piece.symbol_name,
                symbol_type=piece.symbol_type,
                parent_symbol=piece.parent_symbol,
            )
            for piece in pieces
        ]

    def _fallback_symbol_chunks(
        self,
        source: str,
        language: str,
    ) -> list[ChunkDraft]:
        """
        Best-effort chunking using symbol extractor line ranges.
        """
        extraction = self._extractor.extract(source, language)
        lines = source.splitlines()
        drafts: list[ChunkDraft] = []

        for symbol in extraction.all_symbols:
            if symbol.start_line > len(lines):
                continue

            end_line = min(symbol.end_line, len(lines))
            content = "\n".join(
                lines[symbol.start_line - 1:end_line],
            ).strip()

            if not content:
                continue

            symbol_type = SymbolType.UNKNOWN

            match symbol.symbol_type:
                case "class":
                    symbol_type = SymbolType.CLASS
                case "function":
                    symbol_type = SymbolType.FUNCTION
                case "method":
                    symbol_type = SymbolType.METHOD

            drafts.append(
                ChunkDraft(
                    content=content,
                    start_line=symbol.start_line,
                    end_line=end_line,
                    language=language,
                    chunk_type=ChunkType.CODE,
                    symbol_name=symbol.name,
                    symbol_type=symbol_type,
                    parent_symbol=symbol.parent,
                ),
            )

        if drafts:
            drafts.extend(
                self._module_drafts(source, language, drafts),
            )
            return self._deduplicate_drafts(drafts)

        return self._fallback_whole_file(source, language)

    def _fallback_whole_file(
        self,
        source: str,
        language: str,
    ) -> list[ChunkDraft]:
        """
        Treat the entire file as one module chunk.
        """
        content = source.strip()

        if not content:
            return []

        line_count = len(source.splitlines()) or 1

        return [
            ChunkDraft(
                content=content,
                start_line=1,
                end_line=line_count,
                language=language,
                chunk_type=ChunkType.CODE,
                symbol_name=None,
                symbol_type=SymbolType.MODULE,
            )
        ]

    def _candidates_to_drafts(
        self,
        candidates: list[_ChunkCandidate],
        language: str,
    ) -> list[ChunkDraft]:
        """
        Expand candidates into chunk drafts, splitting large symbols.
        """
        drafts: list[ChunkDraft] = []

        for candidate in candidates:
            pieces = self._split_large_content(
                candidate.content,
                candidate.start_line,
                candidate.end_line,
                candidate.symbol_name,
                candidate.symbol_type,
                candidate.parent_symbol,
            )

            for piece in pieces:
                drafts.append(
                    ChunkDraft(
                        content=piece.content,
                        start_line=piece.start_line,
                        end_line=piece.end_line,
                        language=language,
                        chunk_type=ChunkType.CODE,
                        symbol_name=piece.symbol_name,
                        symbol_type=piece.symbol_type,
                        parent_symbol=piece.parent_symbol,
                    ),
                )

        return drafts

    @staticmethod
    def _covered_lines(drafts: list[ChunkDraft]) -> set[int]:
        """
        Return line numbers already covered by chunk drafts.
        """
        covered: set[int] = set()

        for draft in drafts:
            covered.update(
                range(draft.start_line, draft.end_line + 1),
            )

        return covered

    @staticmethod
    def _deduplicate_drafts(
        drafts: list[ChunkDraft],
    ) -> list[ChunkDraft]:
        """
        Remove duplicate drafts that share the same line range and name.
        """
        seen: set[tuple[int, int, str, str]] = set()
        unique: list[ChunkDraft] = []

        for draft in drafts:
            key = (
                draft.start_line,
                draft.end_line,
                draft.symbol_name or "",
                draft.content,
            )

            if key in seen:
                continue

            seen.add(key)
            unique.append(draft)

        return unique

    @staticmethod
    def _is_wrapped_by_decorated(node) -> bool:
        """
        Check whether a node is already represented by a decorator wrapper.
        """
        parent = node.parent
        return bool(
            parent
            and parent.type
            in {
                "decorated_definition",
                "decorator",
            },
        )

    @staticmethod
    def _get_definition_node(node):
        """
        Resolve the primary definition node for symbol naming.
        """
        if node.type == "decorated_definition":
            for child in node.children:
                if child.type in {
                    "class_definition",
                    "class_declaration",
                    "function_definition",
                    "function_declaration",
                    "method_definition",
                    "method_declaration",
                    "constructor_declaration",
                    "generator_function_declaration",
                }:
                    return child

            for child in node.children:
                if child.is_named:
                    return child

        return node

    @classmethod
    def _node_name(cls, node, source: str) -> str:
        """
        Extract a symbol name from a definition node.
        """
        name_node = node.child_by_field_name("name")

        if name_node is not None:
            return ASTParser.get_node_text(name_node, source).strip()

        for field_name in ("declarator", "left", "pattern"):
            candidate = node.child_by_field_name(field_name)
            name = cls._first_identifier(candidate, source, deep=True) if candidate else ""
            if name:
                return name

        return cls._first_identifier(node, source, deep=False) or "<anonymous>"

    @classmethod
    def _first_identifier(cls, node, source: str, deep: bool = True) -> str:
        if node is None:
            return ""

        if node.type in {
            "identifier",
            "property_identifier",
            "type_identifier",
            "shorthand_property_identifier",
            "field_identifier",
        }:
            return ASTParser.get_node_text(node, source).strip()

        if not deep:
            return ""

        for child in node.children:
            name = cls._first_identifier(child, source, deep=deep)
            if name:
                return name

        return ""

    @staticmethod
    def _find_parent_class(
        node,
        source: str,
    ) -> Optional[str]:
        """
        Find the nearest enclosing class name for a node.
        """
        current = node.parent

        while current is not None:
            if current.type in {
                "class_definition",
                "class_declaration",
            }:
                name_node = current.child_by_field_name("name")

                if name_node is not None:
                    return ASTParser.get_node_text(name_node, source)

                return None

            current = current.parent

        return None
