"""Tests for BtwTaskNotifier and _emit_btw_done."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

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

    def test_publishes_on_task_failed(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(result="", error="timeout")

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_failed", task)

        event = queue.get_nowait()
        assert event.data["status"] == "failed"
        assert event.data["result"] == "timeout"

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

    def test_result_falls_back_to_error(self) -> None:
        from app.services.kanban.service import _emit_btw_done

        bus = _make_event_bus()
        queue = bus.subscribe()
        task = _btw_task(result=None, error="crash")

        with patch("app.services.kanban.event_publisher.get_event_bus", return_value=bus):
            _emit_btw_done("task_completed", task)

        event = queue.get_nowait()
        assert event.data["result"] == "crash"

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


def _deliver_data(**overrides: object) -> dict[str, object]:
    data: dict[str, object] = {
        "channel": "discord",
        "chat_id": "ch1",
        "status": "completed",
        "title": "test task",
        "result": "done",
        "thread_id": "th1",
        "user_id": "uid1",
        "locale": "en",
    }
    data.update(overrides)
    return data


def _gateway_with_send_now(**send_now_kwargs: object) -> MagicMock:
    gateway = MagicMock()
    gateway.bus.send_now = AsyncMock(**send_now_kwargs)
    return gateway


class TestBtwTaskNotifier:
    """Unit tests for BtwTaskNotifier lifecycle and delivery."""

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self) -> None:
        from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

        bus = _make_event_bus()
        notifier = BtwTaskNotifier(bus)

        await notifier.start()
        assert notifier._task is not None
        assert notifier._queue is not None

        await notifier.stop()
        assert notifier._task is None
        assert notifier._queue is None

    @pytest.mark.asyncio
    async def test_deliver_sends_to_channel(self) -> None:
        from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

        notifier = BtwTaskNotifier(_make_event_bus())
        mock_gateway = _gateway_with_send_now(return_value="mid-1")

        with (
            patch("app.core.channel_bridge.btw_notifier.channel_t", return_value="Test notification"),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(_deliver_data())

        mock_gateway.bus.send_now.assert_awaited_once()
        sent_msg = mock_gateway.bus.send_now.call_args[0][0]
        assert sent_msg.channel == "discord"
        assert sent_msg.recipient_id == "ch1"
        assert sent_msg.user_id == "uid1"
        assert sent_msg.content == "Test notification"

    @pytest.mark.asyncio
    async def test_deliver_adds_mobile_status_button_when_task_id_present(self) -> None:
        from app.channels.types.components import ActionButton, ButtonStyle
        from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

        notifier = BtwTaskNotifier(_make_event_bus())
        mock_gateway = _gateway_with_send_now(return_value="mid-1")
        mobile_components = (
            (
                ActionButton(
                    label="Open mobile status",
                    action_id="mobile:open_status",
                    style=ButtonStyle.PRIMARY,
                    url="https://tunnel.example.com/mobile/status/ch1?pair=token",
                ),
            ),
        )

        mock_chat = MagicMock()
        mock_chat.id = "chat-uuid-1"

        with (
            patch("app.core.channel_bridge.btw_notifier.channel_t", return_value="Test notification"),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
            patch(
                "app.services.chat.chat_service.ChatService.get_channel_chat_by_key",
                new_callable=AsyncMock,
                return_value=mock_chat,
            ),
            patch(
                "app.remote_access.mobile_deep_link.resolve_web_handoff_components",
                AsyncMock(return_value=mobile_components),
            ),
        ):
            await notifier._deliver(_deliver_data(task_id="task-42"))

        mock_gateway.bus.send_now.assert_awaited_once()
        sent_msg = mock_gateway.bus.send_now.call_args[0][0]
        assert sent_msg.components == mobile_components

    @pytest.mark.asyncio
    async def test_deliver_swallows_undeliverable_channel(self) -> None:
        from app.channels.core.exceptions import ChannelSendError
        from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

        notifier = BtwTaskNotifier(_make_event_bus())
        mock_gateway = _gateway_with_send_now(side_effect=ChannelSendError("No channel registered for 'nonexistent'"))

        with (
            patch("app.core.channel_bridge.btw_notifier.channel_t", return_value="msg"),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(_deliver_data(channel="nonexistent", thread_id="", user_id=""))

        mock_gateway.bus.send_now.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deliver_skips_empty_channel(self) -> None:
        from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

        bus = _make_event_bus()
        notifier = BtwTaskNotifier(bus)
        await notifier._deliver({"channel": "", "chat_id": "c1"})

    @pytest.mark.asyncio
    async def test_deliver_skips_empty_chat_id(self) -> None:
        from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

        bus = _make_event_bus()
        notifier = BtwTaskNotifier(bus)
        await notifier._deliver({"channel": "discord", "chat_id": ""})

    @pytest.mark.asyncio
    async def test_deliver_handles_send_failure(self) -> None:
        from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

        notifier = BtwTaskNotifier(_make_event_bus())
        mock_gateway = _gateway_with_send_now(side_effect=ConnectionError("network down"))

        with (
            patch("app.core.channel_bridge.btw_notifier.channel_t", return_value="msg"),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(_deliver_data(channel="test", thread_id="", user_id=""))

        mock_gateway.bus.send_now.assert_awaited_once()

    @pytest.mark.asyncio
    async def test_deliver_no_thread_id_metadata_is_none(self) -> None:
        from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

        notifier = BtwTaskNotifier(_make_event_bus())
        mock_gateway = _gateway_with_send_now(return_value="mid-1")

        with (
            patch("app.core.channel_bridge.btw_notifier.channel_t", return_value="msg"),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(_deliver_data(channel="test", thread_id="", user_id="u1"))

        assert mock_gateway.bus.send_now.call_args[0][0].metadata is None

    @pytest.mark.asyncio
    async def test_stop_when_not_started(self) -> None:
        from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

        bus = _make_event_bus()
        notifier = BtwTaskNotifier(bus)
        await notifier.stop()
        assert notifier._task is None
        assert notifier._queue is None

    @pytest.mark.asyncio
    async def test_double_stop(self) -> None:
        from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

        bus = _make_event_bus()
        notifier = BtwTaskNotifier(bus)
        await notifier.start()
        await notifier.stop()
        await notifier.stop()
        assert notifier._task is None

    @pytest.mark.asyncio
    async def test_user_id_fallback(self) -> None:
        from app.core.channel_bridge.btw_notifier import BtwTaskNotifier

        notifier = BtwTaskNotifier(_make_event_bus())
        mock_gateway = _gateway_with_send_now(return_value="mid-1")

        with (
            patch("app.core.channel_bridge.btw_notifier.channel_t", return_value="msg"),
            patch("app.core.channel_bridge.channel_gateway", mock_gateway),
        ):
            await notifier._deliver(_deliver_data(channel="test", thread_id="", user_id=""))

        assert mock_gateway.bus.send_now.call_args[0][0].user_id == "local-user"


class TestFormatNotification:
    """Unit tests for _format_notification."""

    def test_completed_format(self) -> None:
        with patch("app.core.channel_bridge.btw_notifier.channel_t", return_value="  ok  "):
            from app.core.channel_bridge.btw_notifier import _format_notification

            result = _format_notification("completed", "my task", "result text", "en")
            assert result == "ok"

    def test_failed_format(self) -> None:
        with patch("app.core.channel_bridge.btw_notifier.channel_t") as mock_t:
            mock_t.return_value = "failed msg"
            from app.core.channel_bridge.btw_notifier import _format_notification

            _format_notification("failed", "my task", "error", "zh-CN")
            mock_t.assert_called_with("zh-CN", "background_failed", title="my task", result="error")

    def test_blocked_format(self) -> None:
        with patch("app.core.channel_bridge.btw_notifier.channel_t") as mock_t:
            mock_t.return_value = "blocked msg"
            from app.core.channel_bridge.btw_notifier import _format_notification

            _format_notification("blocked", "my task", "needs review", "en")
            mock_t.assert_called_with("en", "background_blocked", title="my task", result="needs review")

    def test_title_truncation(self) -> None:
        with patch("app.core.channel_bridge.btw_notifier.channel_t") as mock_t:
            mock_t.return_value = "msg"
            from app.core.channel_bridge.btw_notifier import _format_notification

            long_title = "x" * 200
            _format_notification("completed", long_title, "", "en")
            call_kwargs = mock_t.call_args[1]
            assert len(call_kwargs["title"]) == 80

    def test_empty_title_fallback(self) -> None:
        with patch("app.core.channel_bridge.btw_notifier.channel_t") as mock_t:
            mock_t.return_value = "msg"
            from app.core.channel_bridge.btw_notifier import _format_notification

            _format_notification("completed", "", "", "en")
            call_kwargs = mock_t.call_args[1]
            assert call_kwargs["title"] == "background task"

    def test_result_truncation(self) -> None:
        with patch("app.core.channel_bridge.btw_notifier.channel_t") as mock_t:
            mock_t.return_value = "msg"
            from app.core.channel_bridge.btw_notifier import _format_notification

            long_result = "r" * 500
            _format_notification("completed", "t", long_result, "en")
            call_kwargs = mock_t.call_args[1]
            assert len(call_kwargs["result"]) == 300

    def test_unknown_status_uses_failed_key(self) -> None:
        with patch("app.core.channel_bridge.btw_notifier.channel_t") as mock_t:
            mock_t.return_value = "msg"
            from app.core.channel_bridge.btw_notifier import _format_notification

            _format_notification("unknown", "t", "", "en")
            assert mock_t.call_args[0][1] == "background_failed"
