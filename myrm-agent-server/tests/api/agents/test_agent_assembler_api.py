"""Unit tests for Visual Modular Agent Assembler REST API endpoints.

[INPUT]
- fastapi.FastAPI, starlette.testclient.TestClient
- app.api.agents.agent_assembler_router

[OUTPUT]
- Pytest test cases covering catalog, validation, dependency rules, and dry-run execution.

[POS]
tests/api/agents/test_agent_assembler_api.py: Full test suite for agent assembler endpoints.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.agent_assembler_router import router as agent_assembler_router


@pytest.fixture
def assembler_client() -> TestClient:
    """Create test client mounting agent_assembler_router."""
    app = FastAPI()
    app.include_router(agent_assembler_router, prefix="/api/v1")
    return TestClient(app)


def test_get_block_catalog_api(assembler_client: TestClient) -> None:
    """Verify GET /api/v1/agents/assembler/block-catalog returns predefined building blocks."""
    response = assembler_client.get("/api/v1/agents/assembler/block-catalog")
    assert response.status_code == 200
    catalog = response.json()
    assert isinstance(catalog, list)
    assert len(catalog) >= 6

    categories = {item["category"] for item in catalog}
    assert "brain" in categories
    assert "persona" in categories
    assert "tools" in categories
    assert "skills" in categories
    assert "memory" in categories
    assert "sandbox" in categories


def test_validate_assembly_success_api(assembler_client: TestClient) -> None:
    """Verify POST /api/v1/agents/assembler/validate passes for a well-formed blueprint."""
    payload = {
        "name": "Full-Stack Dev Agent",
        "description": "Production autonomous engineering agent",
        "blocks": [
            {
                "id": "brain-1",
                "category": "brain",
                "name": "Claude 3.7",
                "description": "Primary brain",
                "enabled": True,
                "config": {"primary_model": "claude-3-7-sonnet"},
            },
            {
                "id": "persona-1",
                "category": "persona",
                "name": "Senior Architect",
                "description": "Clean code persona",
                "enabled": True,
                "config": {"prompt_template": "You write zero any type clean TypeScript and Python."},
            },
            {
                "id": "tools-1",
                "category": "tools",
                "name": "Dev Tools",
                "description": "File manipulation",
                "enabled": True,
                "config": {"tool_names": ["read_file", "write_to_file"], "has_python_microtool": False},
            },
        ],
    }
    response = assembler_client.post("/api/v1/agents/assembler/validate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert len(data["errors"]) == 0
    assert data["estimated_token_cost"] > 250


def test_validate_assembly_missing_brain_api(assembler_client: TestClient) -> None:
    """Verify validation fails when no brain module is attached."""
    payload = {
        "name": "Brainless Agent",
        "blocks": [
            {
                "id": "persona-1",
                "category": "persona",
                "name": "Helpful Persona",
                "description": "Persona only",
                "enabled": True,
                "config": {},
            }
        ],
    }
    response = assembler_client.post("/api/v1/agents/assembler/validate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is False
    assert any("Missing Brain block" in err for err in data["errors"])


def test_validate_assembly_python_microtools_sandbox_warning_api(assembler_client: TestClient) -> None:
    """Verify warning is issued when Python microtools are present without sandbox."""
    payload = {
        "name": "Unsandboxed Python Agent",
        "blocks": [
            {
                "id": "brain-1",
                "category": "brain",
                "name": "GPT-4o",
                "description": "Brain",
                "enabled": True,
                "config": {"primary_model": "gpt-4o"},
            },
            {
                "id": "tools-1",
                "category": "tools",
                "name": "Python Scripting",
                "description": "In-process microtool",
                "enabled": True,
                "config": {"tool_names": ["python_exec"], "has_python_microtool": True},
            },
        ],
    }
    response = assembler_client.post("/api/v1/agents/assembler/validate", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert data["is_valid"] is True
    assert any("Sandbox" in w for w in data["warnings"])
    assert any("Sandbox" in s for s in data["suggestions"])


def test_dry_run_assembly_api(assembler_client: TestClient) -> None:
    """Verify POST /api/v1/agents/assembler/dry-run simulates execution correctly."""
    payload = {
        "blueprint": {
            "name": "Research Analyst",
            "blocks": [
                {
                    "id": "brain-1",
                    "category": "brain",
                    "name": "Claude 3.7",
                    "description": "Brain",
                    "enabled": True,
                    "config": {"primary_model": "claude-3-7-sonnet"},
                },
                {
                    "id": "persona-1",
                    "category": "persona",
                    "name": "Analyst",
                    "description": "Persona",
                    "enabled": True,
                    "config": {
                        "prompt_template": "You analyze data with citations.",
                        "persona_signature": "Truth and Rigor",
                    },
                },
                {
                    "id": "tools-1",
                    "category": "tools",
                    "name": "Search Tools",
                    "description": "Web search tools",
                    "enabled": True,
                    "config": {"tool_names": ["search_web", "fetch_url"]},
                },
            ],
        },
        "prompt": "Please search for latest AI papers on arxiv.",
    }
    response = assembler_client.post("/api/v1/agents/assembler/dry-run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "Truth and Rigor" in data["resolved_system_prompt"]
    assert "search_web" in data["predicted_tool_calls"]
    assert data["latency_ms"] > 0
    assert data["tokens_used"] > 0
    assert "Simulated execution" in data["simulated_response"]


def test_dry_run_assembly_invalid_blueprint_aborted_api(assembler_client: TestClient) -> None:
    """Verify dry-run aborts early if blueprint has critical validation errors."""
    payload = {
        "blueprint": {
            "name": "Broken Blueprint",
            "blocks": [],
        },
        "prompt": "Do something.",
    }
    response = assembler_client.post("/api/v1/agents/assembler/dry-run", json=payload)
    assert response.status_code == 200
    data = response.json()
    assert "aborted" in data["simulated_response"].lower()
    assert data["predicted_tool_calls"] == []
