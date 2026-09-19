"""
Repository dependency graph construction and querying.

This module builds, queries, updates and persists the repository
dependency graph used by the RAG retrieval pipeline.

The graph is file-level and is generated using information extracted
from the AST parser and symbol extractor.
"""

from __future__ import annotations

import json
import shutil
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable

from rag.config.constants import (
    DEPENDENCY_GRAPH_FILENAME,
    GRAPH_DIRECTORY,
    SUPPORTED_LANGUAGES,
)
from rag.config.settings import settings
from rag.parsing.language_detector import LanguageDetector
from rag.parsing.symbol_extractor import (
    ExtractionResult,
    SymbolExtractor,
)
from rag.schemas.graph import (
    DependencyEdge,
    DependencyGraph,
    DependencyNode,
    DependencyType,
)
from rag.utils import get_logger

logger = get_logger(__name__)


class DependencyGraphBuilder:
    """
    Builds a repository dependency graph.

    This class is responsible only for graph construction.

    It does not perform graph traversal, persistence or incremental
    updates.
    """

    def __init__(
        self,
        extractor: SymbolExtractor | None = None,
    ) -> None:
        self._extractor = extractor or SymbolExtractor()

    def build(
        self,
        repository: dict[str, str],
        repository_name: str,
        commit_sha: str,
    ) -> DependencyGraph:
        """
        Build a dependency graph for an entire repository.

        Parameters
        ----------
        repository
            Mapping of repository-relative paths to source code.

        repository_name
            Repository name.

        commit_sha
            Commit SHA corresponding to this graph.

        Returns
        -------
        DependencyGraph
        """
        logger.info("Building dependency graph...")

        extraction_results = self._extract_repository(repository)

        return self.build_from_extractions(
            extraction_results,
            repository_name,
            commit_sha,
        )

    def build_from_extractions(
        self,
        extraction_results: dict[str, ExtractionResult],
        repository_name: str,
        commit_sha: str,
    ) -> DependencyGraph:
        """
        Build a dependency graph from pre-computed extraction results.
        """
        graph = DependencyGraph(
            repository=repository_name,
            commit_sha=commit_sha,
        )

        self._create_nodes(graph, extraction_results)
        self._create_edges(graph, extraction_results)
        self._validate(graph)

        logger.info(
            "Dependency graph created (%d nodes, %d edges).",
            graph.total_nodes,
            graph.total_edges,
        )

        return graph

    def _extract_repository(
        self,
        repository: dict[str, str],
    ) -> dict[str, ExtractionResult]:
        """
        Extract symbols and imports for every file in a repository.
        """
        results: dict[str, ExtractionResult] = {}

        for file_path, source in repository.items():
            language = LanguageDetector.detect(file_path)

            if language in ("unknown", "documentation"):
                results[file_path] = ExtractionResult()
                continue

            results[file_path] = self._extractor.extract(
                source,
                language,
            )

        return results

    def _create_nodes(
        self,
        graph: DependencyGraph,
        extraction_results: dict[str, ExtractionResult],
    ) -> None:
        """
        Create graph nodes for every parsed repository file.
        """
        for file_path, extraction in extraction_results.items():
            graph.nodes[file_path] = self._build_node(
                file_path,
                extraction,
            )

    @staticmethod
    def _build_node(
        file_path: str,
        extraction: ExtractionResult,
    ) -> DependencyNode:
        """
        Construct a graph node.
        """
        symbols = [symbol.name for symbol in extraction.all_symbols]

        return DependencyNode(
            file_path=file_path,
            language=Path(file_path).suffix.lstrip("."),
            symbols=symbols,
        )

    def _create_edges(
        self,
        graph: DependencyGraph,
        extraction_results: dict[str, ExtractionResult],
    ) -> None:
        """
        Create dependency edges between repository files.
        """
        repository_files = set(extraction_results.keys())

        for source_file, extraction in extraction_results.items():
            resolved_imports = self._resolve_imports(
                source_file,
                extraction.imports,
                repository_files,
            )

            for target_file in resolved_imports:
                self._add_edge(graph, source_file, target_file)

    def _resolve_imports(
        self,
        source_file: str,
        imports: list[str],
        repository_files: set[str],
    ) -> set[str]:
        """
        Resolve imported modules to repository files.
        """
        resolved: set[str] = set()

        for module in imports:
            target = self._resolve_import(
                source_file,
                module,
                repository_files,
            )

            if target is not None:
                resolved.add(target)

        return resolved

    def _resolve_import(
        self,
        source_file: str,
        module: str,
        repository_files: set[str],
    ) -> str | None:
        """
        Resolve a single imported module.

        Returns
        -------
        Repository-relative path if found.
        """
        module = module.strip()

        if not module:
            return None

        candidates = self._import_candidates(source_file, module)

        normalized_files = {
            file_path.replace("\\", "/"): file_path
            for file_path in repository_files
        }

        for candidate in candidates:
            normalized_candidate = candidate.replace("\\", "/")

            if normalized_candidate in normalized_files:
                return normalized_files[normalized_candidate]

            for normalized_path, original_path in normalized_files.items():
                if normalized_path.endswith(f"/{normalized_candidate}"):
                    return original_path

        return None

    @staticmethod
    def _import_candidates(
        source_file: str,
        module: str,
    ) -> list[str]:
        """
        Build candidate repository paths for an import statement.
        """
        extensions = sorted(SUPPORTED_LANGUAGES.keys())
        source_dir = Path(source_file).parent

        def with_supported_extensions(base: Path | str) -> list[str]:
            base_path = str(base).replace("\\", "/")
            suffix = Path(base_path).suffix
            if suffix in extensions:
                return [base_path]

            candidates = [base_path]
            for ext in extensions:
                candidates.append(f"{base_path}{ext}")
            for ext in extensions:
                candidates.append(f"{base_path}/index{ext}")
                candidates.append(f"{base_path}/__init__{ext}")
            return candidates

        # Handle explicit file paths with known extensions (e.g., C headers #include "utils.h")
        if Path(module).suffix in extensions:
            cleaned = module.replace("\\", "/")
            candidates = []
            if cleaned.startswith("."):
                candidates.append(str(source_dir / cleaned).replace("\\", "/"))
            else:
                candidates.append(str(source_dir / cleaned).replace("\\", "/"))
                candidates.append(cleaned)
            return candidates

        if module.startswith("."):
            level = 0
            rest = module

            while rest.startswith("."):
                level += 1
                rest = rest[1:]

            base = source_dir
            for _ in range(level - 1):
                base = base.parent

            if rest:
                module_path = rest.replace(".", "/")
                return with_supported_extensions(base / module_path)

            candidates: list[str] = []
            for ext in extensions:
                candidates.append(str(base / f"index{ext}").replace("\\", "/"))
                candidates.append(str(base / f"__init__{ext}").replace("\\", "/"))
            return candidates

        module_path = module.replace(".", "/")
        return with_supported_extensions(module_path)

    @staticmethod
    def _add_edge(
        graph: DependencyGraph,
        source: str,
        target: str,
    ) -> None:
        """
        Create one dependency edge.
        """
        if source == target:
            return

        for edge in graph.edges:
            if (
                edge.source == source
                and edge.target == target
                and edge.dependency_type == DependencyType.IMPORT
            ):
                return

        graph.edges.append(
            DependencyEdge(
                source=source,
                target=target,
                dependency_type=DependencyType.IMPORT,
            )
        )

    @staticmethod
    def _validate(graph: DependencyGraph) -> None:
        """
        Validate graph consistency.
        """
        node_set = set(graph.nodes.keys())
        seen: set[tuple[str, str, DependencyType]] = set()

        for edge in graph.edges:
            if edge.source not in node_set:
                raise ValueError(
                    f"Missing source node: {edge.source}",
                )

            if edge.target not in node_set:
                raise ValueError(
                    f"Missing target node: {edge.target}",
                )

            if edge.source == edge.target:
                raise ValueError(
                    f"Self-loop detected: {edge.source}",
                )

            key = (
                edge.source,
                edge.target,
                edge.dependency_type,
            )

            if key in seen:
                raise ValueError(
                    "Duplicate dependency edge detected.",
                )

            seen.add(key)

    @staticmethod
    def statistics(graph: DependencyGraph) -> dict[str, int]:
        """
        Return graph statistics.
        """
        connected_nodes = {
            edge.source
            for edge in graph.edges
        } | {
            edge.target
            for edge in graph.edges
        }

        return {
            "nodes": graph.total_nodes,
            "edges": graph.total_edges,
            "isolated_nodes": graph.total_nodes - len(connected_nodes),
        }

    @staticmethod
    def print_summary(graph: DependencyGraph) -> None:
        """
        Log graph statistics.
        """
        stats = DependencyGraphBuilder.statistics(graph)

        logger.info("Nodes: %d", stats["nodes"])
        logger.info("Edges: %d", stats["edges"])
        logger.info("Isolated Nodes: %d", stats["isolated_nodes"])


