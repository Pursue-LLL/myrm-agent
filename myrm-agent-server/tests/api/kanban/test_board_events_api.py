"""Board Events API integration tests.

Tests GET /kanban/boards/{board_id}/events endpoint with real SQLite DB.
Covers: basic listing, kinds filter, assignee filter, since_id, since_time, limit.
"""

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
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation():
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
        yield c


def _create_board(client: TestClient, name: str = "EventBoard") -> dict:
    resp = client.post("/api/v1/kanban/boards", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_task(
    client: TestClient,
    board_id: str,
    title: str = "Task",
    agent_id: str | None = None,
) -> dict:
    body: dict = {"title": title}
    if agent_id is not None:
        body["agent_id"] = agent_id
    resp = client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json=body)
    assert resp.status_code == 201
    return resp.json()


class TestBoardEventsApi:
    """Integration tests for GET /kanban/boards/{board_id}/events."""

    def test_empty_board_returns_empty_events(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = str(board["board_id"])
        resp = client.get(f"/api/v1/kanban/boards/{bid}/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_created_events_appear(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = str(board["board_id"])
        _create_task(client, bid, "Alpha")
        _create_task(client, bid, "Beta")

        resp = client.get(f"/api/v1/kanban/boards/{bid}/events")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] >= 2
        kinds = [e["kind"] for e in data["items"]]
        assert "created" in kinds

    def test_kinds_filter(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = str(board["board_id"])
        task = _create_task(client, bid, "Movable")
        tid = str(task["task_id"])

        client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "ready"})
        client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "running"})
        client.post(
            f"/api/v1/kanban/tasks/{tid}/move",
            json={"status": "completed"},
        )

        resp = client.get(
            f"/api/v1/kanban/boards/{bid}/events",
            params={"kinds": "completed"},
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["kind"] == "completed"

    def test_kinds_filter_multiple(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = str(board["board_id"])
        task = _create_task(client, bid, "Multi")
        tid = str(task["task_id"])

        client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "ready"})
        client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "running"})
        client.post(
            f"/api/v1/kanban/tasks/{tid}/move",
            json={"status": "completed"},
        )

        resp = client.get(
            f"/api/v1/kanban/boards/{bid}/events",
            params={"kinds": "created,completed"},
        )
        assert resp.status_code == 200
        data = resp.json()
        allowed = {"created", "completed"}
        for item in data["items"]:
            assert item["kind"] in allowed

    def test_assignee_filter(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = str(board["board_id"])
        _create_task(client, bid, "AgentA Task", agent_id="agent_a")
        _create_task(client, bid, "AgentB Task", agent_id="agent_b")

        resp = client.get(
            f"/api/v1/kanban/boards/{bid}/events",
            params={"assignee": "agent_a"},
        )
        assert resp.status_code == 200
        data = resp.json()
        for item in data["items"]:
            assert item["task_assignee"] == "agent_a"

    def test_since_id_filter(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = str(board["board_id"])
        _create_task(client, bid, "First")
        _create_task(client, bid, "Second")

        all_resp = client.get(f"/api/v1/kanban/boards/{bid}/events")
        all_items = all_resp.json()["items"]
        assert len(all_items) >= 2

        min_id = min(e["event_id"] for e in all_items)
        resp = client.get(
            f"/api/v1/kanban/boards/{bid}/events",
            params={"since_id": min_id},
        )
        data = resp.json()
        for item in data["items"]:
            assert item["event_id"] > min_id

    def test_limit_param(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = str(board["board_id"])
        for i in range(5):
            _create_task(client, bid, f"Task{i}")

        resp = client.get(
            f"/api/v1/kanban/boards/{bid}/events",
            params={"limit": 2},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert len(data["items"]) <= 2

    def test_nonexistent_board_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/boards/nonexistent999/events")
        assert resp.status_code == 404

    def test_invalid_since_time_400(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = str(board["board_id"])
        resp = client.get(
            f"/api/v1/kanban/boards/{bid}/events",
            params={"since_time": "not-a-date"},
        )
        assert resp.status_code == 400

    def test_event_has_task_title(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = str(board["board_id"])
        _create_task(client, bid, "MySpecialTitle")

        resp = client.get(f"/api/v1/kanban/boards/{bid}/events")
        data = resp.json()
        titles = [e["task_title"] for e in data["items"]]
        assert "MySpecialTitle" in titles

    def test_events_ordered_newest_first(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = str(board["board_id"])
        _create_task(client, bid, "T1")
        _create_task(client, bid, "T2")
        _create_task(client, bid, "T3")

        resp = client.get(f"/api/v1/kanban/boards/{bid}/events")
        data = resp.json()
        ids = [e["event_id"] for e in data["items"]]
        assert ids == sorted(ids, reverse=True)

    def test_cross_board_isolation(self, client: TestClient) -> None:
        board_a = _create_board(client, "BoardA")
        board_b = _create_board(client, "BoardB")
        bid_a = str(board_a["board_id"])
        bid_b = str(board_b["board_id"])
        _create_task(client, bid_a, "TaskInA")
        _create_task(client, bid_b, "TaskInB")

        resp_a = client.get(f"/api/v1/kanban/boards/{bid_a}/events")
        resp_b = client.get(f"/api/v1/kanban/boards/{bid_b}/events")

        titles_a = [e["task_title"] for e in resp_a.json()["items"]]
        titles_b = [e["task_title"] for e in resp_b.json()["items"]]

        assert "TaskInA" in titles_a
        assert "TaskInB" not in titles_a
        assert "TaskInB" in titles_b
        assert "TaskInA" not in titles_b
