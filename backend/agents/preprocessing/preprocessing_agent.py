"""
agents/preprocessing/preprocessing_agent.py
---------------------------------------------
Preprocessing Agent — repository scanner and metadata extractor.

Responsibilities (SRS Part 3):
- Traverse repository files recursively.
- Apply ignore rules (directories and file types).
- Detect programming languages by file extension.
- Detect frameworks using indicator files.
- Detect dependency files.
- Detect configuration files.
- Detect API specification files.
- Detect common entry points.
- Generate a simplified directory tree.
- Collect repository statistics.
- Classify each file into a category.
- Write all findings into SharedMemory.metadata.

This agent MUST NOT:
- Use LLMs.
- Generate documentation.
- Read file contents deeply (no semantic parsing).
- Clone or pull repositories.
- Generate embeddings.
- Save markdown files.
"""

import logging
import os
from pathlib import Path

from agents.coordinator.coordinator import AgentResult
from agents.memory.shared_memory import (
    SharedMemory,
    RepositoryMetadata,
    RepositoryStatistics,
    LanguageStat,
)

logger = logging.getLogger(__name__)

# ---------------------------------------------------------------------------
# Ignore rules (SRS Part 3, Sections 10 & 11)
# ---------------------------------------------------------------------------

IGNORED_DIRECTORIES: frozenset[str] = frozenset({
    ".git", ".github", ".idea", ".vscode",
    "node_modules", "venv", ".venv", "__pycache__",
    "dist", "build", "target", "coverage",
    ".next", ".cache", "pytest_cache", ".pytest_cache",
    "logs", "generated_docs", "vector_db",
    ".eggs", "htmlcov",
})

IGNORED_EXTENSIONS: frozenset[str] = frozenset({
    ".pyc", ".class", ".exe", ".dll", ".so",
    ".zip", ".rar", ".7z",
    ".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico",
    ".mp4", ".mp3", ".wav",
    ".db", ".sqlite", ".sqlite3",
    ".lock", ".bin", ".whl",
})

# ---------------------------------------------------------------------------
# Language detection map  (SRS Part 3, Section 13)
# ---------------------------------------------------------------------------

EXTENSION_TO_LANGUAGE: dict[str, str] = {
    ".py": "Python",
    ".js": "JavaScript",
    ".ts": "TypeScript",
    ".jsx": "JavaScript",
    ".tsx": "TypeScript",
    ".java": "Java",
    ".go": "Go",
    ".rs": "Rust",
    ".cpp": "C++",
    ".hpp": "C++",
    ".c": "C",
    ".h": "C",
    ".cs": "C#",
    ".rb": "Ruby",
    ".php": "PHP",
    ".swift": "Swift",
    ".kt": "Kotlin",
    ".scala": "Scala",
    ".sh": "Shell",
    ".yaml": "YAML",
    ".yml": "YAML",
    ".json": "JSON",
    ".toml": "TOML",
    ".xml": "XML",
    ".html": "HTML",
    ".css": "CSS",
    ".scss": "SCSS",
    ".md": "Markdown",
}

# ---------------------------------------------------------------------------
# Framework detection rules  (SRS Part 3, Section 14)
# ---------------------------------------------------------------------------

# Each entry: (indicator_file, keyword_in_file, framework_name)
# keyword is searched case-insensitively in the file content (first 4 KB only).
FRAMEWORK_RULES: list[tuple[str, str, str]] = [
    # Python
    ("requirements.txt", "fastapi", "FastAPI"),
    ("requirements.txt", "django", "Django"),
    ("requirements.txt", "flask", "Flask"),
    ("requirements.txt", "tornado", "Tornado"),
    ("requirements.txt", "starlette", "Starlette"),
    ("pyproject.toml", "fastapi", "FastAPI"),
    ("pyproject.toml", "django", "Django"),
    ("pyproject.toml", "flask", "Flask"),
    # JavaScript / TypeScript
    ("package.json", "\"next\"", "Next.js"),
    ("package.json", "\"react\"", "React"),
    ("package.json", "\"vue\"", "Vue.js"),
    ("package.json", "\"angular\"", "Angular"),
    ("package.json", "\"express\"", "Express"),
    ("package.json", "\"svelte\"", "Svelte"),
    ("package.json", "\"nuxt\"", "Nuxt.js"),
    # Java
    ("pom.xml", "spring-boot", "Spring Boot"),
    ("build.gradle", "spring-boot", "Spring Boot"),
]

