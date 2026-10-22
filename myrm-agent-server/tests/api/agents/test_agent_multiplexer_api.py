"""Unit tests for Agent Session Multiplexer REST API endpoints.

[INPUT]
- fastapi.FastAPI, starlette.testclient.TestClient
- app.api.agents.agent_multiplexer_router
- myrm_agent_harness.agent.sub_agents.multiplexer.session_multiplexer::get_session_multiplexer

[OUTPUT]
- Pytest test cases verifying session registration, listing, cross-session inspection, and instruction injection.

[POS]
tests/api/agents/test_agent_multiplexer_api.py: End-to-end API test suite for AgentMultiplexer.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from myrm_agent_harness.agent.sub_agents.multiplexer.session_multiplexer import (
    get_session_multiplexer,
)
from starlette.testclient import TestClient

from app.api.agents.agent_multiplexer_router import router as agent_multiplexer_router


@pytest.fixture
def multiplexer_client() -> TestClient:
    """Create test client mounting agent_multiplexer_router."""
    app = FastAPI()
    app.include_router(agent_multiplexer_router, prefix="/api/v1")
    return TestClient(app)


def test_register_and_list_multiplexer_sessions_api(
    multiplexer_client: TestClient,
) -> None:
    """Verify POST /api/v1/agents/multiplexer/sessions and GET list filtering."""
    # 1. Register a regular worker session
    p1 = {
        "session_id": "api-worker-1",
        "agent_type": "coder",
        "task_objective": "Implement database connection pool",
        "parent_session_id": "api-root-001",
        "is_headless": False,
    }
    res1 = multiplexer_client.post("/api/v1/agents/multiplexer/sessions", json=p1)
    assert res1.status_code == 201
    d1 = res1.json()
    assert d1["session_id"] == "api-worker-1"
    assert d1["agent_type"] == "coder"
    assert d1["state"] == "running"
    assert d1["is_headless"] is False

    # 2. Register a headless background worker session
    p2 = {
        "session_id": "api-worker-headless",
        "agent_type": "researcher",
        "task_objective": "Continuous documentation scraping",
        "parent_session_id": "api-root-001",
        "is_headless": True,
    }
    res2 = multiplexer_client.post("/api/v1/agents/multiplexer/sessions", json=p2)
    assert res2.status_code == 201
    d2 = res2.json()
    assert d2["is_headless"] is True

    # 3. List all sessions for parent
    list_res = multiplexer_client.get(
        "/api/v1/agents/multiplexer/sessions",
        params={"parent_session_id": "api-root-001"},
    )
    assert list_res.status_code == 200
    sessions = list_res.json()
    session_ids = [s["session_id"] for s in sessions]
    assert "api-worker-1" in session_ids
    assert "api-worker-headless" in session_ids

    # 4. Filter by is_headless
    hl_res = multiplexer_client.get(
        "/api/v1/agents/multiplexer/sessions",
        params={"parent_session_id": "api-root-001", "is_headless": True},
    )
    assert hl_res.status_code == 200
    hl_sessions = hl_res.json()
    assert len(hl_sessions) == 1
    assert hl_sessions[0]["session_id"] == "api-worker-headless"


def test_inspect_multiplexer_session_api(multiplexer_client: TestClient) -> None:
    """Verify GET /api/v1/agents/multiplexer/sessions/{id}/inspect returns logs and artifacts."""
    mux = get_session_multiplexer()
    session_id = "api-inspect-target"
    mux.register_session(
        session_id=session_id,
        agent_type="architect",
        task_objective="Design event schema",
    )
    mux.append_log(session_id, "Validating Avro schema backward compatibility...")
    mux.record_artifact(session_id, "/workspace/schema.avsc")

    # 1. Successful inspection
    res = multiplexer_client.get(f"/api/v1/agents/multiplexer/sessions/{session_id}/inspect")
    assert res.status_code == 200
    data = res.json()
    assert data["session_id"] == session_id
    assert data["agent_type"] == "architect"
    assert data["state"] == "running"
    assert "Validating Avro schema" in data["log_tail"][0]
    assert data["artifacts"] == ["/workspace/schema.avsc"]

    # 2. Non-existent session returns 404
    missing_res = multiplexer_client.get("/api/v1/agents/multiplexer/sessions/non-existent-id/inspect")
    assert missing_res.status_code == 404


def test_instruct_multiplexer_session_api(multiplexer_client: TestClient) -> None:
    """Verify POST /api/v1/agents/multiplexer/sessions/{id}/instruct injects steering directive."""
    mux = get_session_multiplexer()
    session_id = "api-instruct-target"
    mux.register_session(
        session_id=session_id,
        agent_type="code-reviewer",
        task_objective="Review PR diff",
    )

    payload = {
        "instruction": "Focus on sql injection vectors in repository queries.",
        "source_agent": "lead-architect",
    }
    res = multiplexer_client.post(
        f"/api/v1/agents/multiplexer/sessions/{session_id}/instruct",
        json=payload,
    )
    assert res.status_code == 200
    data = res.json()
    assert data["success"] is True
    assert data["session_id"] == session_id
    assert data["queued_instructions_count"] == 1

    # Non-existent session returns 404
    bad_res = multiplexer_client.post(
        "/api/v1/agents/multiplexer/sessions/missing-session/instruct",
        json=payload,
    )
    assert bad_res.status_code == 404
