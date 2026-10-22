"""Unit tests for Pi Harness v2 Deterministic Subagent Session Fork Primitive API (Item 51).

[INPUT]
- app.api.agents.session_fork_router.router
- app.services.agent.session_fork_service.SessionForkService

[OUTPUT]
- Pytest test cases validating deterministic child derivation, safe replay reattach,
  branch vs tree scoped node duplication, parent directory queries, and reset.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_session_fork_api.py
"""

from __future__ import annotations

from collections.abc import Generator

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.session_fork_router import (
    get_service,
)
from app.api.agents.session_fork_router import (
    router as session_fork_router,
)
from app.services.agent.session_fork_service import (
    SessionForkService,
)


@pytest.fixture
def service() -> SessionForkService:
    return SessionForkService()


@pytest.fixture
def client(
    service: SessionForkService,
) -> Generator[TestClient, None, None]:
    app = FastAPI()
    app.include_router(session_fork_router)
    app.dependency_overrides[get_service] = lambda: service
    yield TestClient(app)
    app.dependency_overrides.clear()


def test_derive_child_id_api(client: TestClient) -> None:
    parent_id = "parent-chat-001"
    tool_call_id = "tool-invoke-999"

    resp1 = client.post(
        "/agents/session-fork/derive-id",
        json={"parent_session_id": parent_id, "tool_call_id": tool_call_id},
    )
    assert resp1.status_code == 200
    data1 = resp1.json()["data"]
    child_id1 = data1["child_session_id"]
    assert child_id1.startswith("child-")

    resp2 = client.post(
        "/agents/session-fork/derive-id",
        json={"parent_session_id": parent_id, "tool_call_id": tool_call_id},
    )
    assert resp2.status_code == 200
    data2 = resp2.json()["data"]
    assert data2["child_session_id"] == child_id1


def test_fork_child_session_and_safe_replay_api(client: TestClient) -> None:
    parent_id = "parent-chat-002"
    tool_call_id = "tool-call-abc"

    # First execution: fresh fork
    f_resp1 = client.post(
        "/agents/session-fork/fork",
        json={
            "parent_session_id": parent_id,
            "tool_call_id": tool_call_id,
            "scope": "branch",
        },
    )
    assert f_resp1.status_code == 201
    res1 = f_resp1.json()["data"]
    assert res1["is_reattached"] is False
    child_id = res1["child_session_id"]

    # Second execution (safe replay): reattach without creating duplicate twin
    f_resp2 = client.post(
        "/agents/session-fork/fork",
        json={
            "parent_session_id": parent_id,
            "tool_call_id": tool_call_id,
            "scope": "branch",
        },
    )
    assert f_resp2.status_code == 201
    res2 = f_resp2.json()["data"]
    assert res2["is_reattached"] is True
    assert res2["child_session_id"] == child_id

    # Check child session linkage
    c_resp = client.get(f"/agents/session-fork/children/{child_id}")
    assert c_resp.status_code == 200
    link = c_resp.json()["data"]
    assert link["reattach_count"] == 1
    assert link["parent_session_id"] == parent_id
    assert link["tool_call_id"] == tool_call_id


def test_fork_with_branch_and_tree_scope_nodes_api(client: TestClient) -> None:
    parent_id = "parent-chat-003"

    sample_nodes = [
        {"node_id": "root", "parent_id": None, "node_type": "root", "content": "Root", "created_at": 100},
        {"node_id": "node-1", "parent_id": "root", "node_type": "message", "content": "Msg 1", "created_at": 101},
        {"node_id": "node-2", "parent_id": "node-1", "node_type": "tool_call", "content": "Call 2", "created_at": 102},
        {"node_id": "node-side", "parent_id": "root", "node_type": "message", "content": "Side msg", "created_at": 103},
    ]

    # Branch scope: trace back from node-2 -> root, node-1, node-2 (3 nodes)
    branch_resp = client.post(
        "/agents/session-fork/fork",
        json={
            "parent_session_id": parent_id,
            "tool_call_id": "call-branch-scope",
            "scope": "branch",
            "parent_nodes": sample_nodes,
            "target_leaf_id": "node-2",
        },
    )
    assert branch_resp.status_code == 201
    branch_res = branch_resp.json()["data"]
    assert branch_res["copied_nodes_count"] == 3
    branch_child_id = branch_res["child_session_id"]

    # Verify copied nodes
    nodes_resp = client.get(f"/agents/session-fork/children/{branch_child_id}/nodes")
    assert nodes_resp.status_code == 200
    copied_nodes = nodes_resp.json()["data"]
    assert len(copied_nodes) == 3
    node_ids = [n["node_id"] for n in copied_nodes]
    assert node_ids == ["root", "node-1", "node-2"]
    assert "node-side" not in node_ids


def test_list_children_for_parent_api(client: TestClient) -> None:
    parent_id = "parent-chat-004"

    client.post(
        "/agents/session-fork/fork",
        json={"parent_session_id": parent_id, "tool_call_id": "subagent-task-1"},
    )
    client.post(
        "/agents/session-fork/fork",
        json={"parent_session_id": parent_id, "tool_call_id": "subagent-task-2"},
    )

    list_resp = client.get(f"/agents/session-fork/parents/{parent_id}/children")
    assert list_resp.status_code == 200
    data = list_resp.json()["data"]
    assert data["parent_session_id"] == parent_id
    assert data["total_children"] == 2
    assert len(data["children"]) == 2


def test_child_not_found_404_api(client: TestClient) -> None:
    resp = client.get("/agents/session-fork/children/non-existent-child-id")
    assert resp.status_code == 404

    nodes_resp = client.get("/agents/session-fork/children/non-existent-child-id/nodes")
    assert nodes_resp.status_code == 404


def test_reset_session_fork_api(client: TestClient) -> None:
    parent_id = "parent-chat-005"
    client.post(
        "/agents/session-fork/fork",
        json={"parent_session_id": parent_id, "tool_call_id": "temp-call"},
    )

    # Reset
    reset_resp = client.post("/agents/session-fork/reset")
    assert reset_resp.status_code == 200

    # Parent should have 0 children
    list_resp = client.get(f"/agents/session-fork/parents/{parent_id}/children")
    assert list_resp.json()["data"]["total_children"] == 0
