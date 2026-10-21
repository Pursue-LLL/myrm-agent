"""Tests for _emit_btw_done and emit_source_chat_done."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from app.services.event.app_event_bus import AppEventType, ServerEventBus


def _make_event_bus() -> ServerEventBus:
    return ServerEventBus()


def _btw_task(
    task_id: str = "t1",
    title: str = "analyse report",
    result: str = "done",
    error: str = "",
    metadata: dict | None = None,
) -> MagicMock:
    task = MagicMock()
    task.task_id = task_id
    task.title = title
    task.result = result
    task.error = error
    task.metadata = metadata or {
        "background_source": "btw",
        "channel": "discord",
        "chat_id": "ch123",
        "thread_id": "th456",
        "user_id": "uid789",
        "locale": "zh-CN",
    }
    return task


class TestEmitBtwDone:
    """Unit tests for _emit_btw_done callback."""

    def test_publishes_on_task_completed(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_completed", _btw_task())

        event = queue.get_nowait()
        assert event.event_type == AppEventType.BACKGROUND_TASK_DONE
        assert event.data["status"] == "completed"
        assert event.data["channel"] == "discord"
        assert event.data["chat_id"] == "ch123"
        assert event.data["thread_id"] == "th456"
        assert event.data["user_id"] == "uid789"
        assert event.data["locale"] == "zh-CN"
        assert event.data["title"] == "analyse report"

    def test_publishes_on_task_failed_without_the_exception_text(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(result="", error="timeout")

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_failed", task)

        event = queue.get_nowait()
        assert event.data["status"] == "failed"
        assert event.data["result"] == ""

    def test_ignores_non_terminal_events(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_started", _btw_task())

        assert queue.empty()

    def test_ignores_non_btw_tasks(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(metadata={"background_source": "kanban", "channel": "x", "chat_id": "y"})

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_completed", task)

        assert queue.empty()

    def test_ignores_missing_channel(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(metadata={"background_source": "btw", "chat_id": "y"})

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_completed", task)

        assert queue.empty()

    def test_user_id_default_when_missing(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(
            metadata={
                "background_source": "btw",
                "channel": "telegram",
                "chat_id": "c1",
            }
        )

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_completed", task)

        event = queue.get_nowait()
        assert event.data["user_id"] == ""

    def test_ignores_missing_chat_id(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(metadata={"background_source": "btw", "channel": "slack"})

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_completed", task)

        assert queue.empty()

    def test_handles_none_metadata(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task()
        task.metadata = None

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_completed", task)

        assert queue.empty()

    def test_completed_result_does_not_fall_back_to_an_old_error(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(result=None, error="crash")

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_completed", task)

        event = queue.get_nowait()
        assert event.data["result"] == ""

    def test_result_empty_when_both_none(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(result=None, error=None)

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_completed", task)

        event = queue.get_nowait()
        assert event.data["result"] == ""

    def test_thread_id_defaults_empty(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(
            metadata={
                "background_source": "btw",
                "channel": "slack",
                "chat_id": "c1",
            }
        )

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_completed", task)

        event = queue.get_nowait()
        assert event.data["thread_id"] == ""

    def test_locale_defaults_en(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(
            metadata={
                "background_source": "btw",
                "channel": "slack",
                "chat_id": "c1",
            }
        )

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_completed", task)

        event = queue.get_nowait()
        assert event.data["locale"] == "en"


class TestEmitSourceChatDone:
    """Unit tests for emit_source_chat_done callback."""

    def test_publishes_on_task_completed(self) -> None:
        from app.services.kanban.event_publisher import emit_source_chat_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(metadata={"source_chat_id": "chat-abc-1"})

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            emit_source_chat_done("task_completed", task)

        event = queue.get_nowait()
        assert event.event_type == AppEventType.BACKGROUND_TASK_DONE
        assert event.data["chat_id"] == "chat-abc-1"
        assert event.data["source_chat_id"] == "chat-abc-1"
        assert event.data["status"] == "completed"

    def test_ignores_btw_tasks(self) -> None:
        from app.services.kanban.event_publisher import emit_source_chat_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(
            metadata={
                "background_source": "btw",
                "source_chat_id": "chat-abc-1",
                "channel": "discord",
                "chat_id": "ch123",
            }
        )

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            emit_source_chat_done("task_completed", task)

        assert queue.empty()

    def test_ignores_without_source_chat(self) -> None:
        from app.services.kanban.event_publisher import emit_source_chat_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(metadata={})

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            emit_source_chat_done("task_completed", task)

        assert queue.empty()

    def test_publishes_on_task_blocked_human(self) -> None:
        from myrm_agent_harness.toolkits.kanban.types import (
            BlockKind,
            KanbanTask,
            TaskStatus,
        )

        from app.services.kanban.event_publisher import emit_source_chat_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = KanbanTask(
            task_id="t-block-1",
            board_id="b1",
            title="Research OpenClaw",
            status=TaskStatus.BLOCKED,
            block_kind=BlockKind.HUMAN,
            blocked_reason="Auto-blocked after 5 consecutive failures",
            metadata={"source_chat_id": "chat-abc-1"},
        )

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            emit_source_chat_done("task_blocked", task)

        event = queue.get_nowait()
        assert event.event_type == AppEventType.BACKGROUND_TASK_DONE
        assert event.data["status"] == "blocked"
        assert event.data["source_chat_id"] == "chat-abc-1"
        assert "Auto-blocked" in str(event.data["result"])

    def test_ignores_scheduled_task_blocked(self) -> None:
        from myrm_agent_harness.toolkits.kanban.types import (
            BlockKind,
            KanbanTask,
            TaskStatus,
        )

        from app.services.kanban.event_publisher import emit_source_chat_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = KanbanTask(
            task_id="t-block-2",
            board_id="b1",
            title="Transient retry",
            status=TaskStatus.BLOCKED,
            block_kind=BlockKind.SCHEDULED,
            blocked_reason="Transient error detected, auto-retry",
            metadata={"source_chat_id": "chat-abc-1"},
        )

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            emit_source_chat_done("task_blocked", task)

        assert queue.empty()
