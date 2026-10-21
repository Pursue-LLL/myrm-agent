"""
[POS] tests/api/agents/test_todo_store_api.py
[INPUT] fastapi.FastAPI, starlette.testclient.TestClient, pathlib.Path, app.api.agents.todo_store_router, app.services.agent.todo_store_service
[OUTPUT] test_create_and_list_todo_items_api, test_update_todo_item_api, test_get_todo_hud_projection_api, test_remove_and_clear_todo_items_api

Integration test suite for shared Todo plan store and terminal-escape safe HUD projection endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from collections.abc import Generator
from pathlib import Path

import pytest
from fastapi import FastAPI
from starlette.testclient import TestClient

from app.api.agents.todo_store_router import router as todo_store_router
from app.services.agent.todo_store_service import (
    TodoStoreService,
    get_todo_store_service,
)


@pytest.fixture
def todo_client(tmp_path: Path) -> Generator[TestClient, None, None]:
    """Provide isolated TestClient fixture with temporary storage directory."""
    service = TodoStoreService(base_storage_dir=tmp_path / "todo_storage")

    test_app = FastAPI()
    test_app.include_router(todo_store_router, prefix="/api/agents")
    test_app.dependency_overrides[get_todo_store_service] = lambda: service

    with TestClient(test_app) as client:
        yield client


def test_create_and_list_todo_items_api(todo_client: TestClient) -> None:
    """Verify creating plan items with ANSI stripping and listing them."""
    session_id = "sess-plan-01"

    # Injected ANSI escape codes in title
    req_payload = {
        "title": "\x1b[32;1mSetup\x1b[0m Kubernetes \x07Cluster",
        "description": "Configure control plane nodes\x00safely",
        "assignee": "infra-bot",
        "item_id": "k8s-task-01",
    }
    resp = todo_client.post(f"/api/agents/todo-store/{session_id}/items", json=req_payload)
    assert resp.status_code == 201
    item = resp.json()
    assert item["item_id"] == "k8s-task-01"
    assert item["title"] == "Setup Kubernetes Cluster"
    assert item["description"] == "Configure control plane nodes safely"
    assert item["status"] == "pending"
    assert item["assignee"] == "infra-bot"

    # List items
    list_resp = todo_client.get(f"/api/agents/todo-store/{session_id}/items")
    assert list_resp.status_code == 200
    list_data = list_resp.json()
    assert list_data["total_count"] == 1
    assert "plan declarations, not execution evidence" in list_data["semantic_contract"]

    # Reject empty title
    bad_resp = todo_client.post(
        f"/api/agents/todo-store/{session_id}/items",
        json={"title": "   \x1b[0m   "},
    )
    assert bad_resp.status_code == 400


def test_update_todo_item_api(todo_client: TestClient) -> None:
    """Verify updating title, status, description, and assignee."""
    session_id = "sess-plan-update"

    # Add initial item
    create_resp = todo_client.post(
        f"/api/agents/todo-store/{session_id}/items",
        json={"title": "Initial Task", "assignee": "coder"},
    )
    assert create_resp.status_code == 201
    item_id = create_resp.json()["item_id"]

    # Update to in_progress
    update_payload = {
        "status": "in_progress",
        "title": "Refined \x1b[34mTask Title\x1b[0m",
        "description": "Added more details",
        "assignee": "reviewer",
    }
    patch_resp = todo_client.patch(
        f"/api/agents/todo-store/{session_id}/items/{item_id}",
        json=update_payload,
    )
    assert patch_resp.status_code == 200
    updated = patch_resp.json()
    assert updated["status"] == "in_progress"
    assert updated["title"] == "Refined Task Title"
    assert updated["description"] == "Added more details"
    assert updated["assignee"] == "reviewer"

    # Update non-existent item returns 404
    missing_resp = todo_client.patch(
        f"/api/agents/todo-store/{session_id}/items/missing-id",
        json={"title": "test"},
    )
    assert missing_resp.status_code == 404


def test_get_todo_hud_projection_api(todo_client: TestClient) -> None:
    """Verify HUD projection calculation and ANSI-safe formatted lines."""
    session_id = "sess-plan-hud"

    # Initial empty HUD
    empty_hud = todo_client.get(f"/api/agents/todo-store/{session_id}/hud")
    assert empty_hud.status_code == 200
    empty_data = empty_hud.json()
    assert empty_data["total_count"] == 0
    assert empty_data["progress_pct"] == 0.0

    # Add 2 items: 1 completed, 1 in_progress
    r1 = todo_client.post(
        f"/api/agents/todo-store/{session_id}/items",
        json={"title": "Task One", "assignee": "dev"},
    )
    r2 = todo_client.post(
        f"/api/agents/todo-store/{session_id}/items",
        json={"title": "Task Two", "assignee": "qa"},
    )
    item1_id = r1.json()["item_id"]
    item2_id = r2.json()["item_id"]

    todo_client.patch(
        f"/api/agents/todo-store/{session_id}/items/{item1_id}",
        json={"status": "completed"},
    )
    todo_client.patch(
        f"/api/agents/todo-store/{session_id}/items/{item2_id}",
        json={"status": "in_progress"},
    )

    hud_resp = todo_client.get(f"/api/agents/todo-store/{session_id}/hud")
    assert hud_resp.status_code == 200
    hud_data = hud_resp.json()
    assert hud_data["total_count"] == 2
    assert hud_data["completed_count"] == 1
    assert hud_data["in_progress_count"] == 1
    assert hud_data["progress_pct"] == 50.0
    assert len(hud_data["active_items"]) == 1  # only Task Two is active (in_progress)

    formatted = "\n".join(hud_data["formatted_hud_lines"])
    assert "[PLAN HUD] Progress: 50.0%" in formatted
    assert "[x] 1. Task One @dev" in formatted
    assert "[>] 2. Task Two @qa" in formatted
    assert "Todo items are plan declarations, not execution evidence." in formatted


def test_remove_and_clear_todo_items_api(todo_client: TestClient) -> None:
    """Verify single deletion and bulk clearing."""
    session_id = "sess-plan-delete"

    r = todo_client.post(
        f"/api/agents/todo-store/{session_id}/items",
        json={"title": "Task to delete"},
    )
    item_id = r.json()["item_id"]

    # Delete single item
    del_resp = todo_client.delete(f"/api/agents/todo-store/{session_id}/items/{item_id}")
    assert del_resp.status_code == 204

    # Deleting again returns 404
    del_again = todo_client.delete(f"/api/agents/todo-store/{session_id}/items/{item_id}")
    assert del_again.status_code == 404

    # Clear all items
    todo_client.post(
        f"/api/agents/todo-store/{session_id}/items",
        json={"title": "Task A"},
    )
    todo_client.post(
        f"/api/agents/todo-store/{session_id}/items",
        json={"title": "Task B"},
    )
    clear_resp = todo_client.delete(f"/api/agents/todo-store/{session_id}/items")
    assert clear_resp.status_code == 204

    hud_after = todo_client.get(f"/api/agents/todo-store/{session_id}/hud")
    assert hud_after.json()["total_count"] == 0
