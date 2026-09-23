"""
prompts/documentation_prompt.py
---------------------------------
Prompt templates for the Documentation Agent.

Rules (SRS Part 8, Section 7):
- Prompts must NOT be embedded inside agent code.
- Each template uses {placeholder} slots filled by the generator.

Documentation structure:
  1. README.md          — Project overview, setup, usage, API reference
  2. ARCHITECTURE.md    — System design, components, data flow, dependencies
  3. REQUIREMENTS.md    — Functional and non-functional requirements specification
  4. WORKFLOW.md        — End-to-end process flowcharts (Mermaid)
  5. CHANGELOG.md       — Recent commit history and changes (prepend-only)
  6. SECURITY.md        — Security model, risks, and recommendations
  7. REPORTS.md         — Deterministic code reports (no LLM call)

Incremental update strategy:
  - README, ARCHITECTURE, REQUIREMENTS, WORKFLOW, SECURITY: LLM receives the existing
    document and updates ONLY the sections affected by the current push.
    All other sections are copied word-for-word to prevent unnecessary
    diff noise.
  - CHANGELOG: LLM generates ONLY the new entry for this push. The agent
    prepends it to the existing file — old entries are never touched.
"""


# ---------------------------------------------------------------------------
# README.md — incremental update
# ---------------------------------------------------------------------------

REPO_OVERVIEW_PROMPT: str = """\
You are a senior technical writer maintaining the README for a software project.
A new push has been made. Update the README to reflect the changes.

CRITICAL RULES:
- If an existing README is provided below, copy every section WORD-FOR-WORD
  EXCEPT sections that are directly affected by the changed files.
- Only rewrite sections that need updating based on the changed files.
- Do NOT rephrase, reorder, or reformat sections that are not affected.
- If no existing README is provided, generate a complete README from scratch.
- STRICT GROUNDING: Do NOT invent or hallucinate any file paths, directories, API endpoints, or frameworks that are not present in the provided Code Context or Project Summary.

Repository: {repository_name}
Branch: {branch}
Primary Languages: {languages}
Detected Frameworks: {frameworks}
Author of latest push: {author}

Files changed in this push:
{changed_files}

Project Summary:
{project_summary}

Project Purpose:
{project_purpose}

Architecture Type: {architecture_type}

Identified Modules:
{modules}

Detected Entry Points:
{entry_points}

Detected Dependencies:
{dependencies}

API Endpoints Identified:
{apis}

Data Flow:
{data_flow}

=== EXISTING README (copy unchanged sections exactly) ===
{existing_content}
=== END EXISTING README ===

=== RETRIEVED CODE CONTEXT ===
{rag_context}
=== END CONTEXT ===

Output the complete updated README.md with exactly these sections:

# {repo_name}

## Overview
2–3 paragraphs: what this project does, who it is for, and why it exists.

## Tech Stack
Bulleted list of languages, frameworks, and key dependencies.

## Project Structure
Table of main folders:
| Folder | Description |

## Key Features
Bulleted list of the main capabilities.

## Getting Started
### Prerequisites
### Installation
### Running the Application

## API Reference
| Method | Route | Description | Request Body | Response |

## Environment Variables
| Variable | Required | Description | Default |

## Architecture Overview
Brief paragraph. Link to ARCHITECTURE.md for full details.

Output Markdown only. No preamble. No explanation. No triple backticks wrapping the output.
"""


# ---------------------------------------------------------------------------
# ARCHITECTURE.md — incremental update
# ---------------------------------------------------------------------------