# ---------------------------------------------------------------------------
# Dependency file names  (SRS Part 3, Section 15)
# ---------------------------------------------------------------------------

DEPENDENCY_FILES: frozenset[str] = frozenset({
    "requirements.txt", "package.json", "pom.xml",
    "build.gradle", "Cargo.toml", "go.mod",
    "composer.json", "Gemfile", "pyproject.toml",
    "setup.py", "setup.cfg", "poetry.lock",
})

# ---------------------------------------------------------------------------
# Configuration file names  (SRS Part 3, Section 16)
# ---------------------------------------------------------------------------

CONFIGURATION_FILES: frozenset[str] = frozenset({
    ".env.example", ".env", "docker-compose.yml", "Dockerfile",
    "pyproject.toml", "setup.cfg", "tox.ini", "pytest.ini",
    "mypy.ini", ".prettierrc", ".eslintrc", "tsconfig.json",
    ".eslintrc.js", ".eslintrc.json", "jest.config.js",
    "babel.config.js", "webpack.config.js", "vite.config.ts",
    "nginx.conf", "supervisord.conf",
})

# ---------------------------------------------------------------------------
# Important files  (SRS Part 3, Section 12)
# ---------------------------------------------------------------------------

IMPORTANT_FILE_NAMES: frozenset[str] = frozenset({
    "README.md", "README.rst", "LICENSE", "Dockerfile",
    "docker-compose.yml", "requirements.txt", "package.json",
    "pyproject.toml", "setup.py", "pom.xml", "build.gradle",
    "Makefile", ".env.example", ".gitignore",
})

# ---------------------------------------------------------------------------
# API specification files  (SRS Part 3, Section 17)
# ---------------------------------------------------------------------------

API_SPEC_FILES: frozenset[str] = frozenset({
    "openapi.yaml", "openapi.yml", "swagger.json", "swagger.yaml",
})

# ---------------------------------------------------------------------------
# Common entry points  (SRS Part 3, Section 18)
# ---------------------------------------------------------------------------

ENTRY_POINT_NAMES: frozenset[str] = frozenset({
    "main.py", "app.py", "server.py", "manage.py",
    "run.py", "wsgi.py", "asgi.py",
    "index.js", "server.js", "app.js",
    "main.ts", "server.ts", "App.tsx", "index.ts",
})

# ---------------------------------------------------------------------------
# File classification  (SRS Part 3, Section 21)
# ---------------------------------------------------------------------------

SOURCE_EXTENSIONS: frozenset[str] = frozenset({
    ".py", ".js", ".ts", ".jsx", ".tsx",
    ".java", ".go", ".rs", ".cpp", ".c",
    ".cs", ".rb", ".php", ".swift", ".kt", ".scala",
})

TEST_PATTERNS: tuple[str, ...] = ("test_", "_test.", ".test.", ".spec.")
DOC_EXTENSIONS: frozenset[str] = frozenset({".md", ".rst", ".txt"})
CONFIG_EXTENSIONS: frozenset[str] = frozenset({".yaml", ".yml", ".toml", ".ini", ".cfg", ".json"})

# Maximum directory tree recursion depth for very large repos
MAX_TREE_DEPTH: int = 5


# ---------------------------------------------------------------------------
# Preprocessing Agent
# ---------------------------------------------------------------------------

