"""Kanban move REST API: a card that leaves the blocked column no longer reports a block.

Runs over HTTP against the real SQLite store, so it covers what the board page actually receives: the move response,
the task read and the board's task list. The reason, kind and wake-up time of a block exist only while the task is
blocked.
"""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.kanban.router import router as kanban_router
from app.services.kanban import KanbanService

_REASON = "Need your decision: Postgres or SQLite?"
_WAKE_AT = "2030-01-01T03:00:00Z"
_NO_BLOCK = {"blocked_reason": None, "block_kind": None, "scheduled_until": None}


@pytest.fixture(autouse=True)
def _reset_singleton() -> Iterator[None]:
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation() -> Iterator[None]:
    with patch.object(KanbanService, "_validate_agent_id", new_callable=AsyncMock):
        yield


@pytest.fixture
def client() -> Iterator[TestClient]:
    app = FastAPI()
    app.include_router(kanban_router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c


def _blocked_task(client: TestClient, **block: str) -> tuple[str, str]:
    """A task moved into the blocked column through the API; returns its board id and task id."""
    board_id = client.post("/api/v1/kanban/boards", json={"name": "Board"}).json()["board_id"]
    task_id = client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json={"title": "Task"}).json()["task_id"]
    resp = client.post(f"/api/v1/kanban/tasks/{task_id}/move", json={"status": "blocked", **block})
    assert resp.status_code == 200
    assert resp.json()["status"] == "blocked"
    return board_id, task_id


def _block_details(payload: dict[str, object]) -> dict[str, object]:
    return {key: payload[key] for key in _NO_BLOCK}


@pytest.mark.parametrize("target", ["backlog", "ready", "completed", "failed", "archived"])
def test_a_card_moved_out_of_the_blocked_column_reports_no_block(client: TestClient, target: str) -> None:
    board_id, task_id = _blocked_task(client, block_kind="scheduled", blocked_reason=_REASON, scheduled_until=_WAKE_AT)

    resp = client.post(f"/api/v1/kanban/tasks/{task_id}/move", json={"status": target})

    assert resp.status_code == 200
    assert resp.json()["status"] == target
    assert _block_details(resp.json()) == _NO_BLOCK
    assert _block_details(client.get(f"/api/v1/kanban/tasks/{task_id}").json()) == _NO_BLOCK
    listed = client.get(f"/api/v1/kanban/boards/{board_id}/tasks").json()["items"]
    assert [_block_details(item) for item in listed] == [_NO_BLOCK]


def test_blocking_a_card_again_without_a_reason_starts_from_a_clean_block(client: TestClient) -> None:
    _, task_id = _blocked_task(client, block_kind="human", blocked_reason=_REASON)
    client.post(f"/api/v1/kanban/tasks/{task_id}/move", json={"status": "backlog"})

    resp = client.post(f"/api/v1/kanban/tasks/{task_id}/move", json={"status": "blocked"})

    assert resp.status_code == 200
    assert resp.json()["block_kind"] == "human"
    assert resp.json()["blocked_reason"] is None
    assert resp.json()["scheduled_until"] is None


def test_rescheduling_a_blocked_card_keeps_its_reason(client: TestClient) -> None:
    _, task_id = _blocked_task(client, block_kind="human", blocked_reason=_REASON)

    resp = client.post(
        f"/api/v1/kanban/tasks/{task_id}/move",
        json={"status": "blocked", "block_kind": "scheduled", "scheduled_until": _WAKE_AT},
    )

    assert resp.status_code == 200
    assert resp.json()["blocked_reason"] == _REASON
    assert resp.json()["block_kind"] == "scheduled"
    assert resp.json()["scheduled_until"] is not None
