"""API integration tests for Visual Kanban Multi-Agent Workflow Dispatcher and Card Handoff (Item 66).

[INPUT]
- app.api.agents.kanban_dispatcher_router.router
- app.services.agent.kanban_dispatcher_service.KanbanDispatcherService

[OUTPUT]
- Pytest assertions verifying card creation, automated cross-agent handoffs,
  progress tracking, blocker management, and workspace state snapshots.

[POS]
- myrm-agent/myrm-agent-server/tests/api/agents/test_kanban_dispatcher_api.py
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.kanban_dispatcher_router import router as kanban_dispatcher_router
from app.services.agent.kanban_dispatcher_service import KanbanDispatcherService


@pytest.fixture(autouse=True)
def reset_service_state() -> None:
    """Clear in-memory kanban workspaces before each test."""
    KanbanDispatcherService.clear()


@pytest.fixture
def client() -> TestClient:
    """TestClient fixture with kanban_dispatcher_router attached."""
    app = FastAPI()
    app.include_router(kanban_dispatcher_router)
    return TestClient(app)


def test_create_and_get_card_api(client: TestClient) -> None:
    """Test creating a kanban card and fetching its details."""
    payload = {
        "workspace_id": "ws-api-test",
        "title": "Design Database Schema",
        "description": "PostgreSQL relational schema for accounts",
        "column": "backlog",
    }
    resp = client.post("/agents/kanban-dispatcher/cards", json=payload)
    assert resp.status_code == 201
    data = resp.json()["data"]
    card_id = data["card_id"]
    assert data["title"] == "Design Database Schema"
    assert data["column"] == "backlog"
    assert data["assigned_agent_id"] == "product_manager"
    assert data["handoff_status"] == "idle"

    get_resp = client.get(f"/agents/kanban-dispatcher/workspaces/ws-api-test/cards/{card_id}")
    assert get_resp.status_code == 200
    card_data = get_resp.json()["data"]
    assert card_data["card_id"] == card_id


def test_list_cards_and_filter_api(client: TestClient) -> None:
    """Test listing cards in a workspace and filtering by column."""
    client.post(
        "/agents/kanban-dispatcher/cards",
        json={"workspace_id": "ws-list", "title": "Task 1", "column": "backlog"},
    )
    client.post(
        "/agents/kanban-dispatcher/cards",
        json={"workspace_id": "ws-list", "title": "Task 2", "column": "researching"},
    )

    all_resp = client.get("/agents/kanban-dispatcher/workspaces/ws-list/cards")
    assert all_resp.status_code == 200
    assert len(all_resp.json()["data"]) == 2

    filtered_resp = client.get("/agents/kanban-dispatcher/workspaces/ws-list/cards?column=researching")
    assert filtered_resp.status_code == 200
    filtered_data = filtered_resp.json()["data"]
    assert len(filtered_data) == 1
    assert filtered_data[0]["title"] == "Task 2"


def test_transition_card_automated_handoff_api(client: TestClient) -> None:
    """Test column transition, automated agent re-assignment, and handoff history."""
    create_resp = client.post(
        "/agents/kanban-dispatcher/cards",
        json={"workspace_id": "ws-trans", "title": "Implement Cache", "column": "backlog"},
    )
    card_id = create_resp.json()["data"]["card_id"]

    # Transition to developing
    trans_payload = {
        "target_column": "developing",
        "handoff_context": {"spec_url": "doc://redis-spec"},
    }
    trans_resp = client.post(
        f"/agents/kanban-dispatcher/workspaces/ws-trans/cards/{card_id}/transition",
        json=trans_payload,
    )
    assert trans_resp.status_code == 200
    trans_data = trans_resp.json()["data"]
    assert trans_data["column"] == "developing"
    assert trans_data["assigned_agent_id"] == "dev_coder"
    assert trans_data["handoff_status"] == "accepted"
    assert trans_data["handoff_payload"]["spec_url"] == "doc://redis-spec"

    # Verify workspace state has handoff event
    ws_resp = client.get("/agents/kanban-dispatcher/workspaces/ws-trans")
    assert ws_resp.status_code == 200
    ws_data = ws_resp.json()["data"]
    assert len(ws_data["handoff_history"]) == 1
    event = ws_data["handoff_history"][0]
    assert event["card_id"] == card_id
    assert event["from_agent_id"] == "product_manager"
    assert event["to_agent_id"] == "dev_coder"


def test_update_progress_api(client: TestClient) -> None:
    """Test updating the execution progress percent of a card."""
    create_resp = client.post(
        "/agents/kanban-dispatcher/cards",
        json={"workspace_id": "ws-prog", "title": "Run Benchmarks", "column": "developing"},
    )
    card_id = create_resp.json()["data"]["card_id"]

    prog_resp = client.post(
        f"/agents/kanban-dispatcher/workspaces/ws-prog/cards/{card_id}/progress",
        json={"progress_percent": 75},
    )
    assert prog_resp.status_code == 200
    assert prog_resp.json()["data"]["progress_percent"] == 75


def test_flag_and_resolve_blocker_api(client: TestClient) -> None:
    """Test flagging a blocker and resolving it."""
    create_resp = client.post(
        "/agents/kanban-dispatcher/cards",
        json={"workspace_id": "ws-blk", "title": "Security Audit", "column": "reviewing"},
    )
    card_id = create_resp.json()["data"]["card_id"]

    # Flag blocker
    block_resp = client.post(
        f"/agents/kanban-dispatcher/workspaces/ws-blk/cards/{card_id}/block",
        json={"reason": "Awaiting HITL Approval for Port Binding"},
    )
    assert block_resp.status_code == 200
    assert block_resp.json()["data"]["handoff_status"] == "blocked"

    ws_resp = client.get("/agents/kanban-dispatcher/workspaces/ws-blk")
    assert ws_resp.json()["data"]["active_blockers"] == 1

    # Unblock
    unblock_resp = client.post(
        f"/agents/kanban-dispatcher/workspaces/ws-blk/cards/{card_id}/unblock",
    )
    assert unblock_resp.status_code == 200
    assert unblock_resp.json()["data"]["handoff_status"] == "accepted"

    ws_resp_after = client.get("/agents/kanban-dispatcher/workspaces/ws-blk")
    assert ws_resp_after.json()["data"]["active_blockers"] == 0


def test_card_not_found_errors(client: TestClient) -> None:
    """Test 404 responses for missing cards."""
    get_404 = client.get("/agents/kanban-dispatcher/workspaces/ws/cards/non-existent-card")
    assert get_404.status_code == 404

    trans_404 = client.post(
        "/agents/kanban-dispatcher/workspaces/ws/cards/non-existent-card/transition",
        json={"target_column": "done"},
    )
    assert trans_404.status_code == 404