class DependencyGraphQuery:
    """
    Read-only dependency graph traversal utilities.

    Adjacency caches are built once during initialization to avoid
    repeatedly scanning the full edge list.
    """

    def __init__(
        self,
        graph: DependencyGraph,
    ) -> None:
        self._graph = graph
        self._forward: dict[str, set[str]] = {}
        self._reverse: dict[str, set[str]] = {}
        self._build_caches()

    def _build_caches(self) -> None:
        """
        Build forward and reverse adjacency caches.
        """
        for edge in self._graph.edges:
            self._forward.setdefault(edge.source, set()).add(edge.target)
            self._reverse.setdefault(edge.target, set()).add(edge.source)

    def get_dependencies(self, file_path: str) -> set[str]:
        """
        Return files imported by the given file.
        """
        if not self._graph.has_node(file_path):
            return set()

        return set(self._forward.get(file_path, set()))

    def get_dependents(self, file_path: str) -> set[str]:
        """
        Return files that import the given file.
        """
        if not self._graph.has_node(file_path):
            return set()

        return set(self._reverse.get(file_path, set()))

    def get_neighbors(self, file_path: str) -> set[str]:
        """
        Return both dependencies and dependents of a file.
        """
        return self.get_dependencies(file_path) | self.get_dependents(
            file_path,
        )

    def one_hop(self, file_path: str) -> set[str]:
        """
        Return all files one edge away from the given file.
        """
        return self.get_neighbors(file_path)

    def two_hop(self, file_path: str) -> set[str]:
        """
        Return all files reachable within two dependency edges.
        """
        return self.bfs(file_path, depth=2)

    def bfs(
        self,
        start: str,
        depth: int = 1,
    ) -> set[str]:
        """
        Breadth-first traversal over dependencies and dependents.

        Returns every file reachable within ``depth`` hops, excluding
        the start file itself.
        """
        if depth < 1 or not self._graph.has_node(start):
            return set()

        visited: set[str] = set()
        queue: deque[tuple[str, int]] = deque([(start, 0)])

        while queue:
            current, current_depth = queue.popleft()

            if current_depth >= depth:
                continue

            for neighbor in self.get_neighbors(current):
                if neighbor in visited or neighbor == start:
                    continue

                visited.add(neighbor)
                queue.append((neighbor, current_depth + 1))

        return visited

    def dfs(
        self,
        start: str,
        max_depth: int | None = None,
    ) -> list[str]:
        """
        Depth-first traversal following import dependencies only.
        """
        if not self._graph.has_node(start):
            return []

        visited: set[str] = set()
        order: list[str] = []

        def _visit(node: str, depth: int) -> None:
            if node in visited:
                return

            if max_depth is not None and depth > max_depth:
                return

            visited.add(node)
            order.append(node)

            for dependency in sorted(self.get_dependencies(node)):
                _visit(dependency, depth + 1)

        _visit(start, 0)
        return order

    def affected_files(
        self,
        changed_files: Iterable[str],
    ) -> set[str]:
        """
        Expand changed files by dependency neighborhood.

        Returns changed files plus all files within the configured
        dependency depth.
        """
        affected = {
            file_path
            for file_path in changed_files
            if self._graph.has_node(file_path)
        }

        depth = settings.max_dependency_depth

        for file_path in changed_files:
            affected.update(self.bfs(file_path, depth=depth))

        return affected

    def path_exists(
        self,
        source: str,
        target: str,
    ) -> bool:
        """
        Check whether a directed import path exists between two files.
        """
        if source == target:
            return True

        if not self._graph.has_node(source) or not self._graph.has_node(
            target,
        ):
            return False

        visited: set[str] = set()
        stack = [source]

        while stack:
            current = stack.pop()

            if current == target:
                return True

            if current in visited:
                continue

            visited.add(current)
            stack.extend(self.get_dependencies(current))

        return False


