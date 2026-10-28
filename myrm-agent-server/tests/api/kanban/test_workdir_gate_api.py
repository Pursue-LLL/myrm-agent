"""Kanban working folders go through the workspace path gate, and a board's default folder can be cleared again.

A task's ``workspace_path`` and a board's ``default_workdir`` decide where the task's agent may write, so they
are refused when they are, or contain, a protected location.
"""

from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from httpx import Response
from sqlalchemy import update

from app.api.kanban.router import router as kanban_router
from app.database.connection import get_session
from app.database.models.kanban import KanbanBoardModel
from app.services.kanban import KanbanService

HOME = str(Path.home())


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    KanbanService._instance = None
    yield
    KanbanService._instance = None


@pytest.fixture(autouse=True)
def _skip_agent_validation() -> None:  # type: ignore[misc]
    with patch.object(KanbanService, "_validate_agent_id", new_callable=AsyncMock):
        yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(kanban_router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c


def _refusal(response: Response, *, field: str) -> str:
    """The ``issue`` a 400 names for ``field``."""
    assert response.status_code == 400, response.text
    (detail,) = response.json()["detail"]["error"]["details"]
    assert detail["field"] == field
    return detail["issue"]


def _create_board(client: TestClient, **body: object) -> dict[str, object]:
    response = client.post("/api/v1/kanban/boards", json={"name": "Board", **body})
    assert response.status_code == 201, response.text
    return response.json()


def _create_task(client: TestClient, board_id: str, **body: object) -> Response:
    return client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json={"title": "Task", **body})


def _store_default_workdir(board_id: str, path: str) -> None:
    """Write straight to the table: how a board bound before the gate existed looks."""

    async def _write() -> None:
        async with get_session() as db:
            await db.execute(update(KanbanBoardModel).where(KanbanBoardModel.id == board_id).values(default_workdir=path))
            await db.commit()

    asyncio.run(_write())


class TestTaskWorkspacePath:
    @pytest.mark.parametrize(
        ("path", "issue"),
        [(HOME, "too_broad"), ("/", "too_broad"), (os.path.join(HOME, ".ssh"), "dangerous"), ("relative/dir", "not_absolute")],
    )
    def test_a_path_the_gate_refuses_is_refused(self, client: TestClient, path: str, issue: str) -> None:
        board = _create_board(client)

        response = _create_task(client, str(board["board_id"]), workspace_path=path)

        assert _refusal(response, field="workspace_path") == issue

    def test_an_ordinary_folder_is_stored_canonicalized(self, client: TestClient, tmp_path: Path) -> None:
        board = _create_board(client)

        response = _create_task(client, str(board["board_id"]), workspace_path=str(tmp_path))

        assert response.status_code == 201, response.text
        assert response.json()["workspace_path"] == os.path.realpath(tmp_path)

    def test_a_task_without_a_folder_is_unaffected(self, client: TestClient) -> None:
        board = _create_board(client)

        response = _create_task(client, str(board["board_id"]))

        assert response.status_code == 201
        assert response.json()["workspace_path"] is None


class TestBoardDefaultWorkdir:
    @pytest.mark.parametrize("path", [HOME, "/"])
    def test_creating_a_board_with_a_broad_folder_is_refused(self, client: TestClient, path: str) -> None:
        response = client.post("/api/v1/kanban/boards", json={"name": "Board", "default_workdir": path})

        assert _refusal(response, field="default_workdir") == "too_broad"

    def test_an_ordinary_default_folder_is_stored_canonicalized(self, client: TestClient, tmp_path: Path) -> None:
        board = _create_board(client, default_workdir=str(tmp_path))

        assert board["settings"]["default_workdir"] == os.path.realpath(tmp_path)

    def test_changing_the_default_folder_to_a_broad_one_is_refused(self, client: TestClient) -> None:
        board = _create_board(client)

        response = client.patch(f"/api/v1/kanban/boards/{board['board_id']}", json={"default_workdir": HOME})

        assert _refusal(response, field="default_workdir") == "too_broad"

    def test_an_unrelated_update_does_not_re_judge_the_stored_folder(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = str(board["board_id"])
        _store_default_workdir(board_id, HOME)

        response = client.patch(f"/api/v1/kanban/boards/{board_id}", json={"max_concurrent_tasks": 2})

        assert response.status_code == 200, response.text
        assert response.json()["settings"]["default_workdir"] == HOME

    def test_an_explicit_null_clears_the_stored_folder(self, client: TestClient) -> None:
        board = _create_board(client)
        board_id = str(board["board_id"])
        _store_default_workdir(board_id, HOME)

        response = client.patch(f"/api/v1/kanban/boards/{board_id}", json={"default_workdir": None})

        assert response.status_code == 200, response.text
        assert response.json()["settings"]["default_workdir"] is None
