"""
agents/memory/shared_memory.py
-------------------------------
Shared Memory — the single source of truth for the entire agent pipeline.

Every agent reads from and writes to this object.
No agent communicates directly with another agent.
This object exists only for the lifetime of a single workflow execution.

Schema sections (as defined in SRS Part 7):
  - repository          : identity information
  - repository_metadata : preprocessing results (languages, frameworks, etc.)
  - understanding       : semantic knowledge (architecture, modules, APIs, etc.)
  - documentation       : generated Markdown documents
  - validation          : QA report and scores
  - revision            : revision history and counts
  - workflow            : orchestration metadata
"""

from dataclasses import dataclass, field
from typing import Any, Optional


# ---------------------------------------------------------------------------
# Section 1 — Repository Identity
# ---------------------------------------------------------------------------

@dataclass
class RepositoryInfo:
    """Basic identity information about the repository under analysis."""

    name: str = ""
    full_name: str = ""
    path: str = ""
    owner: str = ""
    branch: str = ""
    commit_sha: str = ""
    clone_url: str = ""
    clone_timestamp: str = ""
    author: str = ""           # GitHub username of the developer who pushed
    push_timestamp: str = ""   # ISO-8601 timestamp of the push event
    commit_message: str = ""   # Message of the HEAD commit in this push
    # Files touched in the triggering push event (relative paths from repo root)
    added_files: list[str] = field(default_factory=list)
    modified_files: list[str] = field(default_factory=list)


# ---------------------------------------------------------------------------
# Section 2 — Repository Metadata  (Preprocessing Agent writes this)
# ---------------------------------------------------------------------------

@dataclass
class LanguageStat:
    """Statistics for a single detected programming language."""

    language: str = ""
    file_count: int = 0
    percentage: float = 0.0


@dataclass
class RepositoryStatistics:
    """Numerical repository statistics collected during preprocessing."""

    total_files: int = 0
    total_directories: int = 0
    source_files: int = 0
    configuration_files: int = 0
    documentation_files: int = 0
    test_files: int = 0
    ignored_files: int = 0
    largest_file: str = ""
    average_file_size_bytes: float = 0.0


@dataclass
class RepositoryMetadata:
    """
    Factual metadata extracted by the Preprocessing Agent.

    The Preprocessing Agent is the ONLY writer of this section.
    """

    languages: list[LanguageStat] = field(default_factory=list)
    frameworks: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)
    dependency_files: list[str] = field(default_factory=list)
    configuration_files: list[str] = field(default_factory=list)
    entry_points: list[str] = field(default_factory=list)
    important_files: dict[str, bool] = field(default_factory=dict)
    api_specification_files: list[str] = field(default_factory=list)
    directory_tree: str = ""
    statistics: RepositoryStatistics = field(default_factory=RepositoryStatistics)
    file_classifications: dict[str, str] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Section 3 — Repository Understanding  (Understanding Agent writes this)
# ---------------------------------------------------------------------------

@dataclass
class ModuleInfo:
    """Describes a logical module identified by the Understanding Agent."""

    name: str = ""
    responsibility: str = ""
    dependencies: list[str] = field(default_factory=list)
    related_folders: list[str] = field(default_factory=list)


@dataclass
class ServiceInfo:
    """Describes an application service identified by the Understanding Agent."""

    name: str = ""
    purpose: str = ""
    inputs: list[str] = field(default_factory=list)
    outputs: list[str] = field(default_factory=list)
    dependencies: list[str] = field(default_factory=list)


@dataclass
class APIEndpoint:
    """Describes an HTTP endpoint discovered by the Understanding Agent."""

    method: str = ""
    route: str = ""
    purpose: str = ""
    request_model: str = ""
    response_model: str = ""


@dataclass
class RepositoryUnderstanding:
    """
    Semantic knowledge produced by the Understanding Agent via RAG + LLM.

    The Understanding Agent is the ONLY writer of this section.
    """

    project_summary: str = ""
    project_purpose: str = ""
    architecture_type: str = "Unknown"
    architectural_decisions: list[str] = field(default_factory=list)
    modules: list[ModuleInfo] = field(default_factory=list)
    services: list[ServiceInfo] = field(default_factory=list)
    apis: list[APIEndpoint] = field(default_factory=list)
    data_flow: list[str] = field(default_factory=list)
    dependency_graph: dict[str, list[str]] = field(default_factory=dict)
    folder_responsibilities: dict[str, str] = field(default_factory=dict)
    coding_style: dict[str, str] = field(default_factory=dict)
    design_patterns: list[str] = field(default_factory=list)
    knowledge_graph: dict[str, Any] = field(default_factory=dict)


# ---------------------------------------------------------------------------
# Section 3b — Documentation Plan  (Documentation Planning Agent writes this)
# ---------------------------------------------------------------------------

@dataclass
class DocumentationPlan:
    """
    Dynamic documentation execution strategy produced by Documentation Planning Agent.
    """

    folder_classifications: dict[str, str] = field(default_factory=dict)
    repository_docs: list[str] = field(default_factory=lambda: [
        "README.md", "ARCHITECTURE.md", "REQUIREMENTS.md", "WORKFLOW.md", "CHANGELOG.md", "SECURITY.md", "REPORTS.md"
    ])
    module_docs: list[str] = field(default_factory=list)
    file_docs: list[str] = field(default_factory=list)
    reports: list[str] = field(default_factory=lambda: [
        "dependency", "quality", "complexity", "coverage", "health", "security", "dead_code", "circular_deps"
    ])


# ---------------------------------------------------------------------------
# Section 4 — Generated Documentation  (Documentation Agent writes this)
# ---------------------------------------------------------------------------

