"""Kanban source_chat_id REST filter integration tests (HTTP → SQLite, no mocks)."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.kanban.router import router as kanban_router
from app.services.kanban import KanbanService


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    KanbanService._instance = None
    yield  # type: ignore[misc]
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation() -> None:  # type: ignore[misc]
    with patch.object(
        KanbanService,
        "_validate_agent_id",
        new_callable=AsyncMock,
    ):
        yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(kanban_router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c  # type: ignore[misc]


def _create_board(client: TestClient) -> str:
    resp = client.post("/api/v1/kanban/boards", json={"name": "SourceChatFilter"})
    assert resp.status_code == 201
    return resp.json()["board_id"]


def test_list_tasks_filters_by_source_chat_id(client: TestClient) -> None:
    board_id = _create_board(client)

    chat_a = client.post(
        f"/api/v1/kanban/boards/{board_id}/tasks",
        json={
            "title": "From chat A",
            "metadata": {"source_chat_id": "chat-session-a"},
        },
    )
    assert chat_a.status_code == 201

    chat_b = client.post(
        f"/api/v1/kanban/boards/{board_id}/tasks",
        json={
            "title": "From chat B",
            "metadata": {"source_chat_id": "chat-session-b"},
        },
    )
    assert chat_b.status_code == 201

    all_tasks = client.get(f"/api/v1/kanban/boards/{board_id}/tasks")
    assert all_tasks.status_code == 200
    assert len(all_tasks.json()["items"]) == 2

    filtered = client.get(
        f"/api/v1/kanban/boards/{board_id}/tasks",
        params={"source_chat_id": "chat-session-a"},
    )
    assert filtered.status_code == 200
    items = filtered.json()["items"]
    assert len(items) == 1
    assert items[0]["title"] == "From chat A"
    assert items[0]["metadata"].get("source_chat_id") == "chat-session-a"
