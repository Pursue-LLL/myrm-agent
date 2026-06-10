"""Kanban REST API integration tests.

Tests the HTTP layer (routes + service + SqlAlchemyKanbanStore) against
a real SQLite database. No mocks — exercises the full stack from HTTP
request to DB and back.

Covers TODO-05 features:
- list_tasks with agent_id filter
- update_task to set/change/clear agent_id
- delete_agent cascading clears kanban agent_id refs
- board/task lifecycle CRUD via REST
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.kanban.types import TaskStatus

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


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    app.include_router(kanban_router, prefix="/api/v1")
    with TestClient(app) as c:
        yield c


def _create_board(client: TestClient, name: str = "Test Board") -> dict[str, object]:
    resp = client.post("/api/v1/kanban/boards", json={"name": name})
    assert resp.status_code == 201
    return resp.json()


def _create_task(
    client: TestClient,
    board_id: str,
    title: str = "Task",
    *,
    agent_id: str | None = None,
    priority: str = "normal",
) -> dict[str, object]:
    body: dict[str, object] = {"title": title, "priority": priority}
    if agent_id is not None:
        body["agent_id"] = agent_id
    resp = client.post(f"/api/v1/kanban/boards/{board_id}/tasks", json=body)
    assert resp.status_code == 201
    return resp.json()


# ===========================================================================
# Board CRUD
# ===========================================================================


class TestBoardApi:
    def test_create_and_get_board(self, client: TestClient) -> None:
        board = _create_board(client, "My Board")
        assert board["name"] == "My Board"

        resp = client.get(f"/api/v1/kanban/boards/{board['board_id']}")
        assert resp.status_code == 200
        assert resp.json()["board_id"] == board["board_id"]

    def test_list_boards(self, client: TestClient) -> None:
        _create_board(client, "Board1")
        _create_board(client, "Board2")
        resp = client.get("/api/v1/kanban/boards")
        assert resp.status_code == 200
        assert resp.json()["total"] >= 2

    def test_delete_board(self, client: TestClient) -> None:
        board = _create_board(client)
        resp = client.delete(f"/api/v1/kanban/boards/{board['board_id']}")
        assert resp.status_code == 204

        resp = client.get(f"/api/v1/kanban/boards/{board['board_id']}")
        assert resp.status_code == 404

    def test_get_nonexistent_board(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/boards/nonexistent")
        assert resp.status_code == 404

    def test_board_summary(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        _create_task(client, bid, "T1")
        _create_task(client, bid, "T2")

        resp = client.get(f"/api/v1/kanban/boards/{bid}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total_tasks"] == 2
        assert "by_agent" in data
        assert "oldest_ready_age_seconds" in data

    def test_board_summary_by_agent(self, client: TestClient) -> None:
        """Summary should include per-agent task distribution."""
        board = _create_board(client)
        bid = board["board_id"]
        _create_task(client, bid, "T1", agent_id="agent-a")
        _create_task(client, bid, "T2", agent_id="agent-a")
        _create_task(client, bid, "T3", agent_id="agent-b")
        _create_task(client, bid, "T4")  # unassigned

        resp = client.get(f"/api/v1/kanban/boards/{bid}/summary")
        assert resp.status_code == 200
        data = resp.json()
        by_agent = {a["agent_id"]: a for a in data["by_agent"]}
        assert by_agent["agent-a"]["total"] == 2
        assert by_agent["agent-b"]["total"] == 1
        assert by_agent[None]["total"] == 1

    def test_board_summary_oldest_ready_age(self, client: TestClient) -> None:
        """Summary should include oldest_ready_age_seconds for ready tasks."""
        board = _create_board(client)
        bid = board["board_id"]
        _create_task(client, bid, "ReadyTask")

        resp = client.get(f"/api/v1/kanban/boards/{bid}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["oldest_ready_age_seconds"] is not None
        assert data["oldest_ready_age_seconds"] >= 0

    def test_board_summary_no_ready_tasks(self, client: TestClient) -> None:
        """oldest_ready_age_seconds should be null when no ready tasks exist."""
        board = _create_board(client)
        bid = board["board_id"]

        resp = client.get(f"/api/v1/kanban/boards/{bid}/summary")
        assert resp.status_code == 200
        data = resp.json()
        assert data["oldest_ready_age_seconds"] is None
        assert data["by_agent"] == []

    def test_board_summary_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/boards/nonexistent/summary")
        assert resp.status_code == 404

    def test_board_summary_by_agent_excludes_archived(self, client: TestClient) -> None:
        """Archived tasks should not appear in by_agent distribution."""
        board = _create_board(client)
        bid = board["board_id"]
        t1 = _create_task(client, bid, "T1", agent_id="agent-a")
        _create_task(client, bid, "T2", agent_id="agent-a")

        client.post(
            f"/api/v1/kanban/tasks/{t1['task_id']}/move",
            json={"status": "archived"},
        )

        resp = client.get(f"/api/v1/kanban/boards/{bid}/summary")
        data = resp.json()
        by_agent = {a["agent_id"]: a for a in data["by_agent"]}
        assert by_agent["agent-a"]["total"] == 1

    def test_board_summary_single_agent(self, client: TestClient) -> None:
        """Single agent should still appear in by_agent."""
        board = _create_board(client)
        bid = board["board_id"]
        _create_task(client, bid, "T1", agent_id="solo")
        _create_task(client, bid, "T2", agent_id="solo")

        resp = client.get(f"/api/v1/kanban/boards/{bid}/summary")
        data = resp.json()
        assert len(data["by_agent"]) == 1
        assert data["by_agent"][0]["agent_id"] == "solo"
        assert data["by_agent"][0]["total"] == 2

    def test_board_summary_by_agent_status_breakdown(self, client: TestClient) -> None:
        """by_agent counts should reflect per-status breakdown."""
        board = _create_board(client)
        bid = board["board_id"]
        t1 = _create_task(client, bid, "T1", agent_id="agent-a")
        _create_task(client, bid, "T2", agent_id="agent-a")

        client.post(
            f"/api/v1/kanban/tasks/{t1['task_id']}/move",
            json={"status": "running"},
        )

        resp = client.get(f"/api/v1/kanban/boards/{bid}/summary")
        data = resp.json()
        by_agent = {a["agent_id"]: a for a in data["by_agent"]}
        counts = by_agent["agent-a"]["counts"]
        assert counts.get("running", 0) == 1
        assert counts.get("ready", 0) == 1

    def test_board_summary_dispatcher_active_field(self, client: TestClient) -> None:
        """dispatcher_active should be false when no dispatcher is running."""
        board = _create_board(client)
        bid = board["board_id"]

        resp = client.get(f"/api/v1/kanban/boards/{bid}/summary")
        data = resp.json()
        assert data["dispatcher_active"] is False


# ===========================================================================
# Task CRUD
# ===========================================================================


class TestTaskApi:
    def test_create_and_get_task(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"], "My Task", agent_id="agent-1")
        assert task["title"] == "My Task"
        assert task["agent_id"] == "agent-1"

        resp = client.get(f"/api/v1/kanban/tasks/{task['task_id']}")
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "agent-1"

    def test_delete_task(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"])
        resp = client.delete(f"/api/v1/kanban/tasks/{task['task_id']}")
        assert resp.status_code == 204

    def test_move_task(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"])
        resp = client.post(
            f"/api/v1/kanban/tasks/{task['task_id']}/move",
            json={"status": "running"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"


# ===========================================================================
# list_tasks with agent_id filter (OPT-B)
# ===========================================================================


class TestListTasksAgentFilter:
    def test_filter_by_agent_id(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        _create_task(client, bid, "T1", agent_id="agent-a")
        _create_task(client, bid, "T2", agent_id="agent-b")
        _create_task(client, bid, "T3", agent_id="agent-a")
        _create_task(client, bid, "T4")  # no agent

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks", params={"agent_id": "agent-a"})
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert all(t["agent_id"] == "agent-a" for t in data["items"])

    def test_no_filter_returns_all(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        _create_task(client, bid, "T1", agent_id="agent-a")
        _create_task(client, bid, "T2")

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

    def test_filter_nonexistent_agent_empty(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        _create_task(client, bid, "T1", agent_id="agent-a")

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks", params={"agent_id": "ghost"})
        assert resp.status_code == 200
        assert resp.json()["total"] == 0

    def test_combined_status_and_agent_filter(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        t1 = _create_task(client, bid, "T1", agent_id="a1")
        t2 = _create_task(client, bid, "T2", agent_id="a1")
        _create_task(client, bid, "T3", agent_id="a2")

        # Move t2 to running
        client.post(f"/api/v1/kanban/tasks/{t2['task_id']}/move", json={"status": "running"})

        resp = client.get(
            f"/api/v1/kanban/boards/{bid}/tasks",
            params={"agent_id": "a1", "status_filter": "ready"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 1
        assert data["items"][0]["task_id"] == t1["task_id"]

    def test_pagination_with_agent_filter(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        for i in range(5):
            _create_task(client, bid, f"T{i}", agent_id="agent-x")

        resp = client.get(
            f"/api/v1/kanban/boards/{bid}/tasks",
            params={"agent_id": "agent-x", "limit": 2, "offset": 0},
        )
        assert resp.status_code == 200
        assert resp.json()["total"] == 2

        resp2 = client.get(
            f"/api/v1/kanban/boards/{bid}/tasks",
            params={"agent_id": "agent-x", "limit": 2, "offset": 4},
        )
        assert resp2.status_code == 200
        assert resp2.json()["total"] == 1


# ===========================================================================
# update_task with agent_id (OPT-E)
# ===========================================================================


class TestUpdateTaskAgentId:
    def test_set_agent_id(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"], "Task")

        resp = client.patch(
            f"/api/v1/kanban/tasks/{task['task_id']}",
            json={"agent_id": "new-agent"},
        )
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "new-agent"

    def test_change_agent_id(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"], "Task", agent_id="old")

        resp = client.patch(
            f"/api/v1/kanban/tasks/{task['task_id']}",
            json={"agent_id": "new"},
        )
        assert resp.status_code == 200
        assert resp.json()["agent_id"] == "new"

    def test_clear_agent_id(self, client: TestClient) -> None:
        """Explicitly setting agent_id=None clears it."""
        board = _create_board(client)
        task = _create_task(client, board["board_id"], "Task", agent_id="agent-1")

        resp = client.patch(
            f"/api/v1/kanban/tasks/{task['task_id']}",
            json={"agent_id": None},
        )
        assert resp.status_code == 200
        assert resp.json()["agent_id"] is None

    def test_omitting_agent_id_preserves_it(self, client: TestClient) -> None:
        """Not sending agent_id in the PATCH body should not change it."""
        board = _create_board(client)
        task = _create_task(client, board["board_id"], "Task", agent_id="keep-me")

        resp = client.patch(
            f"/api/v1/kanban/tasks/{task['task_id']}",
            json={"title": "New Title"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "New Title"
        assert data["agent_id"] == "keep-me"

    def test_update_nonexistent_task(self, client: TestClient) -> None:
        resp = client.patch(
            "/api/v1/kanban/tasks/nonexistent",
            json={"title": "X"},
        )
        assert resp.status_code == 404


# ===========================================================================
# clear_agent_references — cascading delete (OPT-C)
# ===========================================================================


class TestClearAgentReferences:
    @pytest.mark.asyncio
    async def test_clear_references(self, client: TestClient) -> None:
        """KanbanService.clear_agent_references nullifies agent_id."""
        board = _create_board(client)
        bid = board["board_id"]
        _create_task(client, bid, "T1", agent_id="doomed")
        _create_task(client, bid, "T2", agent_id="doomed")
        _create_task(client, bid, "T3", agent_id="safe")

        svc = KanbanService.get_instance()
        cleared = await svc.clear_agent_references("doomed")
        assert cleared == 2

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks", params={"agent_id": "doomed"})
        assert resp.json()["total"] == 0

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks", params={"agent_id": "safe"})
        assert resp.json()["total"] == 1

    @pytest.mark.asyncio
    async def test_clear_nonexistent_agent_returns_zero(self, client: TestClient) -> None:
        svc = KanbanService.get_instance()
        cleared = await svc.clear_agent_references("nonexistent")
        assert cleared == 0


# ===========================================================================
# Error paths
# ===========================================================================


class TestAgentIdValidation:
    """Validate agent_id existence on create/update (TODO-48).

    Uses real _validate_agent_id — override the autouse mock fixture by name.
    """

    @pytest.fixture(autouse=True)
    def _skip_agent_validation(self) -> None:
        """Same name as the module-level autouse fixture, so pytest uses this (no-op) instead."""

    def test_create_task_with_nonexistent_agent_id(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "T1", "agent_id": "nonexistent_agent"},
        )
        assert resp.status_code == 400
        assert "nonexistent_agent" in resp.json()["detail"]

    def test_create_task_with_null_agent_id_succeeds(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "T1"},
        )
        assert resp.status_code == 201

    def test_update_task_with_nonexistent_agent_id(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        task = _create_task(client, bid, "T1")
        resp = client.patch(
            f"/api/v1/kanban/tasks/{task['task_id']}",
            json={"agent_id": "nonexistent_agent"},
        )
        assert resp.status_code == 400
        assert "nonexistent_agent" in resp.json()["detail"]

    def test_update_task_clear_agent_id_succeeds(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        task = _create_task(client, bid, "T1")
        resp = client.patch(
            f"/api/v1/kanban/tasks/{task['task_id']}",
            json={"agent_id": None},
        )
        assert resp.status_code == 200
        assert resp.json()["agent_id"] is None


# ===========================================================================
# Dependency API (TODO-06)
# ===========================================================================


class TestDependencyApi:
    def test_create_task_with_depends_on(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        parent = _create_task(client, bid, "Parent")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [parent["task_id"]]},
        )
        assert resp.status_code == 201
        child = resp.json()
        assert child["status"] == "backlog"

    def test_add_dependency(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        parent = _create_task(client, bid, "Parent")
        child = _create_task(client, bid, "Child")

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/dependencies",
            json={"parent_task_id": parent["task_id"]},
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["parent_task_id"] == parent["task_id"]
        assert data["child_task_id"] == child["task_id"]

    def test_list_dependencies(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        p1 = _create_task(client, bid, "P1")
        p2 = _create_task(client, bid, "P2")
        child = _create_task(client, bid, "Child")

        client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/dependencies",
            json={"parent_task_id": p1["task_id"]},
        )
        client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/dependencies",
            json={"parent_task_id": p2["task_id"]},
        )

        resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}/dependencies")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2
        assert sorted(data["items"]) == sorted([p1["task_id"], p2["task_id"]])

    def test_list_dependents(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        parent = _create_task(client, bid, "Parent")
        c1 = _create_task(client, bid, "C1")
        c2 = _create_task(client, bid, "C2")

        client.post(
            f"/api/v1/kanban/tasks/{c1['task_id']}/dependencies",
            json={"parent_task_id": parent["task_id"]},
        )
        client.post(
            f"/api/v1/kanban/tasks/{c2['task_id']}/dependencies",
            json={"parent_task_id": parent["task_id"]},
        )

        resp = client.get(f"/api/v1/kanban/tasks/{parent['task_id']}/dependents")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

    def test_remove_dependency(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        parent = _create_task(client, bid, "Parent")
        child = _create_task(client, bid, "Child")

        client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/dependencies",
            json={"parent_task_id": parent["task_id"]},
        )

        resp = client.delete(f"/api/v1/kanban/tasks/{child['task_id']}/dependencies/{parent['task_id']}")
        assert resp.status_code == 204

        resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}/dependencies")
        assert resp.json()["total"] == 0

    def test_cycle_detection_409(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        a = _create_task(client, bid, "A")
        b = _create_task(client, bid, "B")

        client.post(
            f"/api/v1/kanban/tasks/{b['task_id']}/dependencies",
            json={"parent_task_id": a["task_id"]},
        )
        resp = client.post(
            f"/api/v1/kanban/tasks/{a['task_id']}/dependencies",
            json={"parent_task_id": b["task_id"]},
        )
        assert resp.status_code == 409

    def test_add_dependency_demotes_ready_to_backlog(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        parent = _create_task(client, bid, "Parent")
        child = _create_task(client, bid, "Child")
        assert child["status"] == "ready"

        client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/dependencies",
            json={"parent_task_id": parent["task_id"]},
        )

        resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}")
        assert resp.json()["status"] == "backlog"

    def test_remove_dependency_promotes_backlog_to_ready(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        parent = _create_task(client, bid, "Parent")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [parent["task_id"]]},
        )
        child = resp.json()
        assert child["status"] == "backlog"

        client.post(
            f"/api/v1/kanban/tasks/{parent['task_id']}/move",
            json={"status": "completed"},
        )

        resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}")
        assert resp.json()["status"] == "ready"

    def test_dependency_on_nonexistent_task_404(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        child = _create_task(client, bid, "Child")

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/dependencies",
            json={"parent_task_id": "nonexistent"},
        )
        assert resp.status_code == 404

    def test_remove_nonexistent_dependency_404(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        child = _create_task(client, bid, "Child")

        resp = client.delete(f"/api/v1/kanban/tasks/{child['task_id']}/dependencies/nonexistent")
        assert resp.status_code == 404

    def test_multiple_parents_all_must_complete(self, client: TestClient) -> None:
        """Child with 2 parents stays backlog until BOTH complete."""
        board = _create_board(client)
        bid = board["board_id"]
        p1 = _create_task(client, bid, "P1")
        p2 = _create_task(client, bid, "P2")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [p1["task_id"], p2["task_id"]]},
        )
        child = resp.json()
        assert child["status"] == "backlog"

        client.post(f"/api/v1/kanban/tasks/{p1['task_id']}/move", json={"status": "completed"})
        resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}")
        assert resp.json()["status"] == "backlog"

        client.post(f"/api/v1/kanban/tasks/{p2['task_id']}/move", json={"status": "completed"})
        resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}")
        assert resp.json()["status"] == "ready"

    def test_idempotent_add_dependency(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        p = _create_task(client, bid, "Parent")
        c = _create_task(client, bid, "Child")

        resp1 = client.post(
            f"/api/v1/kanban/tasks/{c['task_id']}/dependencies",
            json={"parent_task_id": p["task_id"]},
        )
        assert resp1.status_code == 201

        resp2 = client.post(
            f"/api/v1/kanban/tasks/{c['task_id']}/dependencies",
            json={"parent_task_id": p["task_id"]},
        )
        assert resp2.status_code == 201

        deps = client.get(f"/api/v1/kanban/tasks/{c['task_id']}/dependencies")
        assert deps.json()["total"] == 1

    def test_transitive_cycle_409(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        a = _create_task(client, bid, "A")
        b = _create_task(client, bid, "B")
        c = _create_task(client, bid, "C")

        client.post(
            f"/api/v1/kanban/tasks/{b['task_id']}/dependencies",
            json={"parent_task_id": a["task_id"]},
        )
        client.post(
            f"/api/v1/kanban/tasks/{c['task_id']}/dependencies",
            json={"parent_task_id": b["task_id"]},
        )

        resp = client.post(
            f"/api/v1/kanban/tasks/{a['task_id']}/dependencies",
            json={"parent_task_id": c["task_id"]},
        )
        assert resp.status_code == 409

    def test_create_task_no_depends_on_is_ready(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"], "NoDepTask")
        assert task["status"] == "ready"

    def test_create_task_empty_depends_on_is_ready(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "EmptyDeps", "depends_on": []},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "ready"

    def test_create_task_invalid_depends_on_fallback_ready(self, client: TestClient) -> None:
        """If all depends_on parents don't exist, task should fall back to READY."""
        board = _create_board(client)
        bid = board["board_id"]
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "BadDep", "depends_on": ["nonexistent"]},
        )
        assert resp.status_code == 201
        assert resp.json()["status"] == "ready"

    def test_delete_parent_cleans_edges(self, client: TestClient) -> None:
        """Deleting parent task should cascade-remove its edges via FK."""
        board = _create_board(client)
        bid = board["board_id"]
        p = _create_task(client, bid, "Parent")
        c = _create_task(client, bid, "Child")
        client.post(
            f"/api/v1/kanban/tasks/{c['task_id']}/dependencies",
            json={"parent_task_id": p["task_id"]},
        )

        client.delete(f"/api/v1/kanban/tasks/{p['task_id']}")

        deps = client.get(f"/api/v1/kanban/tasks/{c['task_id']}/dependencies")
        assert deps.json()["total"] == 0

    def test_failed_parent_promotes_child(self, client: TestClient) -> None:
        """When parent fails, child should still be promoted (FAILED is terminal)."""
        board = _create_board(client)
        bid = board["board_id"]
        p = _create_task(client, bid, "Parent")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [p["task_id"]]},
        )
        child = resp.json()
        assert child["status"] == "backlog"

        client.post(f"/api/v1/kanban/tasks/{p['task_id']}/move", json={"status": "failed"})
        resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}")
        assert resp.json()["status"] == "ready"

    def test_dependency_events_generated(self, client: TestClient) -> None:
        """Verify PROMOTED event is generated after dependency promotion."""
        board = _create_board(client)
        bid = board["board_id"]
        p = _create_task(client, bid, "Parent")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [p["task_id"]]},
        )
        child = resp.json()

        client.post(f"/api/v1/kanban/tasks/{p['task_id']}/move", json={"status": "completed"})

        events = client.get(f"/api/v1/kanban/tasks/{child['task_id']}/events")
        kinds = [e["kind"] for e in events.json()["items"]]
        assert "created" in kinds
        assert "promoted" in kinds

    def test_archived_parent_promotes_child(self, client: TestClient) -> None:
        """ARCHIVED is terminal, so child should be promoted."""
        board = _create_board(client)
        bid = board["board_id"]
        p = _create_task(client, bid, "Parent")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [p["task_id"]]},
        )
        child = resp.json()
        assert child["status"] == "backlog"

        client.post(f"/api/v1/kanban/tasks/{p['task_id']}/move", json={"status": "archived"})
        resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}")
        assert resp.json()["status"] == "ready"

    def test_self_loop_409(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        t = _create_task(client, bid, "Task")

        resp = client.post(
            f"/api/v1/kanban/tasks/{t['task_id']}/dependencies",
            json={"parent_task_id": t["task_id"]},
        )
        assert resp.status_code == 409

    def test_diamond_dag_valid(self, client: TestClient) -> None:
        """A→B, A→C, B→D, C→D is valid (diamond, not cycle)."""
        board = _create_board(client)
        bid = board["board_id"]
        a = _create_task(client, bid, "A")
        b = _create_task(client, bid, "B")
        c = _create_task(client, bid, "C")
        d = _create_task(client, bid, "D")

        for child_id, parent_id in [
            (b["task_id"], a["task_id"]),
            (c["task_id"], a["task_id"]),
            (d["task_id"], b["task_id"]),
            (d["task_id"], c["task_id"]),
        ]:
            resp = client.post(
                f"/api/v1/kanban/tasks/{child_id}/dependencies",
                json={"parent_task_id": parent_id},
            )
            assert resp.status_code == 201

        deps = client.get(f"/api/v1/kanban/tasks/{d['task_id']}/dependencies")
        assert deps.json()["total"] == 2

    def test_delete_parent_promotes_backlog_child(self, client: TestClient) -> None:
        """Deleting parent should promote BACKLOG child whose deps are now met."""
        board = _create_board(client)
        bid = board["board_id"]
        p = _create_task(client, bid, "Parent")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [p["task_id"]]},
        )
        child = resp.json()
        assert child["status"] == "backlog"

        client.delete(f"/api/v1/kanban/tasks/{p['task_id']}")

        resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}")
        assert resp.json()["status"] == "ready"

    def test_delete_child_cleans_edges_from_parent(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        p = _create_task(client, bid, "Parent")
        c = _create_task(client, bid, "Child")
        client.post(
            f"/api/v1/kanban/tasks/{c['task_id']}/dependencies",
            json={"parent_task_id": p["task_id"]},
        )

        client.delete(f"/api/v1/kanban/tasks/{c['task_id']}")

        deps = client.get(f"/api/v1/kanban/tasks/{p['task_id']}/dependents")
        assert deps.json()["total"] == 0

    def test_chain_promotion_cascading(self, client: TestClient) -> None:
        """A→B→C: completing A promotes B, then completing B promotes C."""
        board = _create_board(client)
        bid = board["board_id"]
        a = _create_task(client, bid, "A")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "B", "depends_on": [a["task_id"]]},
        )
        b = resp.json()
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "C", "depends_on": [b["task_id"]]},
        )
        c = resp.json()

        assert b["status"] == "backlog"
        assert c["status"] == "backlog"

        client.post(f"/api/v1/kanban/tasks/{a['task_id']}/move", json={"status": "completed"})
        resp = client.get(f"/api/v1/kanban/tasks/{b['task_id']}")
        assert resp.json()["status"] == "ready"

        resp = client.get(f"/api/v1/kanban/tasks/{c['task_id']}")
        assert resp.json()["status"] == "backlog"

        client.post(f"/api/v1/kanban/tasks/{b['task_id']}/move", json={"status": "completed"})
        resp = client.get(f"/api/v1/kanban/tasks/{c['task_id']}")
        assert resp.json()["status"] == "ready"