@dataclass
class GeneratedDocumentation:
    """
    Per-file Markdown documents produced by the Documentation Agent.

    The Documentation Agent is the ONLY writer of this section.

    Attributes:
        file_docs:
            Per-file Markdown documents keyed by the file's relative path
            within the repository (e.g. 'app/api/webhook.py').
            Each value is a complete Markdown document describing that file.
    """

    readme: str = ""
    architecture: str = ""
    api: str = ""
    installation: str = ""
    developer_guide: str = ""
    folder_guide: str = ""
    workflow_guide: str = ""
    configuration_guide: str = ""
    changelog: str = ""
    system_overview: str = ""
    file_docs: dict[str, str] = field(default_factory=dict)

    def all_documents(self) -> dict[str, str]:
        """Return all non-empty documents as a {doc_name: content} dict."""
        docs = {}
        if self.readme:
            docs["README"] = self.readme
        if self.architecture:
            docs["Architecture"] = self.architecture
        if self.api:
            docs["API"] = self.api
        if self.installation:
            docs["Installation"] = self.installation
        if self.developer_guide:
            docs["Developer Guide"] = self.developer_guide
        if self.folder_guide:
            docs["Folder Structure"] = self.folder_guide
        if self.workflow_guide:
            docs["Workflow"] = self.workflow_guide
        if self.configuration_guide:
            docs["Configuration"] = self.configuration_guide
        if self.changelog:
            docs["CHANGELOG.md"] = self.changelog
        if self.system_overview:
            docs["SYSTEM_OVERVIEW.md"] = self.system_overview

        # Always merge file_docs — contains module docs, file docs, and reports.
        # Previously this was inside an `if not docs:` guard which silently
        # dropped everything once README / Architecture were populated.
        for path, content in self.file_docs.items():
            if content:
                docs[path] = content

        return docs




# ---------------------------------------------------------------------------
# Section 5 — Validation  (Validation Agent writes this)
# ---------------------------------------------------------------------------

@dataclass
class ValidationReport:
    """
    Quality assurance report produced by the Validation Agent.

    The Validation Agent is the ONLY writer of this section.
    """

    validation_status: str = ""        # PASSED | PASSED_WITH_WARNINGS | FAILED
    quality_score: float = 0.0         # 0–100
    faithfulness_score: float = 0.0    # 0–100 — LLM-judged groundedness vs RAG context
    faithfulness_notes: str = ""       # Unsupported claims found, if any
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)
    missing_sections: list[str] = field(default_factory=list)
    hallucination_findings: list[str] = field(default_factory=list)
    consistency_issues: list[str] = field(default_factory=list)
    per_document_scores: dict[str, float] = field(default_factory=dict)
    timestamp: str = ""


# ---------------------------------------------------------------------------
# Section 6 — Revision  (Revision Agent writes this)
# ---------------------------------------------------------------------------

@dataclass
class RevisionRecord:
    """A single revision entry in the revision history."""

    revision_number: int = 0
    timestamp: str = ""
    reason: str = ""
    modified_documents: list[str] = field(default_factory=list)
    summary: str = ""


@dataclass
class RevisionHistory:
    """
    Revision tracking data produced by the Revision Agent.

    The Revision Agent is the ONLY writer of this section.
    """

    revision_count: int = 0
    records: list[RevisionRecord] = field(default_factory=list)
    last_revision_timestamp: str = ""


# ---------------------------------------------------------------------------
# Section 7 — Workflow  (Coordinator writes this)
# ---------------------------------------------------------------------------

@dataclass
class WorkflowMetadata:
    """
    Orchestration metadata written by the Coordinator.

    The Coordinator is the ONLY writer of this section.
    """

    workflow_id: str = ""
    current_agent: str = ""
    current_status: str = ""
    execution_times: dict[str, float] = field(default_factory=dict)
    total_execution_time: float = 0.0
    output_directory: str = ""  # Set by SyncAgent — repo's generated_docs/ path


# ---------------------------------------------------------------------------
# Shared Memory — top-level container
# ---------------------------------------------------------------------------

@dataclass
class SharedMemory:
    """
    The single communication channel between all agents in the pipeline.

    Access rules (from SRS Part 7):
      - Every agent may READ any field.
      - Every agent may WRITE only its own designated section.
      - No agent may delete or overwrite another agent's data.

    Lifecycle:
      - Created by the Coordinator at workflow start.
      - Populated progressively by each agent.
      - Destroyed after the workflow completes (Sync Agent has saved output).

    Args:
        repository:      Identity information supplied at initialization.
        metadata:        Populated by the Preprocessing Agent.
        understanding:   Populated by the Understanding Agent.
        plan:            Populated by the Documentation Planning Agent.
        documentation:   Populated by the Documentation Agent; revised by Revision.
        validation:      Populated by the Validation Agent.
        revision:        Populated by the Revision Agent.
        workflow:        Populated by the Coordinator.
    """

    repository: RepositoryInfo = field(default_factory=RepositoryInfo)
    metadata: RepositoryMetadata = field(default_factory=RepositoryMetadata)
    understanding: RepositoryUnderstanding = field(default_factory=RepositoryUnderstanding)
    plan: DocumentationPlan = field(default_factory=DocumentationPlan)
    documentation: GeneratedDocumentation = field(default_factory=GeneratedDocumentation)
    validation: ValidationReport = field(default_factory=ValidationReport)
    revision: RevisionHistory = field(default_factory=RevisionHistory)
    workflow: WorkflowMetadata = field(default_factory=WorkflowMetadata)

    # Populated by the Coordinator when a RAGPipeline run precedes the agent
    # graph. UnderstandingAgent reads this to access pre-computed retrieval
    # context without calling the RAG pipeline a second time.
    # Set to None when RAG is not active or when the pipeline did not produce
    # a valid ContextPackage.
    rag_context_package: Optional[Any] = None
