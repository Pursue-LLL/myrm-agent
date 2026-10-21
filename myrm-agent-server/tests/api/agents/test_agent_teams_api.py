"""Unit tests for Durable Agent Teams API endpoints (Item 28).

[INPUT]
- app.api.agents.agent_teams_router.router
- app.services.agent.agent_teams_service.(AgentTeamsService, get_agent_teams_service)

[OUTPUT]
- Pytest test cases verifying roster provisioning, CAS task board DAG transitions,
  optimistic lock conflict (409), blocker dependency handling (422), and peer mailbox messaging.

[POS]
myrm-agent/myrm-agent-server/tests/api/agents/test_agent_teams_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.agent_teams_router import (
    get_agent_teams_service,
)
from app.api.agents.agent_teams_router import (
    router as agent_teams_router,
)
from app.services.agent.agent_teams_service import (
    AgentTeamsService,
)


@pytest.fixture
def mock_teams_service() -> AgentTeamsService:
    return AgentTeamsService()


@pytest.fixture
def teams_client(
    mock_teams_service: AgentTeamsService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(agent_teams_router)
    app.dependency_overrides[get_agent_teams_service] = lambda: mock_teams_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_teams_roster_and_member_lifecycle(teams_client: TestClient) -> None:
    team_id = "session-test-001"

    # 1. Verify implicit root lead is provisioned in projection
    resp = teams_client.get(f"/teams/{team_id}/projection")
    assert resp.status_code == 200
    data = resp.json()
    assert data["team_id"] == team_id
    assert len(data["members"]) == 1
    lead = data["members"][0]
    assert lead["name"] == "lead"
    assert lead["role"] == "lead"
    assert lead["phase"] == "active"

    # 2. Spawn a valid kebab-case teammate
    spawn_payload = {
        "name": "researcher-alpha",
        "description": "Information retrieval specialist",
        "provider": "anthropic",
        "context": "fresh",
    }
    resp = teams_client.post(f"/teams/{team_id}/members", json=spawn_payload)
    assert resp.status_code == 201
    member = resp.json()
    assert member["name"] == "researcher-alpha"
    assert member["role"] == "teammate"
    assert member["phase"] == "active"

    # 3. Reject invalid naming (non-kebab-case) with 400
    bad_payload = {
        "name": "Invalid_Name!",
        "description": "Bad name",
    }
    resp = teams_client.post(f"/teams/{team_id}/members", json=bad_payload)
    assert resp.status_code == 400

    # 4. Reject duplicate name with 400
    resp = teams_client.post(f"/teams/{team_id}/members", json=spawn_payload)
    assert resp.status_code == 400

    # 5. Mark teammate as failed with diagnosis
    fail_payload = {"error": "Subagent context limit exceeded"}
    resp = teams_client.post(f"/teams/{team_id}/members/researcher-alpha/fail", json=fail_payload)
    assert resp.status_code == 200
    failed_member = resp.json()
    assert failed_member["phase"] == "failed"
    assert failed_member["error"] == "Subagent context limit exceeded"

    # 6. Verify projection records failure
    resp = teams_client.get(f"/teams/{team_id}/projection")
    assert resp.status_code == 200
    proj = resp.json()
    assert proj["failure"] is not None
    assert "Subagent context limit exceeded" in proj["failure"]


def test_teams_cas_task_board_and_dag_blockers(teams_client: TestClient) -> None:
    team_id = "session-test-002"

    # Spawn worker teammate
    teams_client.post(
        f"/teams/{team_id}/members",
        json={"name": "worker-1", "description": "General worker"},
    )

    # 1. Create Task 1 (no blockers)
    t1_payload = {
        "subject": "Step 1: Download dataset",
        "description": "Fetch remote archive",
        "write_scopes": ["data/raw"],
    }
    resp = teams_client.post(f"/teams/{team_id}/tasks", json=t1_payload)
    assert resp.status_code == 201
    task_1 = resp.json()
    assert task_1["id"] == "task-1"
    assert task_1["revision"] == 1
    assert task_1["ready"] is True

    # 2. Create Task 2 (blocked by Task 1)
    t2_payload = {
        "subject": "Step 2: Clean and parse",
        "blocked_by": ["task-1"],
        "write_scopes": ["data/cleaned"],
    }
    resp = teams_client.post(f"/teams/{team_id}/tasks", json=t2_payload)
    assert resp.status_code == 201
    task_2 = resp.json()
    assert task_2["id"] == "task-2"
    assert task_2["revision"] == 1
    assert task_2["ready"] is False

    # 3. Claiming Task 2 while blocked must return 422
    claim_t2_payload = {
        "expected_revision": 1,
        "owner_name": "worker-1",
    }
    resp = teams_client.post(f"/teams/{team_id}/tasks/task-2/claim", json=claim_t2_payload)
    assert resp.status_code == 422
    assert "blocked by incomplete tasks" in resp.json()["detail"]

    # 4. CAS conflict check: update Task 1 with wrong revision returns 409
    stale_update_payload = {
        "expected_revision": 999,  # Wrong! Current is 1
        "description": "Stale update",
    }
    resp = teams_client.post(f"/teams/{team_id}/tasks/task-1/update", json=stale_update_payload)
    assert resp.status_code == 409
    assert "CAS conflict" in resp.json()["detail"]

    # 5. Claim Task 1 and complete it
    claim_t1_payload = {
        "expected_revision": 1,
        "owner_name": "worker-1",
    }
    resp = teams_client.post(f"/teams/{team_id}/tasks/task-1/claim", json=claim_t1_payload)
    assert resp.status_code == 200
    claimed_t1 = resp.json()
    assert claimed_t1["revision"] == 2
    assert claimed_t1["status"] == "in_progress"

    complete_t1_payload = {"expected_revision": 2}
    resp = teams_client.post(f"/teams/{team_id}/tasks/task-1/complete", json=complete_t1_payload)
    assert resp.status_code == 200
    completed_t1 = resp.json()
    assert completed_t1["status"] == "completed"

    # 6. Task 2 must now automatically be ready!
    resp = teams_client.get(f"/teams/{team_id}/tasks/task-2")
    assert resp.status_code == 200
    assert resp.json()["ready"] is True

    # 7. Worker can now claim Task 2
    resp = teams_client.post(f"/teams/{team_id}/tasks/task-2/claim", json=claim_t2_payload)
    assert resp.status_code == 200
    assert resp.json()["status"] == "in_progress"
    assert resp.json()["owner_name"] == "worker-1"


def test_teams_peer_mailbox_and_history(teams_client: TestClient) -> None:
    team_id = "session-test-003"

    # Spawn two teammates
    teams_client.post(
        f"/teams/{team_id}/members",
        json={"name": "agent-a", "description": "Analyst"},
    )
    teams_client.post(
        f"/teams/{team_id}/members",
        json={"name": "agent-b", "description": "Reviewer"},
    )

    # 1. Send peer message from agent-a to agent-b
    msg_payload = {
        "sender_name": "agent-a",
        "target_name": "agent-b",
        "content": "Please verify findings on revenue metrics",
        "mode": "waking",
    }
    resp = teams_client.post(f"/teams/{team_id}/messages", json=msg_payload)
    assert resp.status_code == 201
    msg = resp.json()
    assert msg["sender_name"] == "agent-a"
    assert msg["target_name"] == "agent-b"
    assert msg["mode"] == "waking"
    assert msg["delivered"] is False

    # 2. Sending to non-existent member returns 404
    bad_msg_payload = {
        "sender_name": "agent-a",
        "target_name": "unknown-agent",
        "content": "Hello?",
    }
    resp = teams_client.post(f"/teams/{team_id}/messages", json=bad_msg_payload)
    assert resp.status_code == 404

    # 3. Drain messages for agent-b
    resp = teams_client.post(f"/teams/{team_id}/messages/agent-b/drain")
    assert resp.status_code == 200
    drain = resp.json()
    assert drain["member_name"] == "agent-b"
    assert len(drain["messages"]) == 1
    assert drain["messages"][0]["delivered"] is True

    # 4. Drain again yields empty list
    resp = teams_client.post(f"/teams/{team_id}/messages/agent-b/drain")
    assert resp.status_code == 200
    assert len(resp.json()["messages"]) == 0