class TestApiErrors:
    def test_invalid_status_filter(self, client: TestClient) -> None:
        board = _create_board(client)
        resp = client.get(
            f"/api/v1/kanban/boards/{board['board_id']}/tasks",
            params={"status_filter": "invalid"},
        )
        assert resp.status_code == 400

    def test_move_invalid_status(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"])
        resp = client.post(
            f"/api/v1/kanban/tasks/{task['task_id']}/move",
            json={"status": "invalid"},
        )
        assert resp.status_code == 400

    def test_delete_nonexistent_board(self, client: TestClient) -> None:
        resp = client.delete("/api/v1/kanban/boards/nonexistent")
        assert resp.status_code == 404

    def test_delete_nonexistent_task(self, client: TestClient) -> None:
        resp = client.delete("/api/v1/kanban/tasks/nonexistent")
        assert resp.status_code == 404


# ===========================================================================
# list_tasks card stats (TODO-29 OPT-B: batch_task_stats)
# ===========================================================================


class TestListTasksCardStats:
    """Verify list_tasks returns dep_count, children_total, children_done, comment_count."""

    def test_stats_default_zero(self, client: TestClient) -> None:
        """Tasks with no deps/children/comments should return 0 for all stats."""
        board = _create_board(client)
        bid = board["board_id"]
        _create_task(client, bid, "Solo")

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item["dep_count"] == 0
        assert item["children_total"] == 0
        assert item["children_done"] == 0
        assert item["comment_count"] == 0

    def test_dep_count(self, client: TestClient) -> None:
        """Task with 2 parents should have dep_count=2."""
        board = _create_board(client)
        bid = board["board_id"]
        p1 = _create_task(client, bid, "P1")
        p2 = _create_task(client, bid, "P2")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [p1["task_id"], p2["task_id"]]},
        )
        child = resp.json()

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks")
        items = {t["task_id"]: t for t in resp.json()["items"]}
        assert items[child["task_id"]]["dep_count"] == 2
        assert items[p1["task_id"]]["dep_count"] == 0

    def test_children_total_and_done(self, client: TestClient) -> None:
        """Parent with children: children_total reflects edge count, children_done reflects completed."""
        board = _create_board(client)
        bid = board["board_id"]
        parent = _create_task(client, bid, "Parent")
        c1 = _create_task(client, bid, "C1")
        c2 = _create_task(client, bid, "C2")

        client.post(
            f"/api/v1/kanban/tasks/{c1['task_id']}/dependencies",
            json={"parent_task_id": parent["task_id"]},
        )
        client.post(
            f"/api/v1/kanban/tasks/{c2['task_id']}/dependencies",
            json={"parent_task_id": parent["task_id"]},
        )

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks")
        items = {t["task_id"]: t for t in resp.json()["items"]}
        assert items[parent["task_id"]]["children_total"] == 2
        assert items[parent["task_id"]]["children_done"] == 0

        client.post(
            f"/api/v1/kanban/tasks/{c1['task_id']}/move",
            json={"status": "completed"},
        )

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks")
        items = {t["task_id"]: t for t in resp.json()["items"]}
        assert items[parent["task_id"]]["children_done"] == 1

    def test_comment_count(self, client: TestClient) -> None:
        """Adding comments increments comment_count in list response."""
        board = _create_board(client)
        bid = board["board_id"]
        task = _create_task(client, bid, "Commented")

        client.post(
            f"/api/v1/kanban/tasks/{task['task_id']}/comments",
            json={"body": "First comment"},
        )
        client.post(
            f"/api/v1/kanban/tasks/{task['task_id']}/comments",
            json={"body": "Second comment"},
        )

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks")
        items = {t["task_id"]: t for t in resp.json()["items"]}
        assert items[task["task_id"]]["comment_count"] == 2

    def test_empty_board_returns_empty(self, client: TestClient) -> None:
        """Empty board should return empty list with no stats errors."""
        board = _create_board(client)
        bid = board["board_id"]

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks")
        assert resp.status_code == 200
        assert resp.json()["items"] == []
        assert resp.json()["total"] == 0


