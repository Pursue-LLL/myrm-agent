"""Kanban FAILED-task retry REST API tests.

Covers `POST /tasks/{id}/retry` over HTTP against the real SQLite store:
- FAILED -> READY with a fresh retry budget, description kept, RETRYING audit event
- idempotent no-ops: non-FAILED returns 200 unchanged, double-submit applies once
- 404 for unknown tasks
- dispatcher path (emit once) and fallback path (SSE published here)
- FAILED stays terminal for manual moves: retry is the only way back
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.toolkits.kanban.dispatcher import KanbanDispatcher
from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskEvent, TaskEventKind, TaskStatus

from app.api.kanban.router import router as kanban_router
from app.services.kanban import KanbanService


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


class _NoopRunner:
    async def run(self, task: KanbanTask) -> tuple[bool, str]:
        return (True, "")


def _create_board(client: TestClient) -> str:
    resp = client.post("/api/v1/kanban/boards", json={"name": "Retry Board"})
    assert resp.status_code == 201
    return str(resp.json()["board_id"])


def _create_failed_task(client: TestClient, board_id: str, *, description: str = "original") -> str:
    resp = client.post(
        f"/api/v1/kanban/boards/{board_id}/tasks",
        json={"title": "Flaky task", "description": description},
    )
    assert resp.status_code == 201
    task_id = str(resp.json()["task_id"])
    asyncio.run(_force_failed(task_id))
    return task_id


async def _force_failed(task_id: str) -> None:
    store = KanbanService.get_instance().store
    task = await store.get_task(task_id)
    assert task is not None
    task.status = TaskStatus.FAILED
    task.error = "Model provider returned 500"
    task.retry_count = 3
    task.consecutive_failures = 3
    task.block_cycle_count = 2
    task.completed_at = datetime.now(UTC)
    task.progress_note = "stuck at step 2"
    await store.save_task(task)


async def _retry_events(task_id: str) -> list[TaskEvent]:
    events = await KanbanService.get_instance().store.list_events(task_id)
    return [e for e in events if e.kind == TaskEventKind.RETRYING]


class TestRetryEndpoint:
    def test_failed_task_returns_to_ready_with_fresh_budget(self, client: TestClient) -> None:
        task_id = _create_failed_task(client, _create_board(client))

        resp = client.post(f"/api/v1/kanban/tasks/{task_id}/retry")

        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "ready"
        assert data["error"] == ""
        assert data["retry_count"] == 0
        assert data["consecutive_failures"] == 0
        assert data["completed_at"] is None
        assert data["progress_note"] is None
        assert data["description"] == "original"

    def test_retry_is_persisted_and_audited(self, client: TestClient) -> None:
        task_id = _create_failed_task(client, _create_board(client))

        client.post(f"/api/v1/kanban/tasks/{task_id}/retry")

        persisted = client.get(f"/api/v1/kanban/tasks/{task_id}").json()
        assert persisted["status"] == "ready"
        events = asyncio.run(_retry_events(task_id))
        assert len(events) == 1
        assert events[0].payload == {"from": "failed", "to": "ready", "source": "human"}

    def test_unknown_task_returns_404(self, client: TestClient) -> None:
        assert client.post("/api/v1/kanban/tasks/nope/retry").status_code == 404

    @pytest.mark.parametrize("status", ["ready", "backlog"])
    def test_non_failed_task_is_returned_unchanged(self, client: TestClient, status: str) -> None:
        board_id = _create_board(client)
        resp = client.post(
            f"/api/v1/kanban/boards/{board_id}/tasks",
            json={"title": "Fresh", "initial_status": status},
        )
        task_id = str(resp.json()["task_id"])

        retried = client.post(f"/api/v1/kanban/tasks/{task_id}/retry")

        assert retried.status_code == 200
        assert retried.json()["status"] == status
        assert asyncio.run(_retry_events(task_id)) == []

    def test_double_submit_applies_once(self, client: TestClient) -> None:
        task_id = _create_failed_task(client, _create_board(client))

        first = client.post(f"/api/v1/kanban/tasks/{task_id}/retry")
        second = client.post(f"/api/v1/kanban/tasks/{task_id}/retry")

        assert first.status_code == second.status_code == 200
        assert second.json()["status"] == "ready"
        assert len(asyncio.run(_retry_events(task_id))) == 1

    def test_concurrent_double_submit_applies_once(self, client: TestClient) -> None:
        task_id = _create_failed_task(client, _create_board(client))

        async def _race() -> list[KanbanTask | None]:
            svc = KanbanService.get_instance()
            return list(await asyncio.gather(svc.retry_task(task_id), svc.retry_task(task_id)))

        results = asyncio.run(_race())

        assert all(t is not None and t.status == TaskStatus.READY for t in results)
        assert len(asyncio.run(_retry_events(task_id))) == 1


class TestRetryDelivery:
    def test_fallback_path_publishes_sse_only_when_applied(self, client: TestClient) -> None:
        task_id = _create_failed_task(client, _create_board(client))

        with patch("app.services.kanban.retry_ops.publish_kanban_event") as publish:
            client.post(f"/api/v1/kanban/tasks/{task_id}/retry")
            client.post(f"/api/v1/kanban/tasks/{task_id}/retry")

        publish.assert_called_once()
        assert publish.call_args.args[2] == "task_retrying"
        assert publish.call_args.kwargs["status"] == "ready"

    def test_dispatcher_path_emits_once(self, client: TestClient) -> None:
        board_id = _create_board(client)
        task_id = _create_failed_task(client, board_id)
        svc = KanbanService.get_instance()
        board = asyncio.run(svc.store.get_board(board_id))
        assert board is not None
        dispatcher = KanbanDispatcher(svc.store, _NoopRunner(), board)
        emitted: list[tuple[str, str]] = []
        dispatcher.on_event(lambda event_type, task: emitted.append((event_type, task.task_id)))
        svc._dispatchers[board_id] = dispatcher

        with patch("app.services.kanban.retry_ops.publish_kanban_event") as publish:
            client.post(f"/api/v1/kanban/tasks/{task_id}/retry")
            client.post(f"/api/v1/kanban/tasks/{task_id}/retry")

        assert emitted == [("task_retrying", task_id)]
        publish.assert_not_called()  # the dispatcher's own event hook publishes SSE


class TestFailedStaysTerminalForMoves:
    def test_manual_move_failed_to_ready_is_rejected(self, client: TestClient) -> None:
        """Retry is the only way back; the move guard must keep rejecting this transition."""
        task_id = _create_failed_task(client, _create_board(client))

        resp = client.post(f"/api/v1/kanban/tasks/{task_id}/move", json={"status": "ready"})

        assert resp.status_code == 409
        assert client.get(f"/api/v1/kanban/tasks/{task_id}").json()["status"] == "failed"
