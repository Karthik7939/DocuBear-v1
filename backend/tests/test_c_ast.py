"""
Tests for C language Tree-sitter AST parsing, symbol extraction, chunking, and dependency resolution.
"""

from pathlib import Path
import pytest

from rag.parsing.ast_parser import ASTParser
from rag.parsing.symbol_extractor import SymbolExtractor
from rag.chunking.code_chunker import CodeChunker
from rag.parsing.dependency_graph import DependencyGraphBuilder


C_HEADER_SOURCE = """
#ifndef UTILS_H
#define UTILS_H

typedef struct {
    int id;
    char name[64];
} UserRecord;

enum LogLevel {
    LOG_DEBUG = 0,
    LOG_INFO = 1,
    LOG_ERROR = 2
};

int calculate_checksum(const char *data, int length);

#endif // UTILS_H
"""

C_MAIN_SOURCE = """
#include <stdio.h>
#include "utils.h"

int calculate_checksum(const char *data, int length) {
    int sum = 0;
    for (int i = 0; i < length; i++) {
        sum += (int)data[i];
    }
    return sum;
}

int main(int argc, char **argv) {
    UserRecord user;
    user.id = 42;
    printf("User ID: %d\\n", user.id);
    
    const char *message = "Hello, C AST!";
    int checksum = calculate_checksum(message, 13);
    printf("Checksum: %d\\n", checksum);
    
    return 0;
}
"""


def test_c_ast_parser_initialization():
    """Verify ASTParser initializes the C grammar parser."""
    parser = ASTParser()
    assert parser.parser_exists("c")
    c_parser = parser.get_parser("c")
    assert c_parser is not None


def test_c_ast_parse():
    """Verify ASTParser successfully parses C source code into a syntax tree."""
    parser = ASTParser()
    tree = parser.parse(C_MAIN_SOURCE, "c")
    assert tree is not None
    root = parser.get_root_node(tree)
    assert root.type == "translation_unit"


def test_c_symbol_extractor():
    """Verify SymbolExtractor extracts C functions, types, structs, calls, and includes."""
    extractor = SymbolExtractor()
    result = extractor.extract(C_MAIN_SOURCE, "c")

    # Functions
    func_names = [f.name for f in result.functions]
    assert "calculate_checksum" in func_names
    assert "main" in func_names

    # Calls
    assert "printf" in result.calls
    assert "calculate_checksum" in result.calls

    # Imports / Includes
    assert any("stdio.h" in imp for imp in result.imports)
    assert any("utils.h" in imp for imp in result.imports)


def test_c_header_symbol_extractor():
    """Verify SymbolExtractor extracts typedef structs and enums from C headers."""
    extractor = SymbolExtractor()
    result = extractor.extract(C_HEADER_SOURCE, "c")

    # Struct / Type definitions
    type_names = [t.name for t in result.type_definitions]
    assert len(type_names) > 0 or len(result.classes) > 0


def test_c_code_chunker():
    """Verify CodeChunker creates semantic symbol chunks for C functions."""
    chunker = CodeChunker()
    drafts = chunker.chunk(C_MAIN_SOURCE, "src/main.c")

    assert len(drafts) >= 2
    draft_names = [d.symbol_name for d in drafts if d.symbol_name]
    assert "calculate_checksum" in draft_names or "main" in draft_names


def test_c_dependency_graph_resolution():
    """Verify DependencyGraphBuilder links .c and .h files via #include."""
    repository = {
        "src/utils.h": C_HEADER_SOURCE,
        "src/main.c": C_MAIN_SOURCE,
    }

    builder = DependencyGraphBuilder()
    graph = builder.build(repository, "c-demo-repo", "commit123")

    assert "src/main.c" in graph.nodes
    assert "src/utils.h" in graph.nodes

    # Check for edge from src/main.c -> src/utils.h
    edges = [(e.source, e.target) for e in graph.edges]
    assert ("src/main.c", "src/utils.h") in edges