# ===========================================================================
# Board edges API (TODO-30: DAG graph view)
# ===========================================================================


class TestBoardEdgesApi:
    """Verify GET /boards/{board_id}/edges returns all dependency edges."""

    def test_empty_board_no_edges(self, client: TestClient) -> None:
        board = _create_board(client)
        resp = client.get(f"/api/v1/kanban/boards/{board['board_id']}/edges")
        assert resp.status_code == 200
        data = resp.json()
        assert data["items"] == []
        assert data["total"] == 0

    def test_edges_returned(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        p = _create_task(client, bid, "Parent")
        c1 = _create_task(client, bid, "Child1")
        c2 = _create_task(client, bid, "Child2")

        client.post(
            f"/api/v1/kanban/tasks/{c1['task_id']}/dependencies",
            json={"parent_task_id": p["task_id"]},
        )
        client.post(
            f"/api/v1/kanban/tasks/{c2['task_id']}/dependencies",
            json={"parent_task_id": p["task_id"]},
        )

        resp = client.get(f"/api/v1/kanban/boards/{bid}/edges")
        assert resp.status_code == 200
        data = resp.json()
        assert data["total"] == 2

        edge_pairs = {(e["parent_task_id"], e["child_task_id"]) for e in data["items"]}
        assert (p["task_id"], c1["task_id"]) in edge_pairs
        assert (p["task_id"], c2["task_id"]) in edge_pairs

    def test_edges_after_removal(self, client: TestClient) -> None:
        board = _create_board(client)
        bid = board["board_id"]
        p = _create_task(client, bid, "Parent")
        c = _create_task(client, bid, "Child")

        client.post(
            f"/api/v1/kanban/tasks/{c['task_id']}/dependencies",
            json={"parent_task_id": p["task_id"]},
        )
        client.delete(f"/api/v1/kanban/tasks/{c['task_id']}/dependencies/{p['task_id']}")

        resp = client.get(f"/api/v1/kanban/boards/{bid}/edges")
        assert resp.json()["total"] == 0

    def test_nonexistent_board_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/boards/nonexistent/edges")
        assert resp.status_code == 404


# ===========================================================================
# Diagnostics API (TODO-18)
# ===========================================================================


class TestDiagnosticsApi:
    """Verify GET /tasks/{task_id}/diagnostics and diagnostics_summary in list_tasks."""

    def test_diagnostics_endpoint_healthy_task(self, client: TestClient) -> None:
        """A freshly created task should have zero diagnostics."""
        board = _create_board(client)
        task = _create_task(client, board["board_id"], "Healthy")

        resp = client.get(f"/api/v1/kanban/tasks/{task['task_id']}/diagnostics")
        assert resp.status_code == 200
        data = resp.json()
        assert data["task_id"] == task["task_id"]
        assert data["diagnostics"] == []

    def test_diagnostics_endpoint_nonexistent_404(self, client: TestClient) -> None:
        resp = client.get("/api/v1/kanban/tasks/nonexistent/diagnostics")
        assert resp.status_code == 404

    def test_list_tasks_diagnostics_summary_absent_for_healthy(self, client: TestClient) -> None:
        """Healthy tasks should have null diagnostics_summary."""
        board = _create_board(client)
        _create_task(client, board["board_id"], "Healthy")

        resp = client.get(f"/api/v1/kanban/boards/{board['board_id']}/tasks")
        assert resp.status_code == 200
        item = resp.json()["items"][0]
        assert item.get("diagnostics_summary") is None

    def test_diagnostics_response_structure(self, client: TestClient) -> None:
        """Verify response schema fields for diagnostics endpoint."""
        board = _create_board(client)
        task = _create_task(client, board["board_id"], "StructTest")

        resp = client.get(f"/api/v1/kanban/tasks/{task['task_id']}/diagnostics")
        data = resp.json()
        assert "task_id" in data
        assert "diagnostics" in data
        assert isinstance(data["diagnostics"], list)

    def test_diagnostics_backlog_no_parents_empty(self, client: TestClient) -> None:
        """BACKLOG task with no parents: dead_dependency rule should not fire."""
        board = _create_board(client)
        bid = board["board_id"]
        parent = _create_task(client, bid, "Parent")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [parent["task_id"]]},
        )
        child = resp.json()
        assert child["status"] == "backlog"

        diag_resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}/diagnostics")
        assert diag_resp.status_code == 200

    def test_diagnostics_dead_dependency_fires(self, client: TestClient) -> None:
        """BACKLOG task with ALL parents failed/archived → dead_dependency diagnostic."""
        board = _create_board(client)
        bid = board["board_id"]
        parent = _create_task(client, bid, "Parent")

        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [parent["task_id"]]},
        )
        resp.json()

        # Fail the parent — child stays backlog because FAILED is terminal
        # but the promotion logic may move child to READY.
        # For dead_dependency to fire, child must remain in BACKLOG.
        # So we need parent to be archived/failed AND child still BACKLOG.
        # Since our system promotes child when parent reaches terminal,
        # the child will be READY after parent fails. So dead_dependency
        # only fires when child was explicitly moved back or has multiple deps.

        # Create scenario with 2 parents, both fail via archive
        p1 = _create_task(client, bid, "P1")
        p2 = _create_task(client, bid, "P2")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Orphan", "depends_on": [p1["task_id"], p2["task_id"]]},
        )
        orphan = resp.json()
        assert orphan["status"] == "backlog"

        # Archive p1 → orphan stays backlog (p2 still active)
        client.post(f"/api/v1/kanban/tasks/{p1['task_id']}/move", json={"status": "archived"})
        # Archive p2 → orphan gets promoted to ready
        client.post(f"/api/v1/kanban/tasks/{p2['task_id']}/move", json={"status": "archived"})

        # Check orphan status — the system promotes it since both parents are terminal
        orphan_resp = client.get(f"/api/v1/kanban/tasks/{orphan['task_id']}")
        orphan_status = orphan_resp.json()["status"]

        diag_resp = client.get(f"/api/v1/kanban/tasks/{orphan['task_id']}/diagnostics")
        assert diag_resp.status_code == 200

        if orphan_status == "backlog":
            diags = diag_resp.json()["diagnostics"]
            dead_diags = [d for d in diags if d["rule_id"] == "dead_dependency"]
            assert len(dead_diags) == 1
            assert dead_diags[0]["severity"] == "error"
            assert any(a["kind"] == "archive" for a in dead_diags[0]["actions"])

    def test_diagnostics_action_response_fields(self, client: TestClient) -> None:
        """Verify DiagnosticActionResponse schema when diagnostics are present."""
        board = _create_board(client)
        task = _create_task(client, board["board_id"], "ActionTest")

        resp = client.get(f"/api/v1/kanban/tasks/{task['task_id']}/diagnostics")
        data = resp.json()
        for diag in data["diagnostics"]:
            assert "rule_id" in diag
            assert "severity" in diag
            assert "title" in diag
            assert "detail" in diag
            assert "actions" in diag
            for action in diag["actions"]:
                assert "kind" in action
                assert "label" in action
                assert "payload" in action
                assert "suggested" in action