REPO_ARCHITECTURE_PROMPT: str = """\
You are a senior software architect maintaining architecture documentation.
A new push has been made. Update the architecture doc to reflect the changes.

CRITICAL RULES:
- If an existing ARCHITECTURE.md is provided below, copy every section WORD-FOR-WORD
  EXCEPT sections that are directly affected by the changed files.
- Only rewrite sections where the changed files introduce new components, modify
  existing ones, or change data flow / dependencies / APIs.
- Always ensure complete API details and Mermaid flowcharts are included.
- If no existing document is provided, generate a complete document from scratch.
- STRICT GROUNDING: Do NOT invent or hallucinate any file paths, directory structures, backend routes, endpoints, or frameworks that do not exist in the provided Code Context or Directory Tree. Formulate architecture claims strictly based on the real code.

Repository: {repository_name}
Architecture Type: {architecture_type}

Directory Tree:
{directory_tree}

Files changed in this push:
{changed_files}

Identified Modules:
{modules}

Services Identified:
{services}

Dependency Relationships:
{dependency_graph}

Data Flow:
{data_flow}

Coding Style Observations:
{coding_style}

API Endpoints:
{apis}

=== EXISTING ARCHITECTURE.md (copy unchanged sections exactly) ===
{existing_content}
=== END EXISTING ARCHITECTURE.md ===

=== RETRIEVED CODE CONTEXT ===
{rag_context}
=== END CONTEXT ===

Output the complete updated ARCHITECTURE.md with exactly these sections:

# Architecture — {repo_name}

## Architecture Style
Describe the overall architecture pattern and core design principles.

## Directory Structure
Provide the project directory tree in a clean code block:
```
{directory_tree}
```

## System Components
For each major module/service, document:
### `ComponentName`
- **Responsibility**:
- **Exposes**:
- **Consumes**:
- **Key Files**:

## Data Flow & Process Diagram
Provide a detailed Mermaid flowchart starting with ```mermaid\nflowchart TD or ```mermaid\ngraph TD (DO NOT use sequenceDiagram).
Show end-to-end data flow between components (User, Frontend Web App, API routes, Database, Tracker).
Follow with numbered step-by-step description.

## API Reference & Endpoints
Copy and output the COMPLETE API Endpoints table provided below:
{apis}

## Dependency Graph
Include a diagram or list showing component dependencies.

## Database & Storage
Document all database tables, local session storage, and persistent files.

## External Integrations
Document external services and libraries (e.g., Clerk, Supabase, OpenAI, pywin32).

## Key Design Decisions
Bullet list of architecture patterns, security decisions, and trade-offs.

## Scalability & Limitations

Output Markdown only. No preamble. No explanation.
"""


# ---------------------------------------------------------------------------
# REQUIREMENTS.md — incremental update
# ---------------------------------------------------------------------------

REPO_REQUIREMENTS_PROMPT: str = """\
You are a senior systems engineer and technical documentation specialist.
Generate or update the formal Requirements Specification (REQUIREMENTS.md) for this project.

CRITICAL RULES:
- If an existing REQUIREMENTS.md is provided below, copy every section WORD-FOR-WORD
  EXCEPT sections that are directly affected by the changed files or new features.
- Only update or add requirement clauses that need revision based on the codebase.
- Preserve consistent ID numbering (FR-1.1.1, FR-1.1.2, NFR-2.1.1, etc.).
- STRICT GROUNDING: Do NOT invent features or APIs that are not evidenced by the Code Context or Understanding.
- Structure the document cleanly with hierarchical headings, clear bulleted requirement IDs, and tables where helpful.

Repository: {repository_name}
Project Name: {repo_name}
Architecture Type: {architecture_type}

Files changed in this push:
{changed_files}

Project Summary:
{project_summary}

Project Purpose:
{project_purpose}

Identified Modules:
{modules}

Identified Services:
{services}

Identified APIs / Protocols:
{apis}

Data Flow:
{data_flow}

=== RETRIEVED CODE CONTEXT ===
{rag_context}
=== END CONTEXT ===

=== EXISTING REQUIREMENTS.md (copy unchanged sections exactly) ===
{existing_content}
=== END EXISTING REQUIREMENTS.md ===

Output the complete updated REQUIREMENTS.md with exactly these sections:

# Requirements Specification — {repo_name}

## 1. Functional Requirements (FR)

Group requirements by subsystem/feature with structured IDs (e.g. `### 1.1 Connection & Initialization`, `### 1.2 Core Protocol / Business Logic`, `### 1.3 Service & System Management`, `### 1.4 User Interface & Administration`, `### 1.5 Configuration & Persistence`):
- **FR-1.X.X**: Requirement description with explicit system behavior, protocols, port numbers, or opcodes where applicable.

## 2. Non-Functional Requirements (NFR)

Group into categories:
### 2.1 Performance & Concurrency
- **NFR-2.1.X**: Performance expectations, latency, memory limits, thread concurrency.

### 2.2 Reliability & Fault Tolerance
- **NFR-2.2.X**: Error recovery, retry mechanisms, cleanup on failure.

### 2.3 Security & Access Control
- **NFR-2.3.X**: Path validation, access limits, authentication/permissions, network isolation.

### 2.4 Compatibility & Standards
- **NFR-2.4.X**: Supported OS, protocols/RFCs, architecture compatibility (32-bit/64-bit).

## 3. Error Handling & Protocol Codes
Provide a table or bulleted list of standard error codes, conditions, and system handling actions.

Output Markdown only. No preamble. No explanation.
"""


# ---------------------------------------------------------------------------
# WORKFLOW.md — incremental update
# ---------------------------------------------------------------------------

