"""Contract: shared/config/kanban_move_guard.json states exactly which manual moves the server accepts.

The frontend reads the same JSON to stop impossible moves before they reach the server, so this test is what
keeps that file honest. Every (from, to) pair, including "stay where you are", is run through the real
`POST /kanban/tasks/{id}/move` against a task forced into the `from` status.
"""

from __future__ import annotations

import asyncio
import json
from collections.abc import Iterator
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.api.kanban.router import router as kanban_router
from app.services.kanban import KanbanService

_GUARD_PATH = Path(__file__).resolve().parents[4] / "shared" / "config" / "kanban_move_guard.json"
_ALL_STATUSES = [status.value for status in TaskStatus]


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


def _load_guard() -> dict[str, list[str]]:
    raw = json.loads(_GUARD_PATH.read_text(encoding="utf-8"))
    assert isinstance(raw, dict), "kanban_move_guard.json must contain a JSON object"
    guard: dict[str, list[str]] = {}
    for source, targets in raw.items():
        assert isinstance(source, str) and isinstance(targets, list), "each source status maps to a list of target statuses"
        assert all(isinstance(target, str) for target in targets), "targets must be status strings"
        guard[source] = targets
    return guard


async def _force_status(task_id: str, status: TaskStatus) -> None:
    svc = KanbanService.get_instance()
    task = await svc.get_task(task_id)
    assert task is not None
    task.status = status
    await svc.store.save_task(task)


def test_shared_move_guard_covers_every_status_exactly_once() -> None:
    guard = _load_guard()

    assert sorted(guard) == sorted(_ALL_STATUSES)
    for source, targets in guard.items():
        assert len(targets) == len(set(targets)), f"{source} lists a target twice"
        assert set(targets) <= set(_ALL_STATUSES), f"{source} lists an unknown status"


def test_server_move_matches_shared_guard_for_every_status_pair(client: TestClient) -> None:
    guard = _load_guard()
    board = client.post("/api/v1/kanban/boards", json={"name": "Move guard contract"}).json()

    disagreements: list[str] = []
    for source in _ALL_STATUSES:
        for target in _ALL_STATUSES:
            created = client.post(f"/api/v1/kanban/boards/{board['board_id']}/tasks", json={"title": f"{source} to {target}"})
            assert created.status_code == 201
            task_id = created.json()["task_id"]
            asyncio.run(_force_status(task_id, TaskStatus(source)))

            response = client.post(f"/api/v1/kanban/tasks/{task_id}/move", json={"status": target})

            assert response.status_code in (200, 409), f"{source} -> {target}: unexpected {response.status_code} {response.text}"
            server_accepts = response.status_code == 200
            if server_accepts != (target in guard[source]):
                disagreements.append(f"{source} -> {target}: server {'accepts' if server_accepts else 'rejects'}")

    assert not disagreements, "shared/config/kanban_move_guard.json is out of step with the server:\n" + "\n".join(disagreements)