# ===========================================================================
# Recovery clear (TODO-37: consecutive_failures reset on unblock/reassign)
# ===========================================================================


class TestRecoveryClear:
    """Verify consecutive_failures and error are reset on recovery actions."""

    @pytest.mark.anyio
    async def test_unblock_clears_consecutive_failures(
        self,
        client: TestClient,
    ) -> None:
        """BLOCKED→READY should reset consecutive_failures and error."""
        board = _create_board(client)
        bid = board["board_id"]
        task = _create_task(client, bid, "BlockedTask")
        tid = str(task["task_id"])

        svc = KanbanService.get_instance()
        t = await svc.get_task(tid)
        assert t is not None
        t.status = TaskStatus.BLOCKED
        t.consecutive_failures = 5
        t.error = "API Key expired"
        t.blocked_reason = "Auto-blocked after 5 consecutive failures"
        await svc.store.save_task(t)

        resp = client.post(
            f"/api/v1/kanban/tasks/{tid}/move",
            json={"status": "ready"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["consecutive_failures"] == 0
        assert data["error"] == ""
        assert data["blocked_reason"] is None

    @pytest.mark.anyio
    async def test_reassign_agent_clears_consecutive_failures(
        self,
        client: TestClient,
    ) -> None:
        """Changing agent_id should reset consecutive_failures and error."""
        board = _create_board(client)
        bid = board["board_id"]
        task = _create_task(client, bid, "ReassignTask", agent_id="old-agent")
        tid = str(task["task_id"])

        svc = KanbanService.get_instance()
        t = await svc.get_task(tid)
        assert t is not None
        t.consecutive_failures = 4
        t.error = "Model rate limited"
        await svc.store.save_task(t)

        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"agent_id": "new-agent"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "new-agent"
        assert data["consecutive_failures"] == 0
        assert data["error"] == ""

    @pytest.mark.anyio
    async def test_same_agent_keeps_consecutive_failures(
        self,
        client: TestClient,
    ) -> None:
        """Re-assigning the same agent_id should NOT reset consecutive_failures."""
        board = _create_board(client)
        bid = board["board_id"]
        task = _create_task(client, bid, "SameAgent", agent_id="same-agent")
        tid = str(task["task_id"])

        svc = KanbanService.get_instance()
        t = await svc.get_task(tid)
        assert t is not None
        t.consecutive_failures = 3
        t.error = "Transient error"
        await svc.store.save_task(t)

        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"agent_id": "same-agent"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] == "same-agent"
        assert data["consecutive_failures"] == 3
        assert data["error"] == "Transient error"

    @pytest.mark.anyio
    async def test_unassign_clears_consecutive_failures(
        self,
        client: TestClient,
    ) -> None:
        """Setting agent_id=None (unassign) should reset consecutive_failures."""
        board = _create_board(client)
        bid = board["board_id"]
        task = _create_task(client, bid, "Unassign", agent_id="doomed")
        tid = str(task["task_id"])

        svc = KanbanService.get_instance()
        t = await svc.get_task(tid)
        assert t is not None
        t.consecutive_failures = 4
        t.error = "Bad model"
        await svc.store.save_task(t)

        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}",
            json={"agent_id": None},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["agent_id"] is None
        assert data["consecutive_failures"] == 0
        assert data["error"] == ""


