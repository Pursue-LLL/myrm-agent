"""API integration tests for Subagent Workspace Context Inheritance & Prompt Enrichment (Item 56).

[INPUT]
- app.api.agents.workspace_inheritance_router.router
- app.services.agent.workspace_inheritance_service.get_workspace_inheritance_service

[OUTPUT]
- Pytest test cases validating workspace rule inspection along the priority chain,
  role-adaptive subagent prompt enrichment, context budget capping, and audit history.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_workspace_inheritance_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.workspace_inheritance_router import router as workspace_inheritance_router
from app.services.agent.workspace_inheritance_service import (
    WorkspaceInheritanceService,
    get_workspace_inheritance_service,
)


@pytest.fixture
def service() -> WorkspaceInheritanceService:
    """Isolated WorkspaceInheritanceService instance for test execution."""
    return WorkspaceInheritanceService()


@pytest.fixture
def client(service: WorkspaceInheritanceService) -> Generator[TestClient, None, None]:
    """TestClient fixture with injected WorkspaceInheritanceService dependency."""
    app = FastAPI()
    app.include_router(workspace_inheritance_router)
    app.dependency_overrides[get_workspace_inheritance_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_inspect_workspace_rules_fallback(client: TestClient) -> None:
    """Verify inspecting rules in a workspace with fallback baseline invariants."""
    req = {"workspace_root": "/mock/workspace/alpha"}
    res = client.post("/agents/workspace-inheritance/inspect-rules", json=req)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["workspace_root"] == "/mock/workspace/alpha"
    assert data["total_snippets"] >= 3
    assert data["estimated_total_tokens"] > 0
    sources = {s["source_type"] for s in data["snippets"]}
    assert ".rules" in sources
    assert "AGENTS.md" in sources


def test_enrich_child_prompt_worker(client: TestClient) -> None:
    """Verify enriching a worker subagent prompt with inherited workspace rules."""
    req = {
        "workspace_root": "/projects/ai/core",
        "base_prompt": "You are a backend task executor.",
        "role": "worker",
        "max_context_tokens": 2000,
    }
    res = client.post("/agents/workspace-inheritance/enrich-prompt", json=req)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["original_prompt"] == "You are a backend task executor."
    assert "Inherited Workspace Rules & Invariants" in data["enriched_prompt"]
    assert "/projects/ai/core" in data["enriched_prompt"]
    assert data["injected_token_count"] > 0
    assert len(data["matched_sources"]) >= 1


def test_enrich_child_prompt_reviewer(client: TestClient) -> None:
    """Verify reviewer subagent prompt focuses on high and critical constraints."""
    req = {
        "workspace_root": "/projects/ai/core",
        "base_prompt": "You are a QA reviewer.",
        "role": "reviewer",
        "max_context_tokens": 2000,
    }
    res = client.post("/agents/workspace-inheritance/enrich-prompt", json=req)
    assert res.status_code == 200
    data = res.json()["data"]
    assert "Inherited Workspace Rules & Invariants" in data["enriched_prompt"]
    for snippet in data["applied_snippets"]:
        assert snippet["priority"] in ["critical", "high"]


def test_enrich_child_prompt_budget_capping(client: TestClient) -> None:
    """Verify that tight token budgets trigger differential compacting."""
    req = {
        "workspace_root": "/projects/ai/tight-budget",
        "base_prompt": "You are an agent with low token capacity.",
        "role": "worker",
        "max_context_tokens": 35,
    }
    res = client.post("/agents/workspace-inheritance/enrich-prompt", json=req)
    assert res.status_code == 200
    data = res.json()["data"]
    assert data["is_compacted"] is True
    assert data["injected_token_count"] <= 35


def test_get_audit_history(client: TestClient) -> None:
    """Verify recording and querying inheritance audit logs."""
    # Perform an enrichment action
    req = {
        "workspace_root": "/projects/ai/audit-test",
        "base_prompt": "Base task prompt.",
        "role": "worker",
        "max_context_tokens": 1500,
    }
    res_enrich = client.post("/agents/workspace-inheritance/enrich-prompt", json=req)
    assert res_enrich.status_code == 200

    # Query audit history
    res_audit = client.get("/agents/workspace-inheritance/audit-history")
    assert res_audit.status_code == 200
    data = res_audit.json()["data"]
    assert data["total"] >= 1
    assert any(r["workspace_root"] == "/projects/ai/audit-test" for r in data["records"])
