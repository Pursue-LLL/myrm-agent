"""Kanban in_review approval-gate REST API tests.

Covers the task-level human approval flow over HTTP:
- require_approval flag on create/update
- approve: IN_REVIEW -> COMPLETED (+ dependent promotion)
- reject: IN_REVIEW -> READY with reason
- error semantics: 404 unknown task, 409 non-reviewable status
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

from app.api.kanban.router import router as kanban_router
from app.services.kanban import KanbanService


@pytest.fixture(autouse=True)
def _reset_singleton() -> None:
    KanbanService._instance = None
    yield
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
        yield c


def _create_board(client: TestClient, name: str = "Review Board") -> dict[str, object]:
    resp = client.post("/api/v1/kanban/boards", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_task(
    client: TestClient,
    board_id: str,
    title: str = "Task",
    *,
    require_approval: bool = False,
    initial_status: str | None = None,
) -> dict[str, object]:
    body: dict[str, object] = {"title": title, "require_approval": require_approval}
    if initial_status is not None:
        body["initial_status"] = initial_status
    resp = client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json=body)
    assert resp.status_code == 201
    return resp.json()


async def _force_status(tid: str, status: TaskStatus) -> None:
    svc = KanbanService.get_instance()
    t = await svc.get_task(tid)
    assert t is not None
    t.status = status
    t.result = "artifact built & verified"
    await svc.store.save_task(t)


class TestRequireApprovalFlag:

    def test_create_task_persists_require_approval(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"], require_approval=True)
        assert task["require_approval"] is True

    def test_create_task_defaults_to_false(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"])
        assert task["require_approval"] is False

    def test_update_task_toggles_require_approval(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"])
        tid = str(task["task_id"])
        resp = client.patch(f"/api/v1/kanban/tasks/{tid}", json={"require_approval": True})
        assert resp.status_code == 200
        assert resp.json()["require_approval"] is True


class TestApproveEndpoint:

    def test_approve_in_review_task_completes_it(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"], require_approval=True)
        tid = str(task["task_id"])
        asyncio.run(_force_status(tid, TaskStatus.IN_REVIEW))

        resp = client.post(f"/api/v1/kanban/tasks/{tid}/approve", json={})
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "completed"
        assert data["completed_at"] is not None

    def test_approve_releases_dependents(self, client: TestClient) -> None:
        board = _create_board(client)
        parent = _create_task(client, board["board_id"], "Parent", require_approval=True)
        child = _create_task(
            client,
            board["board_id"],
            "Child",
            initial_status="backlog",
        )
        svc = KanbanService.get_instance()

        async def _wire() -> None:
            await svc.store.add_edge(
                str(parent["task_id"]),
                str(child["task_id"]),
            )

        asyncio.run(_wire())

        # Put parent into IN_REVIEW as the dispatcher would.
        asyncio.run(_force_status(str(parent["task_id"]), TaskStatus.IN_REVIEW))

        resp = client.post(
            f"/api/v1/kanban/tasks/{parent['task_id']}/approve",
            json={"approver": "alice"},
        )
        assert resp.status_code == 200

        resp_child = client.get(f"/api/v1/kanban/tasks/{child['task_id']}")
        assert resp_child.status_code == 200
        assert resp_child.json()["status"] == "ready"

    def test_approve_unknown_task_returns_404(self, client: TestClient) -> None:
        resp = client.post("/api/v1/kanban/tasks/nope/approve", json={})
        assert resp.status_code == 404

    def test_approve_non_review_task_returns_409(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"])
        tid = str(task["task_id"])
        resp = client.post(f"/api/v1/kanban/tasks/{tid}/approve", json={})
        assert resp.status_code == 409


class TestRejectEndpoint:

    def test_reject_in_review_task_returns_to_ready(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"], require_approval=True)
        tid = str(task["task_id"])
        asyncio.run(_force_status(tid, TaskStatus.IN_REVIEW))

        resp = client.post(
            f"/api/v1/kanban/tasks/{tid}/reject",
            json={"reason": "add source citations"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["error"] == "add source citations"

    def test_reject_unknown_task_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/kanban/tasks/nope/reject",
            json={"reason": "why"},
        )
        assert resp.status_code == 404

    def test_reject_non_review_task_returns_409(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"])
        tid = str(task["task_id"])
        resp = client.post(
            f"/api/v1/kanban/tasks/{tid}/reject",
            json={"reason": "why"},
        )
        assert resp.status_code == 409
