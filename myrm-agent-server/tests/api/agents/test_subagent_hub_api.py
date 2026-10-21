"""Unit tests for Subagent Supervision Hub API endpoints.

[INPUT]
- app.api.agents.subagent_hub_router.router
- app.services.agent.subagent_hub_service.SubagentHubService
- myrm_agent_harness.agent.sub_agents.supervision_hub.SubagentSupervisionCoordinator

[OUTPUT]
- Pytest test cases verifying roster overview, transcript retrieval, and steer/kill/revive actions

[POS]
myrm-agent/myrm-agent-server/tests/api/agents/test_subagent_hub_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from myrm_agent_harness.agent.sub_agents.supervision_hub import (
    SubagentSupervisionCoordinator,
)
from starlette.testclient import TestClient

from app.api.agents.subagent_hub_router import (
    get_subagent_hub_service,
)
from app.api.agents.subagent_hub_router import (
    router as subagent_hub_router,
)
from app.services.agent.subagent_hub_service import SubagentHubService


@pytest.fixture
def mock_subagent_hub_service() -> SubagentHubService:
    coord = SubagentSupervisionCoordinator()
    # Pre-register test workers
    session_id = "test-chat-session-001"
    coord.register_worker(session_id, "worker-1", "coder", "Writing backend code", model="gpt-4o")
    coord.register_worker(session_id, "worker-2", "reviewer", "Reviewing PR", model="claude-3-5")
    coord.update_worker_activity(
        "worker-1",
        current_activity="Running pytest",
        last_tool="pytest",
        tokens_delta=1200,
        elapsed_seconds=15.0,
    )
    coord.append_transcript("worker-1", "pytest", "tests/test_api.py", "4 passed", "info", duration_ms=45)
    return SubagentHubService(coordinator=coord)


@pytest.fixture
def subagent_hub_client(
    mock_subagent_hub_service: SubagentHubService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(subagent_hub_router)
    app.dependency_overrides[get_subagent_hub_service] = lambda: mock_subagent_hub_service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_get_session_roster_overview_api(subagent_hub_client: TestClient) -> None:
    resp = subagent_hub_client.get("/chats/test-chat-session-001/subagents/hub/roster")
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["session_id"] == "test-chat-session-001"
    assert data["total_workers"] == 2
    assert data["active_workers"] == 2
    assert data["total_tokens"] == 1200
    assert len(data["workers"]) == 2


def test_get_subagent_live_transcript_api(subagent_hub_client: TestClient) -> None:
    resp = subagent_hub_client.get(
        "/chats/test-chat-session-001/subagents/worker-1/transcript?limit=50"
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["code"] == 0
    data = body["data"]
    assert data["task_id"] == "worker-1"
    assert data["total_entries"] == 1
    assert data["entries"][0]["tool_name"] == "pytest"
    assert data["entries"][0]["output_summary"] == "4 passed"


def test_supervision_action_steer_api(subagent_hub_client: TestClient) -> None:
    # 1. Steer with empty message should fail with 400
    fail_resp = subagent_hub_client.post(
        "/chats/test-chat-session-001/subagents/worker-1/action",
        json={"action": "steer", "message": "   "},
    )
    assert fail_resp.status_code == 400

    # 2. Steer with valid message should succeed
    ok_resp = subagent_hub_client.post(
        "/chats/test-chat-session-001/subagents/worker-1/action",
        json={"action": "steer", "message": "Please add docstrings to all functions"},
    )
    assert ok_resp.status_code == 200
    data = ok_resp.json()["data"]
    assert data["success"] is True
    assert data["new_status"] == "running"


def test_supervision_action_kill_and_revive_api(subagent_hub_client: TestClient) -> None:
    # 1. Kill worker
    kill_resp = subagent_hub_client.post(
        "/chats/test-chat-session-001/subagents/worker-2/action",
        json={"action": "kill", "message": ""},
    )
    assert kill_resp.status_code == 200
    kill_data = kill_resp.json()["data"]
    assert kill_data["success"] is True
    assert kill_data["new_status"] == "failed"

    # 2. Revive the killed worker
    revive_resp = subagent_hub_client.post(
        "/chats/test-chat-session-001/subagents/worker-2/action",
        json={"action": "revive", "message": ""},
    )
    assert revive_resp.status_code == 200
    revive_data = revive_resp.json()["data"]
    assert revive_data["success"] is True
    assert revive_data["new_status"] == "running"