REPO_WORKFLOW_PROMPT: str = """\
You are a senior software architect documenting the operational workflow of a
software project as a set of Mermaid flowcharts. A new push has been made.
Update the workflow doc to reflect the changes.

CRITICAL RULES:
- If an existing WORKFLOW.md is provided below, copy every section WORD-FOR-WORD
  EXCEPT sections that are directly affected by the changed files.
- Only rewrite sections where the changed files alter a process, add/remove a
  step, change an API flow, or introduce a new entry point.
- Every diagram MUST be valid Mermaid syntax inside a ```mermaid fenced block,
  starting with `flowchart TD` (or `flowchart LR` for short linear flows) or
  `stateDiagram-v2` for lifecycle/status diagrams. Do NOT use sequenceDiagram.
- Reference real file/module/function names from the context below in each
  diagram node — never invent generic placeholder steps.
- The Development Methodology section must be an HONEST INFERENCE from the
  evidence provided (commit cadence, CI/CD config, branching signals) — never
  assert a methodology as fact. If there isn't enough evidence to distinguish
  between methodologies, say so plainly instead of guessing.
- If no existing document is provided, generate a complete document from scratch.

Repository: {repository_name}
Architecture Type: {architecture_type}

Detected Entry Points:
{entry_points}

Files changed in this push:
{changed_files}

Identified Modules:
{modules}

Services Identified:
{services}

API Endpoints:
{apis}

Data Flow:
{data_flow}

Dependency Relationships:
{dependency_graph}

Configuration / CI-CD / Process Files Detected (e.g. .github/workflows,
Jenkinsfile, docker-compose.yml, CONTRIBUTING.md, issue/PR templates):
{process_signal_files}

Recent Commit History (from CHANGELOG.md, most recent first — use this to
judge commit cadence, batch size, and iteration pattern):
{commit_history_excerpt}

=== EXISTING WORKFLOW.md (copy unchanged sections exactly) ===
{existing_content}
=== END EXISTING WORKFLOW.md ===

=== RETRIEVED CODE CONTEXT ===
{rag_context}
=== END CONTEXT ===

Output the complete updated WORKFLOW.md with exactly these sections:

# Workflow — {repo_name}

## Overview
1–2 paragraphs describing the primary end-to-end workflow(s) this project executes.

## End-to-End Flow
A single Mermaid flowchart (```mermaid\\nflowchart TD) tracing the main
request/process lifecycle from trigger/entry point through every
module/service it passes through to its final output, labeling each node
with the real file or function that implements it.

## Key Sub-Workflows
For each significant sub-process (e.g. an API endpoint's request handling,
a background job, a data pipeline stage), provide a short Mermaid flowchart
plus 1–3 sentences of explanation.

## State / Lifecycle
If the project has entities with a status lifecycle (e.g. job states, order
states, pipeline states), provide a Mermaid `stateDiagram-v2`. Omit this
section entirely if no such lifecycle exists.

## Development Methodology
Best-effort inference of the software development methodology this repository
appears to follow (e.g. Agile/Scrum, Kanban, Trunk-Based/Continuous Delivery,
Waterfall, or "No formal methodology observed"). Base the call ONLY on
observable evidence, cite that evidence explicitly, and state your confidence:
- **Commit cadence & batch size** (from the commit history above): frequent
  small commits suggest iterative/Agile work; infrequent large commits suggest
  a more Waterfall or ad-hoc pattern.
- **CI/CD automation** (from the process files above): automated
  build/test/deploy pipelines suggest Continuous Integration/Delivery practice.
- **Process artifacts**: issue templates, PR templates, CONTRIBUTING.md, or
  sprint/iteration-named branches/folders suggest a formal Agile process;
  their absence suggests an informal or solo-developer workflow.
Output one short paragraph naming the best-fit label plus 2-3 bullet points
of the specific evidence behind it. If evidence is too thin to distinguish
between methodologies, say exactly that instead of picking one.

Output Markdown only. No preamble. No explanation. No triple backticks wrapping the output.
"""


# ---------------------------------------------------------------------------
# CHANGELOG.md — new entry only (agent prepends to existing file)
# ---------------------------------------------------------------------------

CHANGELOG_ENTRY_PROMPT: str = """\
You are a technical writer producing a single changelog entry for a software project.
Generate ONLY the new entry for this push — do NOT include a heading like "# Changelog".
The agent will prepend your output to the existing changelog automatically.

Repository: {repository_name}
Branch: {branch}
Commit SHA: {commit_sha}
Commit Message: {commit_message}
Author: {author}
Date: {push_date}
Time: {push_time}

Files Added in this push:
{added_files}

Files Modified in this push:
{modified_files}

Project Summary (for context):
{project_summary}

=== RETRIEVED CODE CONTEXT (changes in this commit) ===
{rag_context}
=== END CONTEXT ===

Output ONLY this block — no preamble, no "# Changelog" heading:

## [{commit_sha_short}] {commit_message_summary}
**Date:** {push_date}  **Time:** {push_time}
**Author:** {author}
**Branch:** `{branch}`
**Commit Message:** {commit_message}

### Summary
One paragraph: what was changed and why, based on the files modified.

### Added
- Bulleted list of new files or features (from the added files list above).
  If nothing was added, write: *No new files in this push.*

### Changed
- Bulleted list of modifications (from the modified files list above).
  For each file, describe what likely changed based on the code context.
  If nothing was modified, write: *No modifications in this push.*

### Impact
- Bulleted list of systems or modules affected by these changes.

---

Output Markdown only. No preamble. No explanation.
"""


