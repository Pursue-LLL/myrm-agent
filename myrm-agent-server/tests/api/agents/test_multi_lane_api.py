"""Unit tests for Pi Harness v2 Multi-Lane Parallel Execution Model API (Item 50).

[INPUT]
- app.api.agents.multi_lane_router.router
- app.services.agent.multi_lane_service.MultiLaneService

[OUTPUT]
- Pytest test cases validating lane creation, append-only tree nodes,
  operation dispatch/completion/cancellation, 409 concurrency conflict, and oplog queries.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_multi_lane_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.multi_lane_router import (
    get_service,
)
from app.api.agents.multi_lane_router import (
    router as multi_lane_router,
)
from app.services.agent.multi_lane_service import (
    MultiLaneService,
)


@pytest.fixture
def service() -> MultiLaneService:
    return MultiLaneService()


@pytest.fixture
def client(
    service: MultiLaneService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(multi_lane_router)
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_create_lane_and_snapshot_api(client: TestClient) -> None:
    chat_id = "test-chat-lane-001"

    # Create custom thread lane
    create_resp = client.post(
        f"/chats/{chat_id}/multi-lane/lanes",
        json={
            "lane_id": "slack:thread-888",
            "display_name": "Slack Bug Discussion Thread",
        },
    )
    assert create_resp.status_code == 201
    created_lane = create_resp.json()["data"]
    assert created_lane["lane_id"] == "slack:thread-888"
    assert created_lane["state"] == "idle"

    # Query snapshot
    snap_resp = client.get(f"/chats/{chat_id}/multi-lane/snapshot")
    assert snap_resp.status_code == 200
    snapshot = snap_resp.json()["data"]
    assert snapshot["session_id"] == chat_id
    assert snapshot["total_nodes"] == 1  # root node
    assert snapshot["active_lanes_count"] == 0
    assert "main" in snapshot["lanes"]
    assert "slack:thread-888" in snapshot["lanes"]


def test_append_tree_node_api(client: TestClient) -> None:
    chat_id = "test-chat-lane-002"

    append_resp = client.post(
        f"/chats/{chat_id}/multi-lane/lanes/main/nodes",
        json={
            "content": "User sent a prompt in main channel",
            "node_type": "message",
            "metadata": {"author": "alice"},
        },
    )
    assert append_resp.status_code == 200
    node = append_resp.json()["data"]
    assert node["lane_id"] == "main"
    assert node["parent_id"] == "root"
    assert node["content"] == "User sent a prompt in main channel"

    # Snapshot should reflect 2 nodes (root + appended node)
    snap_resp = client.get(f"/chats/{chat_id}/multi-lane/snapshot")
    assert snap_resp.json()["data"]["total_nodes"] == 2


def test_dispatch_and_complete_operation_api(client: TestClient) -> None:
    chat_id = "test-chat-lane-003"

    # Dispatch operation on main
    dispatch_resp = client.post(
        f"/chats/{chat_id}/multi-lane/lanes/main/dispatch",
        json={
            "name": "llm_turn_execution",
            "payload": {"prompt": "Solve issue #42"},
        },
    )
    assert dispatch_resp.status_code == 200
    op = dispatch_resp.json()["data"]
    op_id = op["op_id"]
    assert op["status"] == "running"

    # Check active lanes count is 1
    snap_resp = client.get(f"/chats/{chat_id}/multi-lane/snapshot")
    assert snap_resp.json()["data"]["active_lanes_count"] == 1

    # Complete the operation
    complete_resp = client.post(
        f"/chats/{chat_id}/multi-lane/lanes/main/complete",
        json={
            "op_id": op_id,
            "result_content": "Issue #42 resolved with patch",
        },
    )
    assert complete_resp.status_code == 200
    completed_op = complete_resp.json()["data"]
    assert completed_op["status"] == "completed"
    assert completed_op["result_node_id"] is not None

    # After completion, active count is 0 and total nodes is 2 (root + result node)
    final_snap = client.get(f"/chats/{chat_id}/multi-lane/snapshot").json()["data"]
    assert final_snap["active_lanes_count"] == 0
    assert final_snap["total_nodes"] == 2


def test_single_lane_concurrency_conflict_409_api(client: TestClient) -> None:
    chat_id = "test-chat-lane-004"

    # Dispatch first operation
    r1 = client.post(
        f"/chats/{chat_id}/multi-lane/lanes/main/dispatch",
        json={"name": "long_task_1", "payload": {}},
    )
    assert r1.status_code == 200

    # Dispatch second operation on same lane MUST return 409 Conflict
    r2 = client.post(
        f"/chats/{chat_id}/multi-lane/lanes/main/dispatch",
        json={"name": "long_task_2", "payload": {}},
    )
    assert r2.status_code == 409
    assert "Per-lane concurrency constraint" in r2.json()["detail"]


def test_cancel_operation_api(client: TestClient) -> None:
    chat_id = "test-chat-lane-005"

    d_resp = client.post(
        f"/chats/{chat_id}/multi-lane/lanes/main/dispatch",
        json={"name": "to_be_cancelled", "payload": {}},
    )
    op_id = d_resp.json()["data"]["op_id"]

    cancel_resp = client.post(
        f"/chats/{chat_id}/multi-lane/lanes/main/cancel",
        json={"op_id": op_id, "reason": "User clicked Stop"},
    )
    assert cancel_resp.status_code == 200
    cancelled_op = cancel_resp.json()["data"]
    assert cancelled_op["status"] == "cancelled"
    assert cancelled_op["error_message"] == "User clicked Stop"

    snap = client.get(f"/chats/{chat_id}/multi-lane/snapshot").json()["data"]
    assert snap["lanes"]["main"]["state"] == "idle"


def test_get_oplog_and_reset_api(client: TestClient) -> None:
    chat_id = "test-chat-lane-006"

    # Dispatch and cancel to generate oplog entry
    d_resp = client.post(
        f"/chats/{chat_id}/multi-lane/lanes/main/dispatch",
        json={"name": "logged_task", "payload": {}},
    )
    op_id = d_resp.json()["data"]["op_id"]
    client.post(
        f"/chats/{chat_id}/multi-lane/lanes/main/cancel",
        json={"op_id": op_id, "reason": "aborted"},
    )

    # Get oplog
    oplog_resp = client.get(f"/chats/{chat_id}/multi-lane/lanes/main/oplog")
    assert oplog_resp.status_code == 200
    log_entries = oplog_resp.json()["data"]
    assert len(log_entries) == 1
    assert log_entries[0]["op_id"] == op_id

    # Reset
    reset_resp = client.post(f"/chats/{chat_id}/multi-lane/reset")
    assert reset_resp.status_code == 200

    # New snapshot should be brand new fresh session
    new_snap = client.get(f"/chats/{chat_id}/multi-lane/snapshot").json()["data"]
    assert len(new_snap["recent_op_logs"]) == 0
