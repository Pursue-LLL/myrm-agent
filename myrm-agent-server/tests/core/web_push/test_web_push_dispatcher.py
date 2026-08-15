"""Tests for WebPushDispatcher — event template formatting and dispatch logic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.web_push.dispatcher import (
    _PUSH_TEMPLATES,
    WebPushDispatcher,
    _background_task_title,
)
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus


class TestPushTemplates:
    """Verify _PUSH_TEMPLATES covers expected event types."""

    def test_approval_required_template(self) -> None:
        assert AppEventType.APPROVAL_REQUIRED in _PUSH_TEMPLATES

    def test_health_alert_template(self) -> None:
        assert AppEventType.HEALTH_ALERT in _PUSH_TEMPLATES

    def test_budget_alert_template(self) -> None:
        assert AppEventType.BUDGET_ALERT in _PUSH_TEMPLATES

    def test_goal_terminal_template(self) -> None:
        assert AppEventType.GOAL_TERMINAL in _PUSH_TEMPLATES

    def test_background_task_done_status_titles(self) -> None:
        assert _background_task_title("completed") == "Task Completed"
        assert _background_task_title("failed") == "Task Failed"
        assert _background_task_title("blocked") == "Task Blocked"
        assert _background_task_title("pending_review") == "Task Pending Review"
        assert _background_task_title("rejected") == "Task Rejected"
        assert _background_task_title("") == "Task Update"  # fallback

    def test_channel_disconnected_template(self) -> None:
        assert AppEventType.CHANNEL_DISCONNECTED in _PUSH_TEMPLATES

    def test_system_notification_template(self) -> None:
        assert AppEventType.SYSTEM_NOTIFICATION in _PUSH_TEMPLATES

    def test_oauth_reauth_required_template(self) -> None:
        assert AppEventType.OAUTH_REAUTH_REQUIRED in _PUSH_TEMPLATES

    def test_idle_status_not_in_templates(self) -> None:
        assert AppEventType.IDLE_STATUS not in _PUSH_TEMPLATES


class TestWebPushDispatcher:
    """Verify dispatcher lifecycle and event handling."""

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self) -> None:
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)

        await dispatcher.start()
        assert dispatcher._task is not None
        assert dispatcher._queue is not None
        assert len(bus._subscribers) == 1

        await dispatcher.stop()
        assert dispatcher._task is None
        assert dispatcher._queue is None
        assert len(bus._subscribers) == 0

    @pytest.mark.asyncio
    async def test_dispatches_health_alert(self) -> None:
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)

        mock_service = AsyncMock()
        mock_service.broadcast = AsyncMock(return_value=1)

        with patch(
            "app.core.web_push.service.get_web_push_service",
            return_value=mock_service,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.HEALTH_ALERT,
                    data={
                        "component": "llm_provider",
                        "message": "API key invalid",
                    },
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_service.broadcast.assert_called_once()
        kwargs = mock_service.broadcast.call_args
        assert "Health Alert" in kwargs.kwargs["title"]
        assert "API key invalid" in kwargs.kwargs["body"]
        assert kwargs.kwargs["url"] == "/settings/system"

    @pytest.mark.asyncio
    async def test_dispatches_approval_with_chat_url(self) -> None:
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)

        mock_service = AsyncMock()
        mock_service.broadcast = AsyncMock(return_value=1)

        with patch(
            "app.core.web_push.service.get_web_push_service",
            return_value=mock_service,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.APPROVAL_REQUIRED,
                    data={
                        "approval_id": "ap-1",
                        "chat_id": "chat-deep-link",
                        "action_type": "delete_file",
                        "severity": "high",
                    },
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_service.broadcast.assert_called_once()
        kwargs = mock_service.broadcast.call_args.kwargs
        assert kwargs["url"] == "/chat-deep-link?approval=ap-1"

    @pytest.mark.asyncio
    async def test_skips_unregistered_event(self) -> None:
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)

        mock_service = AsyncMock()

        with patch(
            "app.core.web_push.service.get_web_push_service",
            return_value=mock_service,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.IDLE_STATUS,
                    data={"session_id": "s1", "status": "running"},
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_service.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatches_background_task_done_with_status_title(self) -> None:
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)

        mock_service = AsyncMock()
        mock_service.broadcast = AsyncMock(return_value=1)

        with patch(
            "app.core.web_push.service.get_web_push_service",
            return_value=mock_service,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.BACKGROUND_TASK_DONE,
                    data={
                        "task_id": "t-1",
                        "status": "blocked",
                        "title": "Deploy report",
                        "result": "Auto-blocked after 3 failures",
                        "chat_id": "chat-1",
                    },
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_service.broadcast.assert_called_once()
        kwargs = mock_service.broadcast.call_args.kwargs
        assert kwargs["title"] == "Task Blocked"
        assert kwargs["body"] == "Deploy report"
        assert kwargs["url"] == "/chat-1"

    @pytest.mark.asyncio
    async def test_background_task_done_pending_review_pushes(self) -> None:
        """pending_review publishes with its own title."""
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)

        mock_service = AsyncMock()
        mock_service.broadcast = AsyncMock(return_value=1)

        with patch(
            "app.core.web_push.service.get_web_push_service",
            return_value=mock_service,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.BACKGROUND_TASK_DONE,
                    data={
                        "task_id": "t-2",
                        "status": "pending_review",
                        "title": "Weekly report",
                        "result": "draft ready",
                        "chat_id": "chat-2",
                        "board_id": "b-1",
                    },
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_service.broadcast.assert_called_once()
        title = mock_service.broadcast.call_args.kwargs["title"]
        assert title == "Task Pending Review"
        assert (
            mock_service.broadcast.call_args.kwargs["url"]
            == "/settings/kanban?board_id=b-1&status=in_review"
        )

    @pytest.mark.asyncio
    async def test_background_task_done_suppress_flag_skips(self) -> None:
        """suppress_web_push still gates kanban BACKGROUND_TASK_DONE pushes."""
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)

        mock_service = AsyncMock()

        with patch(
            "app.core.web_push.service.get_web_push_service",
            return_value=mock_service,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.BACKGROUND_TASK_DONE,
                    data={
                        "task_id": "t-4",
                        "status": "completed",
                        "title": "Quiet task",
                        "result": "done",
                        "chat_id": "chat-4",
                        "suppress_web_push": True,
                    },
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_service.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_background_task_done_rejected_title(self) -> None:
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)

        mock_service = AsyncMock()
        mock_service.broadcast = AsyncMock(return_value=1)

        with patch(
            "app.core.web_push.service.get_web_push_service",
            return_value=mock_service,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.BACKGROUND_TASK_DONE,
                    data={
                        "task_id": "t-3",
                        "status": "rejected",
                        "title": "Weekly report",
                        "result": "add citations",
                        "chat_id": "chat-3",
                    },
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_service.broadcast.assert_called_once()
        title = mock_service.broadcast.call_args.kwargs["title"]
        assert title == "Task Rejected"

    @pytest.mark.asyncio
    async def test_suppresses_with_flag(self) -> None:
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)

        mock_service = AsyncMock()

        with patch(
            "app.core.web_push.service.get_web_push_service",
            return_value=mock_service,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.HEALTH_ALERT,
                    data={
                        "component": "test",
                        "message": "suppressed",
                        "suppress_web_push": True,
                    },
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_service.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_skips_on_template_format_error(self) -> None:
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)

        mock_service = AsyncMock()

        with patch(
            "app.core.web_push.service.get_web_push_service",
            return_value=mock_service,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.HEALTH_ALERT,
                    data={},  # missing component & message
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_service.broadcast.assert_not_called()

    @pytest.mark.asyncio
    async def test_handles_exception_gracefully(self) -> None:
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)

        mock_service = AsyncMock()
        mock_service.broadcast = AsyncMock(side_effect=RuntimeError("push error"))

        with patch(
            "app.core.web_push.service.get_web_push_service",
            return_value=mock_service,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.HEALTH_ALERT,
                    data={"component": "test", "message": "err"},
                )
            )

            await asyncio.sleep(0.1)
            # Should not crash — dispatcher remains running
            assert dispatcher._task is not None
            await dispatcher.stop()

    @pytest.mark.asyncio
    async def test_stop_handles_unsubscribe_error(self) -> None:
        bus = ServerEventBus()
        dispatcher = WebPushDispatcher(bus)
        await dispatcher.start()

        with patch.object(
            bus, "unsubscribe", side_effect=ValueError("already removed")
        ):
            await dispatcher.stop()

        assert dispatcher._queue is None
        assert dispatcher._task is None