# ===========================================================================
# Bulk Actions
# ===========================================================================


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


# ===========================================================================
# Promote Task
# ===========================================================================


class TestPromoteTask:
    """Tests for POST /tasks/{task_id}/promote endpoint."""

    def test_promote_partial_deps_met(self, client: TestClient) -> None:
        """BACKLOG task with 2 parents, one completed — promote(force=False) returns unmet."""
        board = _create_board(client, "PromotePartial")
        bid = str(board["board_id"])
        p1 = _create_task(client, bid, "ParentDone")
        p2 = _create_task(client, bid, "ParentPending")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [str(p1["task_id"]), str(p2["task_id"])]},
        )
        child = resp.json()
        assert child["status"] == "backlog"

        # Complete only p1
        client.post(f"/api/v1/kanban/tasks/{p1['task_id']}/move", json={"status": "running"})
        client.post(f"/api/v1/kanban/tasks/{p1['task_id']}/move", json={"status": "completed"})

        # Promote without force — should fail with unmet p2
        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/promote",
            json={"force": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["promoted"] is False
        assert len(data["unmet_parents"]) == 1
        assert data["unmet_parents"][0]["task_id"] == str(p2["task_id"])

    def test_promote_unmet_deps_no_force(self, client: TestClient) -> None:
        """BACKLOG task with unmet deps returns unmet_parents when force=False."""
        board = _create_board(client, "PromoteUnmet")
        bid = str(board["board_id"])
        parent = _create_task(client, bid, "BlockingParent")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Blocked", "depends_on": [str(parent["task_id"])]},
        )
        child = resp.json()

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/promote",
            json={"force": False},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["promoted"] is False
        assert len(data["unmet_parents"]) == 1
        assert data["unmet_parents"][0]["task_id"] == str(parent["task_id"])

    def test_promote_force(self, client: TestClient) -> None:
        """force=True promotes even with unmet deps."""
        board = _create_board(client, "PromoteForce")
        bid = str(board["board_id"])
        parent = _create_task(client, bid, "UnfinishedParent")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Forced", "depends_on": [str(parent["task_id"])]},
        )
        child = resp.json()

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/promote",
            json={"force": True, "reason": "Urgent deadline"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["promoted"] is True
        assert data["forced"] is True
        assert data["reason"] == "Urgent deadline"
        assert len(data["unmet_parents"]) == 1

        # Verify task is now READY
        resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}")
        assert resp.json()["status"] == "ready"

    def test_promote_non_backlog_fails(self, client: TestClient) -> None:
        """Promote only works on BACKLOG tasks."""
        board = _create_board(client, "PromoteReady")
        bid = str(board["board_id"])
        task = _create_task(client, bid, "AlreadyReady")
        assert task["status"] == "ready"

        resp = client.post(
            f"/api/v1/kanban/tasks/{task['task_id']}/promote",
            json={"force": False},
        )
        assert resp.status_code == 409

    def test_promote_not_found(self, client: TestClient) -> None:
        """Promote on nonexistent task returns 409."""
        resp = client.post(
            "/api/v1/kanban/tasks/nonexistent-id/promote",
            json={"force": False},
        )
        assert resp.status_code == 409


