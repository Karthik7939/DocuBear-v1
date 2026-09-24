"""
tests/test_requirements_service.py
-----------------------------------
Unit tests for the RequirementsService and requirements parsing logic.
"""

from unittest.mock import MagicMock
import pytest
from services.requirements_service import RequirementsService, RequirementItem


def test_requirement_item_to_dict():
    item = RequirementItem(
        id="FR-01",
        type="functional",
        category="Authentication",
        title="User Login",
        description="Support JWT login",
        status="completed",
        confidence=0.95,
        evidence_files=["backend/auth.py"],
        evidence_snippet="Found JWT validation in auth.py",
        remediation="Fully implemented.",
    )
    d = item.to_dict()
    assert d["id"] == "FR-01"
    assert d["type"] == "functional"
    assert d["status"] == "completed"
    assert d["confidence"] == 0.95
    assert "backend/auth.py" in d["evidence_files"]


def test_extract_requirements_from_text():
    mock_llm = MagicMock()
    mock_llm.generate.return_value = """
    ```json
    [
      {
        "id": "FR-01",
        "type": "functional",
        "category": "Authentication",
        "title": "User OAuth",
        "description": "Support GitHub login."
      },
      {
        "id": "NFR-01",
        "type": "non_functional",
        "category": "Security",
        "title": "Token Encryption",
        "description": "Store secrets securely."
      }
    ]
    ```
    """
    service = RequirementsService(llm=mock_llm)
    items = service.extract_requirements_from_text("Sample specification text")
    assert len(items) == 2
    assert items[0]["id"] == "FR-01"
    assert items[0]["type"] == "functional"
    assert items[1]["id"] == "NFR-01"
    assert items[1]["type"] == "non_functional"


def test_evaluate_requirement_against_codebase():
    mock_llm = MagicMock()
    mock_llm.generate.return_value = """
    ```json
    {
      "status": "completed",
      "confidence": 0.92,
      "evidence_files": ["services/auth.py"],
      "evidence_snippet": "Auth logic handles GitHub OAuth handshake.",
      "remediation": "Fully implemented."
    }
    ```
    """
    mock_rag = MagicMock()
    mock_rag.retrieve.return_value = MagicMock(context="OAuth implementation code context")

    service = RequirementsService(llm=mock_llm, rag=mock_rag)
    item = {
        "id": "FR-01",
        "type": "functional",
        "category": "Authentication",
        "title": "User OAuth",
        "description": "Support GitHub login."
    }
    evaluated = service.evaluate_requirement_against_codebase(
        item=item,
        repo_slug="test_repo",
        codebase_file_list="services/auth.py\nmain.py",
    )
    assert evaluated["status"] == "completed"
    assert evaluated["confidence"] == 0.92
    assert "services/auth.py" in evaluated["evidence_files"]


def test_parse_markdown_requirements():
    sample_md = """
    # Requirements Specification

    ## 1. Functional Requirements (FR)

    ### 1.1 Authentication
    - **FR-1.1.1**: The system must authenticate users via JWT.
    - **FR-1.1.2**: Support OAuth2 providers including GitHub.

    ## 2. Non-Functional Requirements (NFR)

    ### 2.1 Security
    - **NFR-2.1.1**: All tokens must be encrypted with AES-256.
    """
    service = RequirementsService()
    items = service.parse_markdown_requirements(sample_md)
    assert len(items) == 3
    assert items[0]["id"] == "FR-1.1.1"
    assert items[0]["type"] == "functional"
    assert items[0]["category"] == "Authentication"
    assert items[2]["id"] == "NFR-2.1.1"
    assert items[2]["type"] == "non_functional"
    assert items[2]["category"] == "Security"


def test_parse_hierarchical_pdf_text():
    sample_pdf_text = """
    1. Functional Requirements (FR)
    1.1 Connection Establishment & Port Allocation
    FR-1.1.1: The system must listen for initial client requests on UDP 
    Port 69.
    FR-1.1.2: The system must support two initial request types: Read 
    Request (RRQ, Opcode 1) and Write Request (WRQ, Opcode 2).
    1.2 TFTP Data Transfer Protocol (RFC 1350)
    FR-1.2.1: The server must segment outgoing data into standard 512-
    byte blocks prefixed with a 2-byte Opcode.

    2. Non-Functional Requirements (NFR)
    2.1 Performance & Concurrency
    NFR-2.1.1: The TFTP server engine must support multiple concurrent 
    active client transfer threads without cross-session blocking.
    NFR-2.1.2: Baseline memory consumption must remain below 15 MB.
    """
    service = RequirementsService()
    items = service.extract_requirements_from_text(sample_pdf_text)
    assert len(items) == 5
    assert items[0]["id"] == "FR-1.1.1"
    assert items[0]["category"] == "Connection Establishment & Port Allocation"
    assert "on UDP Port 69." in items[0]["description"]
    assert items[0]["type"] == "functional"

    assert items[2]["id"] == "FR-1.2.1"
    assert items[2]["category"] == "TFTP Data Transfer Protocol (RFC 1350)"

    assert items[3]["id"] == "NFR-2.1.1"
    assert items[3]["category"] == "Performance & Concurrency"
    assert items[3]["type"] == "non_functional"
    assert "cross-session blocking." in items[3]["description"]


def test_verify_items_against_markdown_specs(tmp_path, monkeypatch):
    from app.core.config import settings
    # Setup temporary docs directory
    fake_docs = tmp_path / "generated_docs"
    repo_dir = fake_docs / "test_repo"
    repo_dir.mkdir(parents=True)
    req_md = repo_dir / "REQUIREMENTS.md"
    req_md.write_text(
        "# Requirements Specification\n\n"
        "## 1. Functional Requirements (FR)\n\n"
        "### 1.1 Auth\n"
        "- **FR-1.1.1**: Listen for client UDP Port 69.\n"
        "- **FR-1.1.2**: Support RRQ and WRQ.\n\n"
        "## 2. Non-Functional Requirements (NFR)\n\n"
        "### 2.1 Concurrency\n"
        "- **NFR-2.1.1**: Support multi-threading.\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(settings, "generated_docs_path", str(fake_docs))

    service = RequirementsService()
    raw_items = [
        {"id": "FR-1.1.1", "title": "UDP Port 69", "description": "Listen on port 69", "category": "Auth", "type": "functional"},
        {"id": "FR-9.9.9", "title": "Missing Item", "description": "Unknown feature", "category": "Auth", "type": "functional"},
    ]
    verified = service._verify_items_against_markdown_specs(raw_items, "test_repo")
    assert len(verified) == 2
    assert verified[0]["id"] == "FR-1.1.1"
    assert verified[0]["status"] == "completed"
    assert "REQUIREMENTS.md" in verified[0]["evidence_files"]

    assert verified[1]["id"] == "FR-9.9.9"
    assert verified[1]["status"] == "missing"



