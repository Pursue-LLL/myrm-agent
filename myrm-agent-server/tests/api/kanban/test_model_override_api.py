"""Tests for per-task model_override API (create/update + validation).

Covers: create task with valid/invalid model override, update task model
override set/clear, and 400 rejection of unresolvable models.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.kanban.router import router as kanban_router
from app.services.kanban import KanbanService


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    """Ensure each test gets a fresh KanbanService singleton."""
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation() -> None:  # type: ignore[misc]
    """Bypass agent_id validation for tests that don't test it explicitly."""
    with patch.object(
        KanbanService,
        "_validate_agent_id",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture(autouse=True)
def _providers_config() -> None:  # type: ignore[misc]
    """Provide a resolvable enabled provider for model override validation."""
    configs = MagicMock()
    configs.providers_dict = {
        "providers": [
            {
                "id": "anthropic",
                "providerType": "anthropic",
                "isEnabled": True,
                "enabledModels": ["claude-sonnet-4"],
                "apiUrl": "https://api.anthropic.com",
                "apiKeys": [{"isActive": True, "key": "sk-test"}],
            }
        ]
    }
    with patch(
        "app.api.kanban.routes.tasks.load_user_configs",
        new_callable=AsyncMock,
        return_value=configs,
    ):
        yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(kanban_router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c


def _create_board(client: TestClient) -> str:
    resp = client.post("/api/v1/kanban/boards", json={"name": "Board"})
    assert resp.status_code == 201
    return str(resp.json()["board_id"])


def test_create_task_with_model_override(client: TestClient) -> None:
    bid = _create_board(client)
    resp = client.post(
        f"/api/v1/kanban/boards/{bid}/tasks",
        json={"title": "T", "model_override": "anthropic/claude-sonnet-4"},
    )
    assert resp.status_code == 201
    assert resp.json()["model_override"] == "anthropic/claude-sonnet-4"


def test_create_task_without_model_override(client: TestClient) -> None:
    bid = _create_board(client)
    resp = client.post(
        f"/api/v1/kanban/boards/{bid}/tasks",
        json={"title": "T"},
    )
    assert resp.status_code == 201
    assert resp.json()["model_override"] is None


def test_create_task_rejects_unresolvable_model(client: TestClient) -> None:
    bid = _create_board(client)
    resp = client.post(
        f"/api/v1/kanban/boards/{bid}/tasks",
        json={"title": "T", "model_override": "foo/bar-baz"},
    )
    assert resp.status_code == 400


def test_update_task_sets_model_override(client: TestClient) -> None:
    bid = _create_board(client)
    created = client.post(f"/api/v1/kanban/boards/{bid}/tasks", json={"title": "T"})
    task_id = created.json()["task_id"]

    resp = client.patch(
        f"/api/v1/kanban/tasks/{task_id}",
        json={"model_override": "anthropic/claude-sonnet-4"},
    )
    assert resp.status_code == 200
    assert resp.json()["model_override"] == "anthropic/claude-sonnet-4"


def test_update_task_clears_model_override(client: TestClient) -> None:
    bid = _create_board(client)
    created = client.post(
        f"/api/v1/kanban/boards/{bid}/tasks",
        json={"title": "T", "model_override": "anthropic/claude-sonnet-4"},
    )
    task_id = created.json()["task_id"]

    resp = client.patch(f"/api/v1/kanban/tasks/{task_id}", json={"model_override": None})
    assert resp.status_code == 200
    assert resp.json()["model_override"] is None


def test_update_task_rejects_unresolvable_model(client: TestClient) -> None:
    bid = _create_board(client)
    created = client.post(f"/api/v1/kanban/boards/{bid}/tasks", json={"title": "T"})
    task_id = created.json()["task_id"]

    resp = client.patch(
        f"/api/v1/kanban/tasks/{task_id}",
        json={"model_override": "foo/bar-baz"},
    )
    assert resp.status_code == 400


def test_list_tasks_returns_model_override(client: TestClient) -> None:
    bid = _create_board(client)
    client.post(
        f"/api/v1/kanban/boards/{bid}/tasks",
        json={"title": "T", "model_override": "anthropic/claude-sonnet-4"},
    )
    resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks")
    assert resp.status_code == 200
    items = resp.json()["items"]
    assert items[0]["model_override"] == "anthropic/claude-sonnet-4"