class PreprocessingAgent:
    """
    Scans the repository and extracts factual metadata without using any LLM.

    All findings are written to shared_memory.metadata.
    """

    def run(self, shared_memory: SharedMemory) -> AgentResult:
        """
        Execute the full preprocessing pipeline.

        Args:
            shared_memory: The shared memory object. Reads repository.path;
                           writes metadata section.

        Returns:
            AgentResult: Success or failure result for the Coordinator.
        """
        repo_path = shared_memory.repository.path

        if not repo_path or not Path(repo_path).is_dir():
            return AgentResult(
                success=False,
                message=f"Repository path does not exist: {repo_path}",
                recoverable=False,
            )

        logger.info("Repository scan started: %s", repo_path)

        try:
            metadata = self._build_metadata(repo_path)
            shared_memory.metadata = metadata
            logger.info("Shared memory updated with repository metadata")
        except Exception as exc:
            logger.exception("Preprocessing failed: %s", exc)
            return AgentResult(
                success=False,
                message=str(exc),
                recoverable=False,
            )

        logger.info("Repository scan completed: %s", repo_path)
        return AgentResult(success=True, message="Preprocessing completed successfully")

    # ------------------------------------------------------------------
    # Internal pipeline
    # ------------------------------------------------------------------

    def _build_metadata(self, repo_path: str) -> RepositoryMetadata:
        """Run all extraction steps and return a populated RepositoryMetadata.

        Args:
            repo_path: Absolute path to the repository root.

        Returns:
            RepositoryMetadata: Fully populated metadata object.
        """
        all_files = self._collect_files(repo_path)

        languages = self._detect_languages(all_files)
        logger.info("Language detection completed: %d language(s)", len(languages))

        frameworks = self._detect_frameworks(repo_path, all_files)
        logger.info("Framework detection completed: %s", frameworks)

        dep_files = self._detect_dependency_files(all_files)
        dependencies = self._extract_dependency_names(repo_path, dep_files)
        logger.info("Dependency detection completed")

        config_files = self._detect_configuration_files(all_files)
        important_files = self._detect_important_files(all_files)
        api_spec_files = self._detect_api_specs(all_files)
        entry_points = self._detect_entry_points(all_files)

        stats = self._collect_statistics(all_files, repo_path)
        logger.info("Statistics generated: total_files=%d", stats.total_files)

        tree = self._generate_directory_tree(repo_path)
        logger.info("Directory tree generated")

        return RepositoryMetadata(
            languages=languages,
            frameworks=frameworks,
            dependencies=dependencies,
            dependency_files=dep_files,
            configuration_files=config_files,
            entry_points=entry_points,
            important_files=important_files,
            api_specification_files=api_spec_files,
            directory_tree=tree,
            statistics=stats,
            file_classifications=self._classify_files(all_files),
        )

    # ------------------------------------------------------------------
    # File collection
    # ------------------------------------------------------------------

    def _collect_files(self, repo_path: str) -> list[Path]:
        """Recursively collect all non-ignored files.

        Args:
            repo_path: Root of the repository.

        Returns:
            list[Path]: Absolute paths of all included files.
        """
        result: list[Path] = []
        root = Path(repo_path)

        for dirpath, dirnames, filenames in os.walk(root):
            # Prune ignored directories in-place to prevent descent
            dirnames[:] = [
                d for d in dirnames
                if d not in IGNORED_DIRECTORIES and not d.startswith(".")
            ]
            for filename in filenames:
                file = Path(dirpath) / filename
                if file.suffix.lower() not in IGNORED_EXTENSIONS:
                    result.append(file)

        return result

    # ------------------------------------------------------------------
    # Language detection
    # ------------------------------------------------------------------

    def _detect_languages(self, files: list[Path]) -> list[LanguageStat]:
        """Count files per language and compute percentages.

        Args:
            files: All non-ignored files.

        Returns:
            list[LanguageStat]: Sorted by file_count descending.
        """
        counts: dict[str, int] = {}
        total = len(files)

        for f in files:
            lang = EXTENSION_TO_LANGUAGE.get(f.suffix.lower())
            if lang:
                counts[lang] = counts.get(lang, 0) + 1

        stats: list[LanguageStat] = []
        for lang, count in sorted(counts.items(), key=lambda x: x[1], reverse=True):
            pct = round((count / total) * 100, 1) if total else 0.0
            stats.append(LanguageStat(language=lang, file_count=count, percentage=pct))

        return stats

    # ------------------------------------------------------------------
    # Framework detection
    # ------------------------------------------------------------------

    def _detect_frameworks(self, repo_path: str, files: list[Path]) -> list[str]:
        """Detect frameworks by checking indicator file contents.

        Reads at most 4 KB from each indicator file to keep this fast.

        Args:
            repo_path: Repository root.
            files:     All non-ignored files.

        Returns:
            list[str]: De-duplicated list of detected framework names.
        """
        root = Path(repo_path)
        file_names: set[str] = {f.name for f in files}
        detected: set[str] = set()

        for indicator, keyword, framework in FRAMEWORK_RULES:
            if indicator not in file_names:
                continue
            indicator_path = root / indicator
            if not indicator_path.is_file():
                continue
            try:
                content = indicator_path.read_bytes()[:4096].decode("utf-8", errors="ignore").lower()
                if keyword.lower() in content:
                    detected.add(framework)
            except OSError:
                pass

        return sorted(detected)

    # ------------------------------------------------------------------
    # Dependency detection
    # ------------------------------------------------------------------

    def _detect_dependency_files(self, files: list[Path]) -> list[str]:
        """Return paths of detected dependency manifest files.

        Args:
            files: All non-ignored files.

        Returns:
            list[str]: Relative paths to dependency files.
        """
        return [str(f) for f in files if f.name in DEPENDENCY_FILES]

    def _extract_dependency_names(
        self, repo_path: str, dep_files: list[str]
    ) -> list[str]:
        """Extract dependency names from requirements.txt or package.json.

        Does NOT perform semantic analysis — extracts package names only.

        Args:
            repo_path:  Repository root.
            dep_files:  Paths to detected dependency files.

        Returns:
            list[str]: Sorted, de-duplicated dependency names.
        """
        deps: set[str] = set()
        for path in dep_files:
            p = Path(path)
            if p.name == "requirements.txt":
                deps.update(self._parse_requirements_txt(p))
            elif p.name == "package.json":
                deps.update(self._parse_package_json(p))
        return sorted(deps)

    @staticmethod
    def _parse_requirements_txt(path: Path) -> list[str]:
        """Extract package names from a requirements.txt file.

        Args:
            path: Path to requirements.txt.

        Returns:
            list[str]: Package names (version specifiers stripped).
        """
        names: list[str] = []
        try:
            for line in path.read_text(encoding="utf-8", errors="ignore").splitlines():
                line = line.strip()
                if not line or line.startswith("#") or line.startswith("-"):
                    continue
                # Strip version specifiers: fastapi==0.115.6 → fastapi
                for sep in ("==", ">=", "<=", "!=", "~=", ">", "<", "["):
                    line = line.split(sep)[0]
                if line:
                    names.append(line.strip())
        except OSError:
            pass
        return names

    @staticmethod
    def _parse_package_json(path: Path) -> list[str]:
        """Extract package names from a package.json file.

        Args:
            path: Path to package.json.

        Returns:
            list[str]: All dependency and devDependency names.
        """
        import json
        names: list[str] = []
        try:
            data = json.loads(path.read_text(encoding="utf-8", errors="ignore"))
            for section in ("dependencies", "devDependencies", "peerDependencies"):
                names.extend(data.get(section, {}).keys())
        except (OSError, json.JSONDecodeError):
            pass
        return names

    # ------------------------------------------------------------------
    # Configuration / important / API spec / entry point detection
    # ------------------------------------------------------------------

    def _detect_configuration_files(self, files: list[Path]) -> list[str]:
        """Return paths of detected configuration files.

        Args:
            files: All non-ignored files.

        Returns:
            list[str]: File paths.
        """
        return [str(f) for f in files if f.name in CONFIGURATION_FILES]

    def _detect_important_files(self, files: list[Path]) -> dict[str, bool]:
        """Check presence of well-known important files.

        Args:
            files: All non-ignored files.

        Returns:
            dict[str, bool]: Mapping of important file name to True/False.
        """
        found: set[str] = {f.name for f in files}
        return {name: name in found for name in IMPORTANT_FILE_NAMES}

    def _detect_api_specs(self, files: list[Path]) -> list[str]:
        """Detect OpenAPI / Swagger specification files.

        Args:
            files: All non-ignored files.

        Returns:
            list[str]: Paths of detected API spec files.
        """
        return [str(f) for f in files if f.name in API_SPEC_FILES]

    def _detect_entry_points(self, files: list[Path]) -> list[str]:
        """Detect common application entry-point files.

        Args:
            files: All non-ignored files.

        Returns:
            list[str]: Paths of detected entry-point files.
        """
        return [str(f) for f in files if f.name in ENTRY_POINT_NAMES]

    # ------------------------------------------------------------------
    # Statistics
    # ------------------------------------------------------------------

    def _collect_statistics(
        self, files: list[Path], repo_path: str
    ) -> RepositoryStatistics:
        """Compute numerical repository statistics.

        Args:
            files:     All non-ignored files.
            repo_path: Repository root (used to count total directories).

        Returns:
            RepositoryStatistics: Populated statistics object.
        """
        total_dirs = sum(
            1 for _, dirs, _ in os.walk(repo_path)
            for d in dirs if d not in IGNORED_DIRECTORIES
        )

        source = test = config = doc = 0
        sizes: list[int] = []
        largest = ""
        largest_size = 0

        for f in files:
            ext = f.suffix.lower()
            name = f.name
            size = 0
            try:
                size = f.stat().st_size
            except OSError:
                pass

            sizes.append(size)

            if size > largest_size:
                largest_size = size
                largest = str(f)

            cat = self._classify_file(name, ext)
            if cat == "Source Code":
                source += 1
            elif cat == "Test":
                test += 1
            elif cat == "Configuration":
                config += 1
            elif cat == "Documentation":
                doc += 1

        avg = round(sum(sizes) / len(sizes), 1) if sizes else 0.0

        return RepositoryStatistics(
            total_files=len(files),
            total_directories=total_dirs,
            source_files=source,
            configuration_files=config,
            documentation_files=doc,
            test_files=test,
            ignored_files=0,
            largest_file=largest,
            average_file_size_bytes=avg,
        )

    # ------------------------------------------------------------------
    # File classification
    # ------------------------------------------------------------------

    def _classify_files(self, files: list[Path]) -> dict[str, str]:
        """Classify every file into a category string.

        Args:
            files: All non-ignored files.

        Returns:
            dict[str, str]: Mapping of file path string to category.
        """
        return {
            str(f): self._classify_file(f.name, f.suffix.lower())
            for f in files
        }

    @staticmethod
    def _classify_file(name: str, ext: str) -> str:
        """Determine the category of a single file.

        Args:
            name: Filename with extension.
            ext:  Lowercase file extension.

        Returns:
            str: One of Source Code, Test, Configuration, Documentation,
                 Script, Asset, or Unknown.
        """
        name_lower = name.lower()

        if any(p in name_lower for p in TEST_PATTERNS):
            return "Test"
        if ext in SOURCE_EXTENSIONS:
            return "Source Code"
        if ext in DOC_EXTENSIONS:
            return "Documentation"
        if name in CONFIGURATION_FILES or ext in CONFIG_EXTENSIONS:
            return "Configuration"
        if ext in {".sh", ".bash", ".zsh", ".ps1", ".bat", ".cmd"}:
            return "Script"
        if ext in {".png", ".jpg", ".jpeg", ".gif", ".svg", ".ico", ".webp"}:
            return "Asset"
        return "Unknown"

    # ------------------------------------------------------------------
    # Directory tree generation
    # ------------------------------------------------------------------

    def _generate_directory_tree(self, repo_path: str) -> str:
        """Generate a simplified text directory tree.

        Limits recursion to MAX_TREE_DEPTH to avoid excessive output for
        very large repositories.

        Args:
            repo_path: Repository root.

        Returns:
            str: Indented text tree.
        """
        root = Path(repo_path)
        lines: list[str] = [root.name + "/"]
        self._build_tree(root, lines, prefix="", depth=0)
        return "\n".join(lines)

    def _build_tree(
        self,
        directory: Path,
        lines: list[str],
        prefix: str,
        depth: int,
    ) -> None:
        """Recursively build the tree lines.

        Args:
            directory: Current directory being processed.
            lines:     Accumulator list for tree lines.
            prefix:    Current indentation prefix.
            depth:     Current recursion depth.
        """
        if depth >= MAX_TREE_DEPTH:
            return

        try:
            entries = sorted(
                [e for e in directory.iterdir()
                 if e.name not in IGNORED_DIRECTORIES and not e.name.startswith(".")],
                key=lambda e: (e.is_file(), e.name.lower()),
            )
        except PermissionError:
            return

        for i, entry in enumerate(entries):
            is_last = i == len(entries) - 1
            connector = "└── " if is_last else "├── "
            lines.append(f"{prefix}{connector}{entry.name}{'/' if entry.is_dir() else ''}")

            if entry.is_dir():
                extension = "    " if is_last else "│   "
                self._build_tree(entry, lines, prefix + extension, depth + 1)