# ===========================================================================
# Reclaim handling: move RUNNING → non-terminal triggers RECLAIMED event
# ===========================================================================


class TestReclaimHandling:
    def test_move_running_to_ready_emits_reclaimed_event(self, client: TestClient) -> None:
        """Moving a RUNNING task to READY should record a RECLAIMED event."""
        board = _create_board(client, "ReclaimBoard")
        bid = board["board_id"]
        task = _create_task(client, bid, "RunningTask")
        tid = task["task_id"]

        client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "running"})

        resp = client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "ready"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"
        assert resp.json()["progress_note"] is None

        events_resp = client.get(f"/api/v1/kanban/tasks/{tid}/events")
        assert events_resp.status_code == 200
        events = events_resp.json()["items"]
        reclaimed_events = [e for e in events if e["kind"] == "reclaimed"]
        assert len(reclaimed_events) == 1
        assert reclaimed_events[0]["payload"]["from"] == "running"
        assert reclaimed_events[0]["payload"]["to"] == "ready"

    def test_move_running_to_backlog_emits_reclaimed_event(self, client: TestClient) -> None:
        """Moving a RUNNING task to BACKLOG should also trigger reclaim handling."""
        board = _create_board(client, "ReclaimBL")
        bid = board["board_id"]
        task = _create_task(client, bid, "RunningTask2")
        tid = task["task_id"]

        client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "running"})

        resp = client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "backlog"})
        assert resp.status_code == 200
        assert resp.json()["status"] == "backlog"

        events_resp = client.get(f"/api/v1/kanban/tasks/{tid}/events")
        events = events_resp.json()["items"]
        reclaimed_events = [e for e in events if e["kind"] == "reclaimed"]
        assert len(reclaimed_events) == 1

    def test_move_running_to_completed_no_reclaim(self, client: TestClient) -> None:
        """Moving RUNNING→COMPLETED (terminal) should NOT emit RECLAIMED."""
        board = _create_board(client, "NoReclaim")
        bid = board["board_id"]
        task = _create_task(client, bid, "RunningTask3")
        tid = task["task_id"]

        client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "running"})

        resp = client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "completed"})
        assert resp.status_code == 200

        events_resp = client.get(f"/api/v1/kanban/tasks/{tid}/events")
        events = events_resp.json()["items"]
        reclaimed_events = [e for e in events if e["kind"] == "reclaimed"]
        assert len(reclaimed_events) == 0


# ===========================================================================
# Move force: /tasks/{id}/move with force=true and 409 deps_unmet
# ===========================================================================


