"""
Language-neutral symbol extraction utilities built on Tree-sitter.

The extractor returns one common intermediate representation for every
parsable language: symbols, type definitions, imports, calls, and structural
operations. Query generation, AST diffing, and dependency graph construction
consume that IR instead of branching on framework or repository details.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Optional

from rag.parsing.ast_parser import ASTParser
from rag.parsing.language_detector import LanguageDetector
from rag.utils import get_logger

logger = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class ExtractedSymbol:
    """
    Represents a semantic symbol extracted from source code.
    """

    name: str
    symbol_type: str
    start_line: int
    end_line: int
    parent: Optional[str] = None
    signature: Optional[str] = None


@dataclass(slots=True)
class ExtractionResult:
    """
    Stores semantic structure extracted from one file.
    """

    classes: list[ExtractedSymbol] = field(default_factory=list)
    functions: list[ExtractedSymbol] = field(default_factory=list)
    methods: list[ExtractedSymbol] = field(default_factory=list)
    type_definitions: list[ExtractedSymbol] = field(default_factory=list)
    variables: list[ExtractedSymbol] = field(default_factory=list)
    imports: list[str] = field(default_factory=list)
    calls: list[str] = field(default_factory=list)
    operations: list[str] = field(default_factory=list)
    data_flows: list[str] = field(default_factory=list)

    @property
    def all_symbols(self) -> list[ExtractedSymbol]:
        """
        Return every extracted code symbol.
        """

        return (
            self.classes
            + self.functions
            + self.methods
            + self.type_definitions
            + self.variables
        )


class SymbolExtractor:
    """
    Extract semantic structure from Tree-sitter ASTs.
    """

    _CLASS_NODES = {
        "class_definition",
        "class_declaration",
        "interface_declaration",
        "struct_item",
        "struct_declaration",
        "struct_specifier",
        "union_specifier",
        "trait_item",
        "enum_declaration",
        "enum_item",
        "enum_specifier",
    }

    _FUNCTION_NODES = {
        "function_definition",
        "function_declaration",
        "generator_function_declaration",
        "method_declaration",
        "method_definition",
        "constructor_declaration",
        "arrow_function",
        "function",
        "function_item",
    }

    _TYPE_NODES = {
        "type_alias_declaration",
        "type_alias",
        "type_definition",
        "interface_declaration",
        "enum_declaration",
        "enum_item",
        "enum_specifier",
        "struct_item",
        "struct_declaration",
        "struct_specifier",
        "union_specifier",
        "trait_item",
    }

    _VARIABLE_NODES = {
        "variable_declarator",
        "lexical_declaration",
        "const_declaration",
        "assignment",
        "assignment_expression",
        "public_field_definition",
        "field_definition",
    }

    _IMPORT_NODES = {
        "import_statement",
        "import_from_statement",
        "import_declaration",
        "import_clause",
        "use_declaration",
        "use_item",
        "using_directive",
        "package_import",
        "require_call",
        "preproc_include",
        "preproc_def",
    }

    _CALL_NODES = {
        "call",
        "call_expression",
        "method_invocation",
        "invocation_expression",
    }

    _CONTROL_OPERATION_NODES = {
        "if_statement": "conditional branching",
        "for_statement": "iteration",
        "for_in_statement": "iteration",
        "while_statement": "iteration",
        "do_statement": "iteration",
        "switch_statement": "branch selection",
        "try_statement": "error handling",
        "catch_clause": "error handling",
        "return_statement": "return value",
        "await_expression": "asynchronous operation",
    }

    def __init__(self, parser: ASTParser | None = None) -> None:
        self.parser = parser or ASTParser()

    def extract(self, source: str, language: str) -> ExtractionResult:
        """
        Extract semantic symbols and implementation hints from source code.
        """

        if not self.parser.parser_exists(language):
            logger.warning(
                "Parser not available for %s; using lexical semantic extraction.",
                language,
            )
            return self._extract_lexical(source)

        tree = self.parser.parse(source, language)
        result = ExtractionResult()
        root = self.parser.get_root_node(tree)

        self._walk(root, source, result, parent=None, scope="module")
        result.imports = self._ordered_unique(result.imports)
        result.calls = self._ordered_unique(result.calls)
        result.operations = self._ordered_unique(result.operations)
        result.data_flows = self._ordered_unique(result.data_flows)

        return result

    def _extract_lexical(self, source: str) -> ExtractionResult:
        """
        Best-effort semantic extraction when no Tree-sitter grammar is loaded.
        """

        result = ExtractionResult()
        lines = source.splitlines()

        import_patterns = [
            r"\bfrom\s+['\"]([^'\"]+)['\"]",
            r"\bimport\s+['\"]([^'\"]+)['\"]",
            r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]",
            r"^\s*from\s+([A-Za-z0-9_./@-]+)\s+import\b",
            r"^\s*import\s+([A-Za-z0-9_.,\s/@-]+)",
        ]
        symbol_patterns = [
            ("class", r"\bclass\s+([A-Za-z_][A-Za-z0-9_]*)"),
            ("interface", r"\binterface\s+([A-Za-z_][A-Za-z0-9_]*)"),
            ("type", r"\btype\s+([A-Za-z_][A-Za-z0-9_]*)"),
            ("enum", r"\benum\s+([A-Za-z_][A-Za-z0-9_]*)"),
            ("struct", r"\bstruct\s+([A-Za-z_][A-Za-z0-9_]*)"),
            ("trait", r"\btrait\s+([A-Za-z_][A-Za-z0-9_]*)"),
            ("function", r"\bfunction\s+([A-Za-z_][A-Za-z0-9_]*)"),
            ("function", r"\bdef\s+([A-Za-z_][A-Za-z0-9_]*)"),
            ("function", r"\b(?:const|let|var)\s+([A-Za-z_][A-Za-z0-9_]*)\s*=\s*(?:async\s*)?\(?[^=]*?\)?\s*=>"),
        ]

        for index, line in enumerate(lines, start=1):
            for pattern in import_patterns:
                for match in re.finditer(pattern, line):
                    for item in match.group(1).split(","):
                        cleaned = item.strip()
                        if cleaned:
                            result.imports.append(cleaned)

            for symbol_type, pattern in symbol_patterns:
                match = re.search(pattern, line)
                if not match:
                    continue
                symbol = ExtractedSymbol(
                    name=match.group(1),
                    symbol_type=symbol_type,
                    start_line=index,
                    end_line=index,
                    signature=line.strip(),
                )
                self._append_symbol(result, symbol)

            for call_match in re.finditer(r"\b([A-Za-z_][A-Za-z0-9_.]*)\s*\(", line):
                result.calls.append(call_match.group(1))

        result.imports = self._ordered_unique(result.imports)
        result.calls = self._ordered_unique(result.calls)
        return result

    def extract_file(self, file_path: str) -> ExtractionResult:
        """
        Extract symbols from a repository file.
        """

        language = LanguageDetector.detect(file_path)
        if language in ("unknown", "documentation"):
            return ExtractionResult()

        with open(file_path, "r", encoding="utf-8", errors="replace") as file:
            source = file.read()

        return self.extract(source, language)

    def find_symbol(
        self,
        result: ExtractionResult,
        symbol_name: str,
    ) -> ExtractedSymbol | None:
        for symbol in result.all_symbols:
            if symbol.name == symbol_name:
                return symbol
        return None

    def has_symbol(self, result: ExtractionResult, symbol_name: str) -> bool:
        return self.find_symbol(result, symbol_name) is not None

    def symbols_by_type(
        self,
        result: ExtractionResult,
        symbol_type: str,
    ) -> list[ExtractedSymbol]:
        return [
            symbol
            for symbol in result.all_symbols
            if symbol.symbol_type == symbol_type
        ]

    def symbol_count(self, result: ExtractionResult) -> int:
        return len(result.all_symbols)

    def import_count(self, result: ExtractionResult) -> int:
        return len(result.imports)

    def statistics(self, result: ExtractionResult) -> dict[str, int]:
        return {
            "classes": len(result.classes),
            "functions": len(result.functions),
            "methods": len(result.methods),
            "types": len(result.type_definitions),
            "variables": len(result.variables),
            "imports": len(result.imports),
            "calls": len(result.calls),
            "operations": len(result.operations),
            "data_flows": len(result.data_flows),
            "total_symbols": len(result.all_symbols),
        }

    def print_summary(self, result: ExtractionResult) -> None:
        stats = self.statistics(result)
        logger.info(
            "Classes=%d Functions=%d Methods=%d Types=%d Variables=%d Imports=%d",
            stats["classes"],
            stats["functions"],
            stats["methods"],
            stats["types"],
            stats["variables"],
            stats["imports"],
        )

    def symbol_names(self, result: ExtractionResult) -> list[str]:
        return [symbol.name for symbol in result.all_symbols]

    def symbols_in_range(
        self,
        result: ExtractionResult,
        start_line: int,
        end_line: int,
    ) -> list[ExtractedSymbol]:
        return [
            symbol
            for symbol in result.all_symbols
            if symbol.end_line >= start_line and symbol.start_line <= end_line
        ]

    def methods_of_class(
        self,
        result: ExtractionResult,
        class_name: str,
    ) -> list[ExtractedSymbol]:
        return [
            method
            for method in result.methods
            if method.parent == class_name
        ]

    def validate(self, result: ExtractionResult) -> bool:
        names = set()
        for symbol in result.all_symbols:
            key = (symbol.name, symbol.start_line, symbol.symbol_type)
            if key in names:
                return False
            names.add(key)
        return True

    def clear(self) -> None:
        logger.debug("Symbol extractor cleared.")

    def _walk(
        self,
        node,
        source: str,
        result: ExtractionResult,
        parent: str | None,
        scope: str,
    ) -> None:
        node_type = node.type
        symbol = self._symbol_from_node(node, source, parent, scope)
        child_parent = parent
        child_scope = scope

        if symbol:
            self._append_symbol(result, symbol)
            if symbol.symbol_type in {"class", "interface", "struct", "enum", "trait"}:
                child_parent = symbol.name
                child_scope = "class"
            elif symbol.symbol_type in {"function", "method"}:
                child_scope = "function"

        if node_type in self._IMPORT_NODES or "import" in node_type:
            result.imports.extend(self._extract_imports_from_text(node, source))

        if node_type in self._CALL_NODES:
            call_name = self._extract_call_name(node, source)
            if call_name:
                result.calls.append(call_name)

        operation = self._CONTROL_OPERATION_NODES.get(node_type)
        if operation:
            result.operations.append(operation)

        data_flow = self._assignment_data_flow(node, source)
        if data_flow:
            result.data_flows.append(data_flow)

        for child in node.children:
            self._walk(child, source, result, child_parent, child_scope)

    def _symbol_from_node(
        self,
        node,
        source: str,
        parent: str | None,
        scope: str,
    ) -> ExtractedSymbol | None:
        node_type = node.type
        if not node.is_named:
            return None

        if node_type in self._CLASS_NODES and scope in {"module", "class"}:
            symbol_type = self._class_symbol_type(node_type)
            return self._build_symbol(node, source, symbol_type, parent=None)

        if node_type in self._FUNCTION_NODES and scope in {"module", "class"}:
            name = self._node_name(node, source)
            if name == "<anonymous>":
                name = self._name_from_parent_assignment(node, source)
            if not name or name == "<anonymous>":
                return None
            symbol_type = "method" if parent else "function"
            return self._build_symbol(node, source, symbol_type, parent, name=name)

        if node_type in self._TYPE_NODES and scope in {"module", "class"}:
            symbol_type = self._class_symbol_type(node_type)
            return self._build_symbol(node, source, symbol_type, parent=None)

        if node_type in self._VARIABLE_NODES and scope in {"module", "class"}:
            if self._contains_function_child(node):
                name = self._node_name(node, source)
                if name and name != "<anonymous>":
                    return self._build_symbol(node, source, "function", parent, name=name)
            elif self._is_meaningful_field(node):
                name = self._node_name(node, source)
                if name and name != "<anonymous>":
                    return self._build_symbol(node, source, "variable", parent, name=name)

        return None

    def _build_symbol(
        self,
        node,
        source: str,
        symbol_type: str,
        parent: str | None,
        name: str | None = None,
    ) -> ExtractedSymbol:
        start, end = self.parser.get_node_range(node)
        resolved_name = name or self._node_name(node, source) or "<anonymous>"
        signature = self.parser.get_node_text(node, source).split("\n")[0].strip()
        return ExtractedSymbol(
            name=resolved_name,
            symbol_type=symbol_type,
            start_line=start,
            end_line=end,
            parent=parent,
            signature=signature,
        )

    def _append_symbol(self, result: ExtractionResult, symbol: ExtractedSymbol) -> None:
        if symbol.name == "<anonymous>":
            return

        target = result.functions
        if symbol.symbol_type == "class":
            target = result.classes
        elif symbol.symbol_type == "method":
            target = result.methods
        elif symbol.symbol_type in {"interface", "type", "enum", "struct", "trait"}:
            target = result.type_definitions
        elif symbol.symbol_type == "variable":
            target = result.variables

        key = (symbol.parent, symbol.name, symbol.symbol_type, symbol.start_line)
        if any((item.parent, item.name, item.symbol_type, item.start_line) == key for item in target):
            return
        target.append(symbol)

    def _node_name(self, node, source: str) -> str:
        name_node = node.child_by_field_name("name")
        if name_node is not None:
            return self.parser.get_node_text(name_node, source).strip()

        for field_name in ("declarator", "left", "pattern"):
            candidate = node.child_by_field_name(field_name)
            name = self._first_identifier(candidate, source, deep=True) if candidate else ""
            if name:
                return name

        return self._first_identifier(node, source, deep=False) or "<anonymous>"

    def _first_identifier(self, node, source: str, deep: bool = True) -> str:
        if node is None:
            return ""

        if node.type in {
            "identifier",
            "property_identifier",
            "type_identifier",
            "shorthand_property_identifier",
        }:
            return self.parser.get_node_text(node, source).strip()

        if not deep:
            return ""

        for child in node.children:
            name = self._first_identifier(child, source, deep=deep)
            if name:
                return name

        return ""

    def _name_from_parent_assignment(self, node, source: str) -> str:
        parent = getattr(node, "parent", None)
        while parent is not None:
            if parent.type in self._VARIABLE_NODES:
                name = self._node_name(parent, source)
                if name and name != "<anonymous>":
                    return name
            parent = getattr(parent, "parent", None)
        return ""

    def _assignment_data_flow(self, node, source: str) -> str:
        """Return a generic assignment edge when the grammar exposes one.

        Tree-sitter grammars commonly expose ``left`` and ``right`` fields for
        assignments.  The edge is kept as traceability evidence; no meaning is
        inferred from either identifier here.
        """
        if "assignment" not in node.type:
            return ""

        target = node.child_by_field_name("left")
        value = node.child_by_field_name("right")
        if target is None or value is None:
            return ""

        target_name = self._first_identifier(target, source)
        value_name = self._first_identifier(value, source)
        if not target_name or not value_name:
            return ""
        return f"{target_name} <- {value_name}"

    def _contains_function_child(self, node) -> bool:
        for child in node.children:
            if child.type in self._FUNCTION_NODES:
                return True
            if child.type not in self._VARIABLE_NODES and self._contains_function_child(child):
                return True
        return False

    @staticmethod
    def _is_meaningful_field(node) -> bool:
        return node.type in {"public_field_definition", "field_definition"}

    @staticmethod
    def _class_symbol_type(node_type: str) -> str:
        if "interface" in node_type:
            return "interface"
        if "type_alias" in node_type or node_type == "type_definition":
            return "type"
        if "enum" in node_type:
            return "enum"
        if "struct" in node_type or "union" in node_type:
            return "struct"
        if "trait" in node_type:
            return "trait"
        return "class"

    def _extract_imports_from_text(self, node, source: str) -> list[str]:
        text = self.parser.get_node_text(node, source).strip()
        imports: list[str] = []

        imports.extend(
            match.group(1)
            for match in re.finditer(r"\bfrom\s+['\"]([^'\"]+)['\"]", text)
        )
        imports.extend(
            match.group(1)
            for match in re.finditer(r"\bimport\s+['\"]([^'\"]+)['\"]", text)
        )
        imports.extend(
            match.group(1)
            for match in re.finditer(r"\brequire\s*\(\s*['\"]([^'\"]+)['\"]", text)
        )
        imports.extend(
            match.group(1)
            for match in re.finditer(r'#include\s+[<"]([^>"]+)[>"]', text)
        )

        if not imports and text.startswith("import "):
            imports.extend(self._parse_python_import_statement(text))
        elif not imports and text.startswith("from "):
            module = self._parse_python_import_from_statement(text)
            if module:
                imports.append(module)

        if not imports:
            imports.extend(self._string_literals(node, source))

        return [import_name for import_name in self._ordered_unique(imports) if import_name]

    def _string_literals(self, node, source: str) -> list[str]:
        values: list[str] = []
        for child in self.parser.walk_tree(node):
            if child.type in {
                "string",
                "string_fragment",
                "interpreted_string_literal",
                "string_literal",
                "system_lib_string",
                "header_name",
            }:
                text = self.parser.get_node_text(child, source).strip()
                text = text.strip("\"'<>`")
                if text:
                    values.append(text)
        return values

    def _extract_call_name(self, node, source: str) -> str:
        function_node = node.child_by_field_name("function")
        if function_node is not None:
            return self._qualified_name(function_node, source)
        return self._qualified_name(node.children[0], source) if node.children else ""

    def _qualified_name(self, node, source: str) -> str:
        text = self.parser.get_node_text(node, source).strip()
        text = re.sub(r"\s+", "", text)
        return text[:120]

    @staticmethod
    def _parse_python_import_statement(statement: str) -> list[str]:
        first_line = statement.splitlines()[0].strip()
        if not first_line.startswith("import "):
            return []

        statement_body = first_line.replace("import ", "", 1)
        modules = []
        for item in statement_body.split(","):
            item = item.strip()
            if " as " in item:
                item = item.split(" as ")[0]
            if item:
                modules.append(item)
        return modules

    @staticmethod
    def _parse_python_import_from_statement(statement: str) -> str | None:
        first_line = statement.splitlines()[0].strip()
        if not first_line.startswith("from "):
            return None
        return first_line.replace("from ", "", 1).split(" import ", 1)[0].strip()

    @staticmethod
    def _ordered_unique(values: list[str]) -> list[str]:
        seen: set[str] = set()
        ordered: list[str] = []
        for value in values:
            cleaned = value.strip()
            key = cleaned.lower()
            if not cleaned or key in seen:
                continue
            seen.add(key)
            ordered.append(cleaned)
        return ordered