class DependencyGraphUpdater:
    """
    Incrementally update an existing dependency graph after Git changes.
    """

    def __init__(
        self,
        builder: DependencyGraphBuilder | None = None,
        extractor: SymbolExtractor | None = None,
    ) -> None:
        self._builder = builder or DependencyGraphBuilder(
            extractor=extractor,
        )

    def update_file(
        self,
        graph: DependencyGraph,
        file_path: str,
        source: str,
    ) -> None:
        """
        Replace a file node and its outgoing import edges.
        """
        language = LanguageDetector.detect(file_path)

        if language in ("unknown", "documentation"):
            extraction = ExtractionResult()
        else:
            extraction = self._builder._extractor.extract(
                source,
                language,
            )

        graph.nodes[file_path] = DependencyGraphBuilder._build_node(
            file_path,
            extraction,
        )

        graph.edges[:] = [
            edge
            for edge in graph.edges
            if edge.source != file_path
        ]

        repository_files = set(graph.nodes.keys())
        resolved_imports = self._builder._resolve_imports(
            file_path,
            extraction.imports,
            repository_files,
        )

        for target_file in resolved_imports:
            DependencyGraphBuilder._add_edge(
                graph,
                file_path,
                target_file,
            )

        logger.debug(
            "Updated dependency graph node for %s.",
            file_path,
        )

    def add_file(
        self,
        graph: DependencyGraph,
        file_path: str,
        source: str,
    ) -> None:
        """
        Add a new file to the dependency graph.
        """
        self.update_file(graph, file_path, source)

    def delete_file(
        self,
        graph: DependencyGraph,
        file_path: str,
    ) -> None:
        """
        Remove a deleted file and all related edges.
        """
        graph.nodes.pop(file_path, None)
        graph.edges[:] = [
            edge
            for edge in graph.edges
            if edge.source != file_path and edge.target != file_path
        ]

        logger.debug(
            "Removed dependency graph node for %s.",
            file_path,
        )

    def rename_file(
        self,
        graph: DependencyGraph,
        old_path: str,
        new_path: str,
    ) -> None:
        """
        Rename a file node and rewrite all affected edges.
        """
        if old_path not in graph.nodes:
            return

        node = graph.nodes.pop(old_path)
        graph.nodes[new_path] = node.model_copy(
            update={"file_path": new_path},
        )

        updated_edges: list[DependencyEdge] = []

        for edge in graph.edges:
            source = new_path if edge.source == old_path else edge.source
            target = new_path if edge.target == old_path else edge.target

            if source == target:
                continue

            updated_edges.append(
                DependencyEdge(
                    source=source,
                    target=target,
                    dependency_type=edge.dependency_type,
                )
            )

        graph.edges[:] = updated_edges

        logger.debug(
            "Renamed dependency graph node from %s to %s.",
            old_path,
            new_path,
        )

    def apply_changes(
        self,
        graph: DependencyGraph,
        added: dict[str, str] | None = None,
        modified: dict[str, str] | None = None,
        deleted: Iterable[str] | None = None,
        renamed: dict[str, str] | None = None,
    ) -> DependencyGraph:
        """
        Apply a batch of repository changes to the graph.

        Parameters
        ----------
        added
            Mapping of new file paths to source code.

        modified
            Mapping of modified file paths to source code.

        deleted
            Iterable of deleted file paths.

        renamed
            Mapping of old file paths to new file paths.
        """
        for old_path, new_path in (renamed or {}).items():
            self.rename_file(graph, old_path, new_path)

        for file_path in deleted or []:
            self.delete_file(graph, file_path)

        for file_path, source in (modified or {}).items():
            self.update_file(graph, file_path, source)

        for file_path, source in (added or {}).items():
            self.add_file(graph, file_path, source)

        DependencyGraphBuilder._validate(graph)

        return graph


