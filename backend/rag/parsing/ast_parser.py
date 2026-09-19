"""
Tree-sitter based AST parser.

This module provides language-independent parsing of source code into
Tree-sitter syntax trees.

The parser itself does NOT extract symbols or dependencies.
Those responsibilities belong to symbol_extractor.py and
dependency_graph.py.
"""

from __future__ import annotations

from pathlib import Path

from tree_sitter import Language, Parser

from tree_sitter_python import language as python_language
from tree_sitter_java import language as java_language
from tree_sitter_javascript import language as javascript_language
from tree_sitter_typescript import (
    language_tsx,
    language_typescript,
)
from tree_sitter_c import language as c_language

from rag.parsing.language_detector import LanguageDetector
from rag.utils import get_logger

logger = get_logger(__name__)

_LANGUAGE_REGISTRY = {
    "python": python_language,
    "java": java_language,
    "javascript": javascript_language,
    "jsx": javascript_language,
    "typescript": language_typescript,
    "tsx": language_tsx,
    "c": c_language,
}


class ASTParser:
    """
    Tree-sitter parser wrapper.
    """

    def __init__(self) -> None:

        self.parsers: dict[str, Parser] = {}

        self._initialize_parsers()

    
    def _initialize_parsers(self) -> None:
        """
        Create one parser per supported language.
        """

        for language_name, language_fn in _LANGUAGE_REGISTRY.items():

            parser = Parser()

            parser.language = Language(language_fn())

            self.parsers[language_name] = parser

        logger.info(
            "Initialized %d Tree-sitter parsers.",
            len(self.parsers),
        )


    def get_parser(
        self,
        language: str,
    ) -> Parser:
        """
        Returns the parser for a language.
        """

        if language not in self.parsers:

            raise ValueError(
                f"Unsupported language: {language}"
            )

        return self.parsers[language]
    
    def parse(
        self,
        source: str,
        language: str,
    ):
        """
        Parse source code into a syntax tree.
        """

        parser = self.get_parser(language)

        tree = parser.parse(
            bytes(source, "utf-8")
        )

        return tree

    def parse_file(
        self,
        file_path: str | Path,
    ):
        """
        Parse a repository file.
        """

        language = LanguageDetector.detect(
            file_path
        )

        if language == "documentation":

            raise ValueError(
                "Documentation files cannot be parsed."
            )

        with open(
            file_path,
            "r",
            encoding="utf-8",
            errors="replace",
        ) as file:

            source = file.read()

        return self.parse(
            source,
            language,
        )
    
    def get_root_node(self, tree):
        """
        Return the root node of a syntax tree.

        Parameters
        ----------
        tree
            Tree-sitter syntax tree.

        Returns
        -------
        Node
            Root node.
        """

        return tree.root_node

    def walk_tree(self, node):
        """
        Perform a depth-first traversal of the syntax tree.

        Parameters
        ----------
        node
            Starting node.

        Yields
        ------
        Node
            Every node in the subtree.
        """

        yield node

        for child in node.children:
            yield from self.walk_tree(child)

    def iter_children(self, node):
        """
        Iterate over the direct children of a node.

        Parameters
        ----------
        node
            Tree-sitter node.

        Yields
        ------
        Node
            Child nodes.
        """

        for child in node.children:
            yield child

    def find_nodes_by_type(
        self,
        tree,
        node_type: str,
    ) -> list:
        """
        Find all nodes of a specific type.

        Parameters
        ----------
        tree
            Tree-sitter syntax tree.

        node_type : str

        Returns
        -------
        list
            Matching nodes.
        """

        root = self.get_root_node(tree)

        return [
            node
            for node in self.walk_tree(root)
            if node.type == node_type
        ]

    def find_first_node(
        self,
        tree,
        node_type: str,
    ):
        """
        Find the first node of the given type.

        Parameters
        ----------
        tree
            Tree-sitter syntax tree.

        node_type : str

        Returns
        -------
        Node | None
        """

        root = self.get_root_node(tree)

        for node in self.walk_tree(root):

            if node.type == node_type:
                return node

        return None

    def count_nodes(
        self,
        tree,
    ) -> int:
        """
        Count the total number of nodes in a syntax tree.

        Parameters
        ----------
        tree
            Tree-sitter syntax tree.

        Returns
        -------
        int
        """

        root = self.get_root_node(tree)

        return sum(
            1
            for _ in self.walk_tree(root)
        )
    
    @staticmethod
    def get_node_text(
        node,
        source: str,
    ) -> str:
        """
        Extract the source text represented by a node.

        Parameters
        ----------
        node

        source : str

        Returns
        -------
        str
        """

        source_bytes = source.encode("utf-8")

        return source_bytes[
            node.start_byte:node.end_byte
        ].decode("utf-8", errors="replace")

    @staticmethod
    def get_node_range(
        node,
    ) -> tuple[int, int]:
        """
        Return the line range occupied by a node.

        Parameters
        ----------
        node

        Returns
        -------
        tuple[int, int]
            (start_line, end_line)
        """

        return (
            node.start_point[0] + 1,
            node.end_point[0] + 1,
        )

    @staticmethod
    def is_named_node(
        node,
    ) -> bool:
        """
        Determine whether a node is a named syntax node.

        Parameters
        ----------
        node

        Returns
        -------
        bool
        """

        return node.is_named

    @staticmethod
    def has_children(
        node,
    ) -> bool:
        """
        Check whether a node has children.

        Parameters
        ----------
        node

        Returns
        -------
        bool
        """

        return len(node.children) > 0
    
    def parse_repository_file(
        self,
        file_path: str | Path,
    ):
        """
        Parse a repository file after validating that it is supported.

        Parameters
        ----------
        file_path : str | Path

        Returns
        -------
        Tree

        Raises
        ------
        ValueError
            If the file type is unsupported.
        """

        path = Path(file_path)

        language = LanguageDetector.detect(path)

        if language == "unknown":
            raise ValueError(
                f"Unsupported language for file: {path}"
            )

        if language == "documentation":
            raise ValueError(
                "Documentation files cannot be parsed into an AST."
            )

        source = path.read_text(
            encoding="utf-8",
            errors="replace",
        )

        return self.parse(source, language)

    def validate_tree(
        self,
        tree,
    ) -> bool:
        """
        Validate a parsed syntax tree.

        Parameters
        ----------
        tree

        Returns
        -------
        bool
        """

        if tree is None:
            return False

        return tree.root_node is not None

    def has_syntax_errors(
        self,
        tree,
    ) -> bool:
        """
        Check whether the syntax tree contains parsing errors.

        Parameters
        ----------
        tree

        Returns
        -------
        bool
        """

        root = tree.root_node

        for node in self.walk_tree(root):

            if node.has_error:
                return True

        return False
    
    @property
    def supported_languages(
        self,
    ) -> list[str]:
        """
        Returns the languages supported by this parser.
        """

        return sorted(
            self.parsers.keys()
        )

    def parser_exists(
        self,
        language: str,
    ) -> bool:
        """
        Check whether a parser exists.

        Parameters
        ----------
        language : str

        Returns
        -------
        bool
        """

        return language in self.parsers
    
    def tree_statistics(
        self,
        tree,
    ) -> dict[str, int]:
        """
        Compute basic statistics for a syntax tree.

        Parameters
        ----------
        tree

        Returns
        -------
        dict
        """

        root = tree.root_node

        total_nodes = 0
        named_nodes = 0

        for node in self.walk_tree(root):

            total_nodes += 1

            if node.is_named:
                named_nodes += 1

        return {
            "total_nodes": total_nodes,
            "named_nodes": named_nodes,
        }
    
    def print_tree(
        self,
        tree,
        max_depth: int = 3,
    ) -> None:
        """
        Pretty-print the syntax tree.

        Parameters
        ----------
        tree

        max_depth : int
        """

        root = tree.root_node

        self._print_node(
            root,
            depth=0,
            max_depth=max_depth,
        )

    def _print_node(
        self,
        node,
        depth: int,
        max_depth: int,
    ) -> None:

        if depth > max_depth:
            return

        indent = "    " * depth

        logger.debug(
            "%s%s",
            indent,
            node.type,
        )

        for child in node.children:

            self._print_node(
                child,
                depth + 1,
                max_depth,
            )

    def clear(self) -> None:
        """
        Clear parser cache.

        Tree-sitter parsers are reusable, so this method currently
        performs no operation. It exists for future extensibility.
        """

        logger.debug(
            "Parser cache cleared."
        )
