"""API integration tests for Multi-Agent Tool Replay History Deduplication & Status Harmonization (Item 57).

[INPUT]
- app.api.agents.replay_dedup_router.router
- app.services.agent.replay_dedup_service.get_replay_dedup_service

[OUTPUT]
- Pytest test cases validating consecutive read-only tool call batching,
  monotonic status machine transitions, and watchdog deadlock prevention.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_replay_dedup_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.replay_dedup_router import router as replay_dedup_router
from app.services.agent.replay_dedup_service import (
    ReplayDedupService,
    get_replay_dedup_service,
)


@pytest.fixture
def service() -> ReplayDedupService:
    """Isolated ReplayDedupService instance for test execution."""
    return ReplayDedupService(default_lease_seconds=10.0)


@pytest.fixture
def client(service: ReplayDedupService) -> Generator[TestClient, None, None]:
    """TestClient fixture with injected ReplayDedupService dependency."""
    app = FastAPI()
    app.include_router(replay_dedup_router)
    app.dependency_overrides[get_replay_dedup_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_merge_replay_history_api(client: TestClient) -> None:
    session_id = "test-replay-session-01"
    payload = {
        "session_id": session_id,
        "min_merge_count": 2,
        "max_batch_size": 10,
        "items": [
            {
                "call_id": "c1",
                "tool_name": "read_file",
                "kind": "read_only",
                "args": {"path": "/app/a.py"},
                "result_summary": "read a.py",
                "status": "completed",
                "start_time": 1000.0,
                "end_time": 1001.0,
                "estimated_tokens": 120,
                "subagent_id": "worker-01",
            },
            {
                "call_id": "c2",
                "tool_name": "read_file",
                "kind": "read_only",
                "args": {"path": "/app/b.py"},
                "result_summary": "read b.py",
                "status": "completed",
                "start_time": 1001.0,
                "end_time": 1002.0,
                "estimated_tokens": 130,
                "subagent_id": "worker-01",
            },
            {
                "call_id": "w1",
                "tool_name": "write_file",
                "kind": "mutating",
                "args": {"path": "/app/out.txt"},
                "result_summary": "wrote out.txt",
                "status": "completed",
                "start_time": 1002.0,
                "end_time": 1003.0,
                "estimated_tokens": 200,
                "subagent_id": "worker-01",
            },
        ],
    }

    response = client.post("/agents/replay-dedup/merge-history", json=payload)
    assert response.status_code == 200
    res_data = response.json()["data"]

    assert res_data["session_id"] == session_id
    assert res_data["original_items_count"] == 3
    # c1 and c2 merged into 1 batch, w1 retained unmerged -> total 2 deduplicated items
    assert res_data["deduplicated_items_count"] == 2
    assert len(res_data["batches"]) == 1
    assert res_data["batches"][0]["tool_name"] == "read_file"
    assert res_data["batches"][0]["merged_count"] == 2
    assert res_data["tokens_saved"] > 0
    assert len(res_data["unmerged_items"]) == 1
    assert res_data["unmerged_items"][0]["call_id"] == "w1"


def test_sync_subagent_status_api(client: TestClient) -> None:
    session_id = "test-replay-session-02"
    subagent_id = "agent-lifecycle-01"

    # 1. Transition to RUNNING
    req1 = {
        "session_id": session_id,
        "subagent_id": subagent_id,
        "status": "running",
        "reason": "Task assigned by orchestrator",
    }
    resp1 = client.post("/agents/replay-dedup/status-sync", json=req1)
    assert resp1.status_code == 200
    data1 = resp1.json()["data"]
    assert data1["new_status"] == "running"
    assert data1["is_deadlock_prevented"] is False

    # 2. Transition to PENDING_APPROVAL
    req2 = {
        "session_id": session_id,
        "subagent_id": subagent_id,
        "status": "pending_approval",
        "reason": "Awaiting human review",
    }
    resp2 = client.post("/agents/replay-dedup/status-sync", json=req2)
    assert resp2.status_code == 200
    assert resp2.json()["data"]["new_status"] == "pending_approval"

    # 3. Transition to COMPLETED
    req3 = {
        "session_id": session_id,
        "subagent_id": subagent_id,
        "status": "completed",
        "reason": "Execution concluded successfully",
    }
    resp3 = client.post("/agents/replay-dedup/status-sync", json=req3)
    assert resp3.status_code == 200
    assert resp3.json()["data"]["new_status"] == "completed"


def test_watchdog_lease_check_api(client: TestClient) -> None:
    session_id = "test-replay-session-03"

    payload = {"session_id": session_id}
    response = client.post("/agents/replay-dedup/watchdog-check", json=payload)
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["session_id"] == session_id
    assert "current_statuses" in data


def test_get_subagent_statuses_api(client: TestClient) -> None:
    session_id = "test-replay-session-04"
    subagent_id = "worker-status-check"

    # Enroll subagent into running
    client.post(
        "/agents/replay-dedup/status-sync",
        json={
            "session_id": session_id,
            "subagent_id": subagent_id,
            "status": "running",
        },
    )

    response = client.get(f"/agents/replay-dedup/{session_id}/statuses")
    assert response.status_code == 200
    data = response.json()["data"]
    assert data["session_id"] == session_id
    assert subagent_id in data["statuses"]
    assert data["statuses"][subagent_id] == "running"