class GraphPersistence:
    """
    Persist and restore dependency graphs to disk.
    """

    def __init__(
        self,
        storage_dir: Path | None = None,
    ) -> None:
        self._storage_dir = storage_dir or (
            settings.storage_root / GRAPH_DIRECTORY
        )

    @property
    def graph_path(self) -> Path:
        """
        Default dependency graph file path.
        """
        return self._storage_dir / DEPENDENCY_GRAPH_FILENAME

    def save(
        self,
        graph: DependencyGraph,
        path: Path | None = None,
    ) -> Path:
        """
        Serialize a dependency graph to JSON.
        """
        target = path or self.graph_path
        target.parent.mkdir(parents=True, exist_ok=True)

        payload = graph.model_dump(mode="json")
        target.write_text(
            json.dumps(payload, indent=2),
            encoding="utf-8",
        )

        logger.info(
            "Saved dependency graph to %s.",
            target,
        )

        return target

    def load(
        self,
        path: Path | None = None,
    ) -> DependencyGraph:
        """
        Load a dependency graph from JSON.
        """
        target = path or self.graph_path

        if not target.exists():
            raise FileNotFoundError(
                f"Dependency graph not found: {target}",
            )

        graph = DependencyGraph.model_validate_json(
            target.read_text(encoding="utf-8"),
        )

        logger.info(
            "Loaded dependency graph from %s.",
            target,
        )

        return graph

    def backup(
        self,
        path: Path | None = None,
    ) -> Path:
        """
        Create a timestamped backup of the dependency graph file.
        """
        source = path or self.graph_path

        if not source.exists():
            raise FileNotFoundError(
                f"Dependency graph not found: {source}",
            )

        timestamp = datetime.now(timezone.utc).strftime(
            "%Y%m%dT%H%M%SZ",
        )
        backup_path = source.with_name(
            f"{source.stem}.{timestamp}.bak{source.suffix}",
        )

        shutil.copy2(source, backup_path)

        logger.info(
            "Created dependency graph backup at %s.",
            backup_path,
        )

        return backup_path
