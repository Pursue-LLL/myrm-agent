"""Kanban in_review approval-gate REST API tests.

Covers the task-level human approval flow over HTTP:
- require_approval flag on create/update
- approve: IN_REVIEW -> COMPLETED (+ dependent promotion)
- reject: IN_REVIEW -> READY with reason (retry_count reset)
- idempotent no-ops: approve/reject on non-IN_REVIEW return 200 unchanged
- manual move into/out of IN_REVIEW rejected with 409
- pending_review IM notification on IN_REVIEW entry
- rejected IM notification on rejection (dispatcher + fallback paths)
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


async def _force_status(
    tid: str, status: TaskStatus, *, error: str | None = None
) -> None:
    svc = KanbanService.get_instance()
    t = await svc.get_task(tid)
    assert t is not None
    t.status = status
    t.result = "artifact built & verified"
    if error is not None:
        t.error = error
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
        resp = client.patch(
            f"/api/v1/kanban/tasks/{tid}", json={"require_approval": True}
        )
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
        parent = _create_task(
            client, board["board_id"], "Parent", require_approval=True
        )
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

    def test_approve_non_review_task_is_idempotent(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"])
        tid = str(task["task_id"])
        resp = client.post(f"/api/v1/kanban/tasks/{tid}/approve", json={})
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"
        assert resp.json()["error"] == ""


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
        assert data["retry_count"] == 0

    def test_reject_unknown_task_returns_404(self, client: TestClient) -> None:
        resp = client.post(
            "/api/v1/kanban/tasks/nope/reject",
            json={"reason": "why"},
        )
        assert resp.status_code == 404

    def test_reject_non_review_task_is_idempotent(self, client: TestClient) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"])
        tid = str(task["task_id"])
        resp = client.post(
            f"/api/v1/kanban/tasks/{tid}/reject",
            json={"reason": "why"},
        )
        assert resp.status_code == 200
        assert resp.json()["status"] == "ready"


class TestManualMoveGuard:

    def test_move_out_of_in_review_returns_409(self, client: TestClient) -> None:
        """Manual moves cannot bypass the approval gate."""
        board = _create_board(client)
        task = _create_task(client, board["board_id"], require_approval=True)
        tid = str(task["task_id"])
        asyncio.run(_force_status(tid, TaskStatus.IN_REVIEW))

        resp = client.post(
            f"/api/v1/kanban/tasks/{tid}/move",
            json={"status": "completed"},
        )
        assert resp.status_code == 409

        resp = client.post(
            f"/api/v1/kanban/tasks/{tid}/move",
            json={"status": "ready"},
        )
        assert resp.status_code == 409


class TestFallbackNotification:

    def test_approve_without_dispatcher_emits_completion_notification(
        self, client: TestClient
    ) -> None:
        board = _create_board(client)
        task = _create_task(client, board["board_id"], require_approval=True)
        tid = str(task["task_id"])
        asyncio.run(
            _force_status(tid, TaskStatus.IN_REVIEW, error="stale failure reason")
        )

        with (
            patch(
                "app.services.kanban.review_ops.emit_source_chat_done"
            ) as mock_source,
            patch("app.services.kanban.review_ops.emit_btw_done") as mock_btw,
        ):
            resp = client.post(
                f"/api/v1/kanban/tasks/{tid}/approve",
                json={"approver": "alice"},
            )
            assert resp.status_code == 200
            assert resp.json()["error"] == ""

        mock_source.assert_called_once()
        assert mock_source.call_args.args[0] == "task_completed"
        mock_btw.assert_called_once()
        assert mock_btw.call_args.args[0] == "task_completed"


class TestPendingReviewNotification:

    def test_source_chat_task_publishes_pending_review_event(self) -> None:
        """IN_REVIEW entry notifies the source chat via BACKGROUND_TASK_DONE."""
        from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskPriority

        from app.services.event.app_event_bus import AppEventType
        from app.services.kanban.event_publisher import emit_review_requested

        task = KanbanTask(
            task_id="t-review",
            board_id="b1",
            title="Deploy v2.1",
            status=TaskStatus.IN_REVIEW,
            priority=TaskPriority.NORMAL,
            result="build ok",
            metadata={
                "source_chat_id": "chat-9",
                "locale": "en",
                "user_id": "u1",
            },
        )
        published: list[object] = []

        with patch("app.services.kanban.event_publisher.get_event_bus") as mock_bus:
            bus = mock_bus.return_value
            bus.publish = lambda ev: published.append(ev)  # type: ignore[method-assign]
            emit_review_requested(task)

        assert len(published) == 1
        event = published[0]
        assert event.event_type == AppEventType.BACKGROUND_TASK_DONE
        assert event.data["status"] == "pending_review"
        assert event.data["board_id"] == "b1"
        assert event.data["chat_id"] == "chat-9"
        assert event.data["title"] == "Deploy v2.1"
        assert event.data.get("suppress_web_push") is not True

    def test_pending_review_skipped_without_source_chat(self) -> None:
        """No source chat / btw target means no notification is published."""
        from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskPriority

        from app.services.kanban.event_publisher import emit_review_requested

        task = KanbanTask(
            task_id="t-plain",
            board_id="b1",
            title="Plain task",
            status=TaskStatus.IN_REVIEW,
            priority=TaskPriority.NORMAL,
            metadata={},
        )
        published: list[object] = []

        with patch("app.services.kanban.event_publisher.get_event_bus") as mock_bus:
            bus = mock_bus.return_value
            bus.publish = lambda ev: published.append(ev)  # type: ignore[method-assign]
            emit_review_requested(task)

        assert published == []


class TestRejectedNotification:

    def test_source_chat_task_publishes_rejected_event(self) -> None:
        """Rejection notifies the source chat with the reason via BACKGROUND_TASK_DONE."""
        from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskPriority

        from app.services.event.app_event_bus import AppEventType
        from app.services.kanban.event_publisher import emit_task_rejected

        task = KanbanTask(
            task_id="t-reject",
            board_id="b1",
            title="Deploy v2.1",
            status=TaskStatus.READY,
            priority=TaskPriority.NORMAL,
            error="add unit tests",
            metadata={
                "source_chat_id": "chat-9",
                "locale": "en",
                "user_id": "u1",
            },
        )
        published: list[object] = []

        with patch("app.services.kanban.event_publisher.get_event_bus") as mock_bus:
            bus = mock_bus.return_value
            bus.publish = lambda ev: published.append(ev)  # type: ignore[method-assign]
            emit_task_rejected(task)

        assert len(published) == 1
        event = published[0]
        assert event.event_type == AppEventType.BACKGROUND_TASK_DONE
        assert event.data["status"] == "rejected"
        assert event.data["chat_id"] == "chat-9"
        assert event.data["result"] == "add unit tests"
        assert event.data["title"] == "Deploy v2.1"
        assert event.data.get("suppress_web_push") is not True

    def test_rejected_skipped_without_source_chat(self) -> None:
        """No source chat / btw target means no rejection notification."""
        from myrm_agent_harness.toolkits.kanban.types import KanbanTask, TaskPriority

        from app.services.kanban.event_publisher import emit_task_rejected

        task = KanbanTask(
            task_id="t-plain",
            board_id="b1",
            title="Plain task",
            status=TaskStatus.READY,
            priority=TaskPriority.NORMAL,
            error="rework",
            metadata={},
        )
        published: list[object] = []

        with patch("app.services.kanban.event_publisher.get_event_bus") as mock_bus:
            bus = mock_bus.return_value
            bus.publish = lambda ev: published.append(ev)  # type: ignore[method-assign]
            emit_task_rejected(task)

        assert published == []

    def test_reject_without_dispatcher_emits_rejection_notification(
        self, client: TestClient
    ) -> None:
        """The fallback reject path notifies the originating chat."""
        board = _create_board(client)
        task = _create_task(client, board["board_id"], require_approval=True)
        tid = str(task["task_id"])
        asyncio.run(_force_status(tid, TaskStatus.IN_REVIEW))

        with patch(
            "app.services.kanban.review_ops.emit_task_rejected"
        ) as mock_rejected:
            resp = client.post(
                f"/api/v1/kanban/tasks/{tid}/reject",
                json={"reason": "needs citations"},
            )
            assert resp.status_code == 200

        mock_rejected.assert_called_once()
        assert mock_rejected.call_args.args[0].status == TaskStatus.READY
        assert mock_rejected.call_args.args[0].error == "needs citations"
