"""Kanban bulk-action REST API tests.

Covers `POST /boards/{id}/tasks/bulk-action` over HTTP against the real SQLite
store: move / archive / reassign / delete, per-item partial failures, request
validation, and the actions the endpoint deliberately does not offer.
"""

from __future__ import annotations

import logging
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


_BULK_LOGGER = "app.api.kanban.routes.bulk"
_KNOWN_AGENT_IDS = frozenset({"agent-007", "agent-x"})


@pytest.fixture(autouse=True)
def _known_agents() -> None:  # type: ignore[misc]
    """Resolve agent ids like the repository does, so the real validator runs: known ids exist, anything else
    (including the empty string) is missing."""

    async def lookup(agent_id: str) -> object | None:
        return object() if agent_id in _KNOWN_AGENT_IDS else None

    with patch(
        "app.services.agent.agent_service.AgentService.get_agent_by_id",
        new=AsyncMock(side_effect=lookup),
    ):
        yield


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(kanban_router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c


def _create_board(client: TestClient, name: str) -> dict[str, object]:
    resp = client.post("/api/v1/kanban/boards", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_task(client: TestClient, board_id: str, title: str, *, agent_id: str | None = None) -> dict[str, object]:
    body: dict[str, object] = {"title": title}
    if agent_id is not None:
        body["agent_id"] = agent_id
    resp = client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json=body)
    assert resp.status_code == 201
    return resp.json()


class TestBulkAction:
    def test_bulk_move(self, client: TestClient) -> None:
        board = _create_board(client, "BulkBoard")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "T1")
        t2 = _create_task(client, bid, "T2")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"]), str(t2["task_id"])],
                "action": "move",
                "params": {"status": "ready"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 2
        assert data["failed"] == 0

    def test_bulk_archive(self, client: TestClient) -> None:
        board = _create_board(client, "BulkArchive")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "A1")
        t2 = _create_task(client, bid, "A2")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"]), str(t2["task_id"])],
                "action": "archive",
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 2

    def test_bulk_reassign(self, client: TestClient) -> None:
        board = _create_board(client, "BulkReassign")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "R1")
        t2 = _create_task(client, bid, "R2")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"]), str(t2["task_id"])],
                "action": "reassign",
                "params": {"agent_id": "agent-007"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 2

    def test_bulk_delete_requires_confirm(self, client: TestClient) -> None:
        board = _create_board(client, "BulkDel")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "D1")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"])],
                "action": "delete",
            },
        )
        assert resp.status_code == 400

    def test_bulk_delete_with_confirm(self, client: TestClient) -> None:
        board = _create_board(client, "BulkDelOk")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "D1")
        t2 = _create_task(client, bid, "D2")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"]), str(t2["task_id"])],
                "action": "delete",
                "confirm": True,
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 2
        assert data["failed"] == 0

    def test_bulk_invalid_action(self, client: TestClient) -> None:
        board = _create_board(client, "BulkInv")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "I1")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"])],
                "action": "invalid_op",
            },
        )
        assert resp.status_code == 400

    def test_bulk_reclaim_is_not_a_bulk_action(self, client: TestClient) -> None:
        """Reclaim stops a running agent, so it stays a single-task, confirmed action."""
        board = _create_board(client, "BulkNoReclaim")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "NR1")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"])],
                "action": "reclaim",
            },
        )
        assert resp.status_code == 400

    def test_bulk_partial_failure(self, client: TestClient) -> None:
        board = _create_board(client, "BulkPartial")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "P1")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"]), "nonexistent-id"],
                "action": "move",
                "params": {"status": "ready"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert data["succeeded"] == 1
        assert data["failed"] == 1
        assert data["results"][1]["success"] is False
        assert data["results"][1]["error"] is not None

    def test_bulk_move_never_forces_past_unmet_dependencies(self, client: TestClient) -> None:
        """A card whose parents are unfinished fails on its own row, even when the caller asks for force.

        Bulk moves have no force path: forcing a promotion is a per-task decision that the single-task move endpoint
        owns together with its confirmation step.
        """
        board = _create_board(client, "BulkDeps")
        bid = str(board["board_id"])
        parent = _create_task(client, bid, "Parent")
        child = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [str(parent["task_id"])]},
        ).json()
        free = _create_task(client, bid, "Free")
        status_before = client.get(f"/api/v1/kanban/tasks/{child['task_id']}").json()["status"]

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(child["task_id"]), str(free["task_id"])],
                "action": "move",
                "params": {"status": "ready", "force": "true"},
            },
        )

        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 1
        assert data["failed"] == 1
        by_task = {item["task_id"]: item for item in data["results"]}
        assert by_task[str(child["task_id"])]["success"] is False
        assert by_task[str(free["task_id"])]["success"] is True
        assert client.get(f"/api/v1/kanban/tasks/{child['task_id']}").json()["status"] == status_before
        assert status_before != "ready"

    def test_bulk_business_rejection_keeps_its_reason_and_stays_out_of_the_error_log(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        board = _create_board(client, "BulkReason")
        bid = str(board["board_id"])
        parent = _create_task(client, bid, "Parent")
        child = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [str(parent["task_id"])]},
        ).json()

        with caplog.at_level(logging.WARNING, logger=_BULK_LOGGER):
            resp = client.post(
                f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
                json={"task_ids": [str(child["task_id"])], "action": "move", "params": {"status": "ready"}},
            )

        error = resp.json()["results"][0]["error"]
        assert error and error != "Internal error"
        assert [r for r in caplog.records if r.name == _BULK_LOGGER] == []

    def test_bulk_unexpected_error_is_logged_and_hidden_from_the_caller(
        self, client: TestClient, caplog: pytest.LogCaptureFixture
    ) -> None:
        board = _create_board(client, "BulkCrash")
        bid = str(board["board_id"])
        broken = str(_create_task(client, bid, "Broken")["task_id"])
        fine = str(_create_task(client, bid, "Fine")["task_id"])
        real_move = KanbanService.move_task

        async def flaky_move(self: KanbanService, task_id: str, *args: object, **kwargs: object) -> object:
            if task_id == broken:
                raise RuntimeError("disk I/O error at /var/lib/myrm/kanban.db")
            return await real_move(self, task_id, *args, **kwargs)

        with patch.object(KanbanService, "move_task", flaky_move), caplog.at_level(logging.ERROR, logger=_BULK_LOGGER):
            resp = client.post(
                f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
                json={"task_ids": [broken, fine], "action": "move", "params": {"status": "ready"}},
            )

        data = resp.json()
        by_task = {item["task_id"]: item for item in data["results"]}
        assert (data["succeeded"], data["failed"]) == (1, 1)
        assert by_task[fine]["success"] is True
        assert by_task[broken]["error"] == "Internal error"
        assert "kanban.db" not in resp.text
        records = [r for r in caplog.records if r.name == _BULK_LOGGER]
        assert len(records) == 1
        assert records[0].exc_info is not None
        assert "kanban.db" in str(records[0].exc_info[1])

    def test_bulk_move_missing_status_param(self, client: TestClient) -> None:
        board = _create_board(client, "BulkNoStatus")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "NS1")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"])],
                "action": "move",
                "params": {},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1
        assert "Missing params.status" in data["results"][0]["error"]

    def test_bulk_move_invalid_status(self, client: TestClient) -> None:
        board = _create_board(client, "BulkBadStatus")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "BS1")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"])],
                "action": "move",
                "params": {"status": "nonexistent_status"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1
        assert "Invalid status" in data["results"][0]["error"]

    def test_bulk_reassign_unassign(self, client: TestClient) -> None:
        board = _create_board(client, "BulkUnassign")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "U1", agent_id="agent-x")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"])],
                "action": "reassign",
                "params": {"agent_id": ""},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["succeeded"] == 1
        assert client.get(f"/api/v1/kanban/tasks/{t1['task_id']}").json()["agent_id"] is None

    def test_bulk_reassign_unknown_agent_fails_per_item(self, client: TestClient) -> None:
        board = _create_board(client, "BulkUnknownAgent")
        bid = str(board["board_id"])
        t1 = _create_task(client, bid, "K1", agent_id="agent-x")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [str(t1["task_id"])],
                "action": "reassign",
                "params": {"agent_id": "agent-missing"},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["failed"] == 1
        assert "not found" in data["results"][0]["error"]
        assert client.get(f"/api/v1/kanban/tasks/{t1['task_id']}").json()["agent_id"] == "agent-x"

    def test_bulk_empty_task_ids_rejected(self, client: TestClient) -> None:
        board = _create_board(client, "BulkEmpty")
        bid = str(board["board_id"])

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks/bulk-action",
            json={
                "task_ids": [],
                "action": "move",
                "params": {"status": "ready"},
            },
        )
        assert resp.status_code == 422