# ---------------------------------------------------------------------------
# SECURITY.md — incremental update
# ---------------------------------------------------------------------------

SECURITY_DOC_PROMPT: str = """\
You are a senior security engineer maintaining security documentation for a software project.
A new push has been made. Update the security doc to reflect any new risks or changes.

CRITICAL RULES:
- If an existing SECURITY.md is provided below, copy every section WORD-FOR-WORD
  EXCEPT sections that are directly affected by the changed files.
- Only update sections where the changed files introduce new endpoints, dependencies,
  environment variables, or security-relevant logic.
- Do NOT rephrase, reorder, or reformat sections that are not affected.
- If no existing document is provided, generate a complete document from scratch.

Repository: {repository_name}
Architecture Type: {architecture_type}
Frameworks: {frameworks}
Dependencies: {dependencies}

Files changed in this push:
{changed_files}

API Endpoints Identified:
{apis}

=== EXISTING SECURITY.md (copy unchanged sections exactly) ===
{existing_content}
=== END EXISTING SECURITY.md ===

=== RETRIEVED CODE CONTEXT ===
{rag_context}
=== END CONTEXT ===

Output the complete updated SECURITY.md with exactly these sections:

# Security — {repo_name}

## Overview
## Authentication & Authorization
## API Security
## Data Security
## Dependency Security
## Environment & Secrets Management
## Known Risks & Recommendations
## Reporting Vulnerabilities
*To report a security vulnerability, please contact the repository owner directly.*

Output Markdown only. No preamble. No explanation.
"""


# ---------------------------------------------------------------------------
# Per-file documentation — on-demand, single-file generation
# ---------------------------------------------------------------------------

FILE_DOCUMENTATION_PROMPT: str = """\
You are a senior software engineer writing focused technical documentation for a
single source file inside a larger project. Only document THIS file — do not
describe the whole repository.

CRITICAL RULES:
- STRICT GROUNDING: Do NOT invent or hallucinate functions, classes, imports,
  exports, or behavior that is not present in the File Skeleton, the Detected
  Imports/Exports, or the Retrieved Code Context below.
- The "Detected Imports" and "Detected Exports" lists were extracted
  deterministically from the source file (not guessed) — reproduce them under
  their respective sections exactly as given, optionally with a short
  one-line explanation of what each import is used for if it's evident from
  the skeleton/context.
- If an existing document is provided below, treat this as a regeneration:
  keep any still-accurate descriptions, but ensure the output reflects the
  CURRENT file skeleton/imports/exports — do not silently keep stale claims.
- If nothing is knowable about a section from the material provided, write
  "Not evident from the available source." instead of guessing.

Repository: {repository_name}
File: {file_path}
Language: {language}

=== FILE SKELETON (imports + class/function signatures + docstrings) ===
{file_skeleton}
=== END FILE SKELETON ===

Detected Imports (deterministically extracted):
{imports}

Detected Exports / Top-level Definitions (deterministically extracted):
{exports}

=== RETRIEVED CODE CONTEXT (RAG chunks scoped to this file) ===
{rag_context}
=== END CONTEXT ===

=== EXISTING DOCUMENTATION FOR THIS FILE (if regenerating) ===
{existing_content}
=== END EXISTING DOCUMENTATION ===

Output the complete Markdown document with exactly these sections:

# {file_path}

## Overview
2-4 sentences: what this file is responsible for within the project.

## Change Summary
A short summary of this file's current purpose and role (if existing
documentation was provided above, briefly note what materially changed;
otherwise describe the file as it stands today).

## Key Components
For each significant class/function from the File Skeleton, a short bullet:
- **`name(...)`** — what it does, based only on the skeleton/context provided.

## Dependencies & Imports
List and briefly explain the Detected Imports above.

## Exports / Public API
List and briefly explain the Detected Exports above — what other files in
the project would import from this file.

## Usage Notes
Any notable usage caveats, side effects, or constraints evident from the
skeleton/context. If none are evident, write "Not evident from the available
source."

Output Markdown only. No preamble. No explanation. No triple backticks
wrapping the entire output.
"""