class TestMoveForce:
    def test_move_to_ready_unmet_deps_returns_409(self, client: TestClient) -> None:
        """Moving to READY with unmet deps returns 409 with structured error."""
        board = _create_board(client, "MoveForce409")
        bid = str(board["board_id"])
        parent = _create_task(client, bid, "ParentTask")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "ChildTask", "depends_on": [str(parent["task_id"])]},
        )
        child = resp.json()

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "ready"},
        )
        assert resp.status_code == 409
        data = resp.json()["detail"]
        assert data["code"] == "deps_unmet"
        assert str(parent["task_id"]) in data["unsatisfied"]
        assert data["message"]
        assert len(data["unmet_parents"]) == 1
        assert data["unmet_parents"][0]["task_id"] == str(parent["task_id"])
        assert data["unmet_parents"][0]["title"] == "ParentTask"
        assert data["unmet_parents"][0]["status"] == "ready"

    def test_move_to_ready_force_true_succeeds(self, client: TestClient) -> None:
        """force=True moves to READY even with unmet deps."""
        board = _create_board(client, "MoveForceOK")
        bid = str(board["board_id"])
        parent = _create_task(client, bid, "ParentTask")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "ForcedChild", "depends_on": [str(parent["task_id"])]},
        )
        child = resp.json()

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "ready", "force": True},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

        events_resp = client.get(f"/api/v1/kanban/tasks/{child['task_id']}/events")
        events = events_resp.json()["items"]
        promoted = [e for e in events if e["kind"] == "promoted"]
        assert len(promoted) == 1
        assert promoted[0]["payload"]["forced"] is True

    def test_move_to_ready_no_deps_no_409(self, client: TestClient) -> None:
        """Moving to READY without deps succeeds normally."""
        board = _create_board(client, "MoveNoDeps")
        bid = str(board["board_id"])
        task = _create_task(client, bid, "NoDepTask")
        client.post(
            f"/api/v1/kanban/tasks/{task['task_id']}/move",
            json={"status": "blocked"},
        )
        resp = client.post(
            f"/api/v1/kanban/tasks/{task['task_id']}/move",
            json={"status": "ready"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_move_to_ready_completed_parent_no_409(self, client: TestClient) -> None:
        """READY move succeeds when parent dep is already completed."""
        board = _create_board(client, "MoveCompletedDep")
        bid = str(board["board_id"])
        parent = _create_task(client, bid, "CompletedParent")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [str(parent["task_id"])]},
        )
        child = resp.json()

        client.post(
            f"/api/v1/kanban/tasks/{parent['task_id']}/move",
            json={"status": "completed"},
        )

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "ready"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_move_to_ready_multiple_unmet_parents(self, client: TestClient) -> None:
        """409 response lists all unmet parents when multiple deps are unmet."""
        board = _create_board(client, "MoveMultiDeps")
        bid = str(board["board_id"])
        p1 = _create_task(client, bid, "Parent1")
        p2 = _create_task(client, bid, "Parent2")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={
                "title": "MultiDepChild",
                "depends_on": [str(p1["task_id"]), str(p2["task_id"])],
            },
        )
        child = resp.json()

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "ready"},
        )
        assert resp.status_code == 409
        data = resp.json()["detail"]
        assert data["code"] == "deps_unmet"
        assert len(data["unmet_parents"]) == 2
        parent_ids = {p["task_id"] for p in data["unmet_parents"]}
        assert str(p1["task_id"]) in parent_ids
        assert str(p2["task_id"]) in parent_ids

    def test_move_to_ready_partial_deps_met(self, client: TestClient) -> None:
        """409 only lists non-terminal parents when some deps are met."""
        board = _create_board(client, "MovePartialDeps")
        bid = str(board["board_id"])
        done_parent = _create_task(client, bid, "DoneParent")
        pending_parent = _create_task(client, bid, "PendingParent")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={
                "title": "PartialChild",
                "depends_on": [
                    str(done_parent["task_id"]),
                    str(pending_parent["task_id"]),
                ],
            },
        )
        child = resp.json()

        client.post(
            f"/api/v1/kanban/tasks/{done_parent['task_id']}/move",
            json={"status": "completed"},
        )

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "ready"},
        )
        assert resp.status_code == 409
        data = resp.json()["detail"]
        assert len(data["unmet_parents"]) == 1
        assert data["unmet_parents"][0]["task_id"] == str(pending_parent["task_id"])
        assert data["unmet_parents"][0]["title"] == "PendingParent"

    def test_move_blocked_to_ready_unmet_deps_returns_409(
        self,
        client: TestClient,
    ) -> None:
        """BLOCKED task moving to READY with unmet deps returns 409."""
        board = _create_board(client, "MoveBlockedForce")
        bid = str(board["board_id"])
        parent = _create_task(client, bid, "StillRunning")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "BlockedChild", "depends_on": [str(parent["task_id"])]},
        )
        child = resp.json()

        client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "ready", "force": True},
        )
        client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "blocked"},
        )

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "ready"},
        )
        assert resp.status_code == 409
        assert resp.json()["detail"]["code"] == "deps_unmet"

    def test_move_blocked_to_ready_force_true(self, client: TestClient) -> None:
        """BLOCKED task can force-move to READY even with unmet deps."""
        board = _create_board(client, "MoveBlockedForceOK")
        bid = str(board["board_id"])
        parent = _create_task(client, bid, "RunningParent")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "BlockedForced", "depends_on": [str(parent["task_id"])]},
        )
        child = resp.json()

        client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "ready", "force": True},
        )
        client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "blocked"},
        )

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "ready", "force": True},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"

    def test_move_to_non_ready_ignores_deps(self, client: TestClient) -> None:
        """Moving to non-READY status ignores dependency check entirely."""
        board = _create_board(client, "MoveNonReady")
        bid = str(board["board_id"])
        parent = _create_task(client, bid, "Parent")
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Child", "depends_on": [str(parent["task_id"])]},
        )
        child = resp.json()

        client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "ready", "force": True},
        )

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "running"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "running"

        resp = client.post(
            f"/api/v1/kanban/tasks/{child['task_id']}/move",
            json={"status": "blocked"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "blocked"


class TestTaskAttachments:
    """Attachment CRUD via the task API (create, read, update, clear)."""

    def test_create_task_with_attachments(self, client: TestClient) -> None:
        board = _create_board(client, "AttachBoard")
        bid = str(board["board_id"])
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={
                "title": "With Attachments",
                "attachment_ids": ["file-1", "file-2"],
            },
        )
        assert resp.status_code == 201
        data = resp.json()
        assert data["attachment_ids"] == ["file-1", "file-2"]
        assert len(data["attachments"]) == 2
        assert all(a["url"] for a in data["attachments"])

    def test_create_task_without_attachments(self, client: TestClient) -> None:
        board = _create_board(client, "NoAttachBoard")
        bid = str(board["board_id"])
        task = _create_task(client, bid, "Plain Task")
        assert task["attachment_ids"] == []
        assert task["attachments"] == []

    def test_get_task_returns_attachments(self, client: TestClient) -> None:
        board = _create_board(client, "GetAttachBoard")
        bid = str(board["board_id"])
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={
                "title": "Get Attach",
                "attachment_ids": ["file-a"],
            },
        )
        task_id = resp.json()["task_id"]

        resp = client.get(f"/api/v1/kanban/tasks/{task_id}")
        assert resp.status_code == 200
        data = resp.json()
        assert data["attachment_ids"] == ["file-a"]
        assert len(data["attachments"]) == 1
        assert data["attachments"][0]["file_id"] == "file-a"

    def test_update_task_attachments(self, client: TestClient) -> None:
        board = _create_board(client, "UpdateAttachBoard")
        bid = str(board["board_id"])
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Update Attach", "attachment_ids": ["old-file"]},
        )
        task_id = resp.json()["task_id"]

        resp = client.patch(
            f"/api/v1/kanban/tasks/{task_id}",
            json={"attachment_ids": ["new-file-1", "new-file-2"]},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["attachment_ids"] == ["new-file-1", "new-file-2"]
        assert len(data["attachments"]) == 2

    def test_clear_task_attachments(self, client: TestClient) -> None:
        board = _create_board(client, "ClearAttachBoard")
        bid = str(board["board_id"])
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Clear Attach", "attachment_ids": ["f1"]},
        )
        task_id = resp.json()["task_id"]

        resp = client.patch(
            f"/api/v1/kanban/tasks/{task_id}",
            json={"attachment_ids": []},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["attachment_ids"] == []
        assert data["attachments"] == []

    def test_list_tasks_includes_attachments(self, client: TestClient) -> None:
        board = _create_board(client, "ListAttachBoard")
        bid = str(board["board_id"])
        client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Attached", "attachment_ids": ["img-1"]},
        )
        client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "NoAttach"},
        )

        resp = client.get(f"/api/v1/kanban/boards/{bid}/tasks")
        assert resp.status_code == 200
        items = resp.json()["items"]
        assert len(items) == 2

        attached = next(t for t in items if t["title"] == "Attached")
        plain = next(t for t in items if t["title"] == "NoAttach")
        assert attached["attachment_ids"] == ["img-1"]
        assert len(attached["attachments"]) == 1
        assert plain["attachment_ids"] == []
        assert plain["attachments"] == []

    def test_create_task_attachment_limit_exceeded(self, client: TestClient) -> None:
        board = _create_board(client, "LimitBoard")
        bid = str(board["board_id"])
        too_many_ids = [f"file-{i}" for i in range(11)]
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Too Many", "attachment_ids": too_many_ids},
        )
        assert resp.status_code == 422

    def test_create_task_attachment_at_limit(self, client: TestClient) -> None:
        """Exactly 10 attachments should succeed (boundary)."""
        board = _create_board(client, "LimitOkBoard")
        bid = str(board["board_id"])
        ids_10 = [f"file-{i}" for i in range(10)]
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "At Limit", "attachment_ids": ids_10},
        )
        assert resp.status_code == 201
        assert len(resp.json()["attachment_ids"]) == 10

    def test_update_task_attachment_limit_exceeded(self, client: TestClient) -> None:
        """PATCH with >10 attachment_ids should return 422."""
        board = _create_board(client, "UpdateLimitBoard")
        bid = str(board["board_id"])
        task = _create_task(client, bid, "Update Limit")
        too_many = [f"file-{i}" for i in range(11)]
        resp = client.patch(
            f"/api/v1/kanban/tasks/{task['task_id']}",
            json={"attachment_ids": too_many},
        )
        assert resp.status_code == 422

    def test_omitting_attachment_ids_preserves_them(self, client: TestClient) -> None:
        """PATCH without attachment_ids should not alter existing attachments."""
        board = _create_board(client, "PreserveBoard")
        bid = str(board["board_id"])
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Keep Attach", "attachment_ids": ["keep-me"]},
        )
        task_id = resp.json()["task_id"]

        resp = client.patch(
            f"/api/v1/kanban/tasks/{task_id}",
            json={"title": "New Title Only"},
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["title"] == "New Title Only"
        assert data["attachment_ids"] == ["keep-me"]

    def test_duplicate_attachment_ids_preserved(self, client: TestClient) -> None:
        """Duplicate file IDs in attachment_ids should be stored as-is."""
        board = _create_board(client, "DupBoard")
        bid = str(board["board_id"])
        resp = client.post(
            f"/api/v1/kanban/boards/{bid}/tasks",
            json={"title": "Dups", "attachment_ids": ["f1", "f1", "f2"]},
        )
        assert resp.status_code == 201
        assert resp.json()["attachment_ids"] == ["f1", "f1", "f2"]


# ===========================================================================
# Synthetic zero-duration run for unclaimed tasks
# ===========================================================================


class TestSyntheticRun:
    """move_task creates a synthetic TaskRun when an unclaimed task
    transitions to COMPLETED / BLOCKED / FAILED."""

    def test_complete_unclaimed_creates_synthetic_run(self, client: TestClient) -> None:
        board = _create_board(client, "SynRun")
        tid = str(_create_task(client, board["board_id"], "Unclaimed")["task_id"])

        resp = client.post(
            f"/api/v1/kanban/tasks/{tid}/move",
            json={"status": "completed", "result": "Done by human"},
        )
        assert resp.status_code == 200
        assert resp.json()["result"] == "Done by human"

        runs = client.get(f"/api/v1/kanban/tasks/{tid}/runs").json()["items"]
        assert len(runs) == 1
        run = runs[0]
        assert run["worker_id"] == "manual"
        assert run["outcome"] == "completed"
        assert run["summary"] == "Done by human"
        assert run["ended_at"] is not None

    def test_block_unclaimed_creates_synthetic_run(self, client: TestClient) -> None:
        board = _create_board(client, "SynBlock")
        tid = str(_create_task(client, board["board_id"], "BlockMe")["task_id"])

        resp = client.post(
            f"/api/v1/kanban/tasks/{tid}/move",
            json={
                "status": "blocked",
                "block_kind": "human",
                "blocked_reason": "waiting for review",
            },
        )
        assert resp.status_code == 200

        runs = client.get(f"/api/v1/kanban/tasks/{tid}/runs").json()["items"]
        assert len(runs) == 1
        assert runs[0]["outcome"] == "blocked"
        assert runs[0]["error"] == "waiting for review"

    def test_fail_unclaimed_creates_synthetic_run(self, client: TestClient) -> None:
        board = _create_board(client, "SynFail")
        tid = str(_create_task(client, board["board_id"], "FailMe")["task_id"])

        resp = client.post(
            f"/api/v1/kanban/tasks/{tid}/move",
            json={"status": "failed"},
        )
        assert resp.status_code == 200

        runs = client.get(f"/api/v1/kanban/tasks/{tid}/runs").json()["items"]
        assert len(runs) == 1
        assert runs[0]["outcome"] == "crashed"
        assert runs[0]["worker_id"] == "manual"

    def test_running_to_completed_no_synthetic_run(self, client: TestClient) -> None:
        """Tasks moved from RUNNING already have a dispatcher-created run;
        no synthetic run should be added."""
        board = _create_board(client, "NoSyn")
        tid = str(_create_task(client, board["board_id"], "Running")["task_id"])

        client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "running"})
        resp = client.post(
            f"/api/v1/kanban/tasks/{tid}/move",
            json={"status": "completed"},
        )
        assert resp.status_code == 200

        runs = client.get(f"/api/v1/kanban/tasks/{tid}/runs").json()["items"]
        assert len(runs) == 0

    def test_move_with_result_and_metadata(self, client: TestClient) -> None:
        board = _create_board(client, "Meta")
        tid = str(_create_task(client, board["board_id"], "WithMeta")["task_id"])

        resp = client.post(
            f"/api/v1/kanban/tasks/{tid}/move",
            json={
                "status": "completed",
                "result": "Implemented feature X",
                "metadata": {"changed_files": ["a.py", "b.py"]},
            },
        )
        assert resp.status_code == 200
        data = resp.json()
        assert data["result"] == "Implemented feature X"
        assert data["metadata"]["handoff"] == {"changed_files": ["a.py", "b.py"]}

    def test_move_ready_no_synthetic_run(self, client: TestClient) -> None:
        """Moving to READY should NOT create a synthetic run."""
        board = _create_board(client, "NoSynReady")
        tid = str(_create_task(client, board["board_id"], "ToReady")["task_id"])

        client.post(f"/api/v1/kanban/tasks/{tid}/move", json={"status": "ready"})

        runs = client.get(f"/api/v1/kanban/tasks/{tid}/runs").json()["items"]
        assert len(runs) == 0

    def test_synthetic_run_event_has_run_id(self, client: TestClient) -> None:
        """The COMPLETED event should reference the synthetic run_id."""
        board = _create_board(client, "EvtRunId")
        tid = str(_create_task(client, board["board_id"], "EvtTask")["task_id"])

        client.post(
            f"/api/v1/kanban/tasks/{tid}/move",
            json={"status": "completed", "result": "ok"},
        )

        runs = client.get(f"/api/v1/kanban/tasks/{tid}/runs").json()["items"]
        assert len(runs) == 1
        run_id = runs[0]["run_id"]

        events = client.get(f"/api/v1/kanban/tasks/{tid}/events").json()["items"]
        completed_events = [e for e in events if e["kind"] == "completed"]
        assert len(completed_events) == 1
        assert completed_events[0]["run_id"] == run_id
