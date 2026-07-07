"""Tests for NotificationDispatcher — event template formatting and dispatch logic."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.notifications.dispatcher import (
    NotificationDispatcher,
    NotificationTarget,
    _format_message,
)
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus


class TestFormatMessage:
    """Verify _format_message covers all configured event templates."""

    def test_pairing_pending(self) -> None:
        event = AppEvent(
            event_type=AppEventType.PAIRING_PENDING,
            data={"channel": "telegram", "sender_id": "12345"},
        )
        result = _format_message(event)
        assert result is not None
        assert "[Myrm AI]" in result
        assert "telegram" in result
        assert "12345" in result

    def test_approval_required(self) -> None:
        event = AppEvent(
            event_type=AppEventType.APPROVAL_REQUIRED,
            data={"approval_id": "a1", "action_type": "file_write", "status": "PENDING", "severity": "high"},
        )
        result = _format_message(event)
        assert result is not None
        assert "file_write" in result
        assert "high" in result

    def test_health_alert(self) -> None:
        event = AppEvent(
            event_type=AppEventType.HEALTH_ALERT,
            data={
                "component": "llm_provider",
                "status": "fail",
                "message": "API key invalid",
                "detail": "",
                "fix_suggestion": "",
                "layer": "server",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "llm_provider" in result
        assert "API key invalid" in result

    def test_budget_alert(self) -> None:
        event = AppEvent(
            event_type=AppEventType.BUDGET_ALERT,
            data={
                "subtype": "budget_alert",
                "status": "warning",
                "today_cost": 8.5,
                "daily_limit": 10.0,
                "remaining": 1.5,
                "pct": 85.0,
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "warning" in result
        assert "85.0%" in result

    def test_new_skill_draft(self) -> None:
        event = AppEvent(
            event_type=AppEventType.NEW_SKILL_DRAFT,
            data={"draft_id": "d1", "draft_type": "CAPTURED", "name": "deploy-react"},
        )
        result = _format_message(event)
        assert result is not None
        assert "deploy-react" in result
        assert "CAPTURED" in result

    def test_message_dead_lettered(self) -> None:
        event = AppEvent(
            event_type=AppEventType.MESSAGE_DEAD_LETTERED,
            data={"channel": "telegram", "error_reason": "timeout"},
        )
        result = _format_message(event)
        assert result is not None
        assert "telegram" in result
        assert "timeout" in result

    def test_channel_disconnected(self) -> None:
        event = AppEvent(
            event_type=AppEventType.CHANNEL_DISCONNECTED,
            data={"channel": "wechat", "status": "error"},
        )
        result = _format_message(event)
        assert result is not None
        assert "wechat" in result

    def test_wechat_session_expired(self) -> None:
        event = AppEvent(
            event_type=AppEventType.WECHAT_SESSION_EXPIRED,
            data={},
        )
        result = _format_message(event)
        assert result is not None
        assert "WeChat" in result

    def test_config_health_warning(self) -> None:
        event = AppEvent(
            event_type=AppEventType.CONFIG_HEALTH_WARNING,
            data={"user_id": "u1", "missing_items": ["api_key"], "suggestions": ["Add key"], "checked_at": "2026-04-29"},
        )
        result = _format_message(event)
        assert result is not None
        assert "missing_items" in result or "api_key" in result

    def test_system_notification(self) -> None:
        event = AppEvent(
            event_type=AppEventType.SYSTEM_NOTIFICATION,
            data={"title": "Task Done", "message": "Report finished", "type": "info", "meta_data": {}},
        )
        result = _format_message(event)
        assert result is not None
        assert "Task Done" in result
        assert "Report finished" in result

    def test_goal_terminal_complete(self) -> None:
        event = AppEvent(
            event_type=AppEventType.GOAL_TERMINAL,
            data={
                "goal_id": "g1",
                "session_id": "s1",
                "status": "complete",
                "objective": "Analyze user feedback",
                "files_modified": 3,
                "total_tokens": 12450,
                "total_cost_usd": 0.0832,
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "[Myrm AI] Goal complete: Analyze user feedback" in result
        assert "3 files" in result
        assert "12,450 tokens" in result
        assert "$0.08" in result

    def test_goal_terminal_cancelled(self) -> None:
        event = AppEvent(
            event_type=AppEventType.GOAL_TERMINAL,
            data={
                "goal_id": "g2",
                "session_id": "s2",
                "status": "cancelled",
                "objective": "Deploy service",
                "files_modified": 0,
                "total_tokens": 500,
                "total_cost_usd": 0.0,
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "Goal cancelled" in result
        assert "0 files" in result
        assert "500 tokens" in result
        assert "$0.00" in result

    def test_goal_terminal_budget_limited(self) -> None:
        event = AppEvent(
            event_type=AppEventType.GOAL_TERMINAL,
            data={
                "goal_id": "g3",
                "session_id": "s3",
                "status": "budget_limited",
                "objective": "Large analysis",
                "files_modified": 10,
                "total_tokens": 100000,
                "total_cost_usd": 5.1234,
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "Goal budget_limited" in result
        assert "10 files" in result
        assert "100,000 tokens" in result
        assert "$5.12" in result

    def test_goal_dequeued(self) -> None:
        event = AppEvent(
            event_type=AppEventType.GOAL_DEQUEUED,
            data={
                "goal_id": "g4",
                "session_id": "s4",
                "objective": "Next task in queue",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert "[Myrm AI] Next goal started: Next task in queue" in result

    def test_goal_terminal_missing_field_returns_none(self) -> None:
        event = AppEvent(
            event_type=AppEventType.GOAL_TERMINAL,
            data={
                "goal_id": "g5",
                "session_id": "s5",
                "status": "complete",
                "objective": "Missing stats",
            },
        )
        result = _format_message(event)
        assert result is None

    def test_unregistered_event_returns_none(self) -> None:
        event = AppEvent(
            event_type=AppEventType.IDLE_STATUS,
            data={"session_id": "s1", "status": "running"},
        )
        assert _format_message(event) is None

    def test_missing_template_field_returns_none(self) -> None:
        event = AppEvent(
            event_type=AppEventType.PAIRING_PENDING,
            data={"channel": "telegram"},  # missing sender_id
        )
        assert _format_message(event) is None

    def test_kanban_task_completed_from_dispatcher(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={
                "board_id": "b1",
                "task_id": "t1",
                "action": "task_completed",
                "title": "Write Report",
                "detail": "Report generated at /docs/report.pdf",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert '"Write Report" completed' in result
        assert "Report generated" in result

    def test_kanban_task_blocked_from_dispatcher(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={
                "board_id": "b1",
                "task_id": "t1",
                "action": "task_blocked",
                "title": "Deploy Service",
                "detail": "Auto-blocked after 3 failures",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert '"Deploy Service" blocked' in result
        assert "Auto-blocked" in result

    def test_kanban_task_failed_from_dispatcher(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "task_failed", "title": "Code Review"},
        )
        result = _format_message(event)
        assert result is not None
        assert '"Code Review" failed' in result

    def test_kanban_moved_to_completed(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={
                "board_id": "b1",
                "task_id": "t1",
                "action": "moved",
                "title": "Analysis",
                "status": "completed",
                "detail": "Done",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert '"Analysis" completed' in result

    def test_kanban_moved_to_ready_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "moved", "title": "Task", "status": "ready"},
        )
        assert _format_message(event) is None

    def test_kanban_created_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "created", "title": "New"},
        )
        assert _format_message(event) is None

    def test_kanban_deleted_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "deleted"},
        )
        assert _format_message(event) is None

    def test_kanban_detail_truncated(self) -> None:
        long_detail = "x" * 300
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "task_completed", "title": "LongTask", "detail": long_detail},
        )
        result = _format_message(event)
        assert result is not None
        assert len(result) < 250

    def test_kanban_moved_to_blocked(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={
                "board_id": "b1",
                "task_id": "t1",
                "action": "moved",
                "title": "BlockedTask",
                "status": "blocked",
                "detail": "Resource unavailable",
            },
        )
        result = _format_message(event)
        assert result is not None
        assert '"BlockedTask" blocked' in result
        assert "Resource unavailable" in result

    def test_kanban_moved_to_failed(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "moved", "title": "FailedTask", "status": "failed"},
        )
        result = _format_message(event)
        assert result is not None
        assert '"FailedTask" failed' in result

    def test_kanban_updated_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "updated", "title": "T"},
        )
        assert _format_message(event) is None

    def test_kanban_promoted_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "promoted"},
        )
        assert _format_message(event) is None

    def test_kanban_dependency_added_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "dependency_added"},
        )
        assert _format_message(event) is None

    def test_kanban_dependency_removed_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "dependency_removed"},
        )
        assert _format_message(event) is None

    def test_kanban_commented_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "commented"},
        )
        assert _format_message(event) is None

    def test_kanban_no_title_uses_task_id(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "abc123", "action": "task_completed"},
        )
        result = _format_message(event)
        assert result is not None
        assert '"abc123" completed' in result

    def test_kanban_empty_data_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={},
        )
        assert _format_message(event) is None

    def test_kanban_no_detail_no_suffix(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "task_completed", "title": "Clean", "detail": ""},
        )
        result = _format_message(event)
        assert result is not None
        assert result.endswith("completed")
        assert "\n" not in result

    def test_kanban_moved_to_running_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "moved", "title": "T", "status": "running"},
        )
        assert _format_message(event) is None

    def test_kanban_moved_to_backlog_skipped(self) -> None:
        event = AppEvent(
            event_type=AppEventType.KANBAN_TASK_UPDATED,
            data={"board_id": "b1", "task_id": "t1", "action": "moved", "title": "T", "status": "backlog"},
        )
        assert _format_message(event) is None


class TestNotificationDispatcher:
    """Verify dispatcher lifecycle and dispatch behavior."""

    @pytest.mark.asyncio
    async def test_start_stop_lifecycle(self) -> None:
        bus = ServerEventBus()
        dispatcher = NotificationDispatcher(bus)

        await dispatcher.start()
        assert dispatcher._task is not None
        assert dispatcher._queue is not None
        assert len(bus._subscribers) == 1

        await dispatcher.stop()
        assert dispatcher._task is None
        assert dispatcher._queue is None
        assert len(bus._subscribers) == 0

    @pytest.mark.asyncio
    async def test_dispatch_skips_agent_notify_dead_letter_im_fanout(self) -> None:
        bus = ServerEventBus()
        dispatcher = NotificationDispatcher(bus)

        mock_targets = [NotificationTarget(channel="telegram", target="123")]

        with (
            patch(
                "app.core.notifications.dispatcher._load_notification_targets",
                new_callable=AsyncMock,
                return_value=mock_targets,
            ),
            patch(
                "app.core.notifications.dispatcher._publish",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.MESSAGE_DEAD_LETTERED,
                    data={
                        "channel": "telegram",
                        "error_reason": "timeout",
                        "suppress_im_notification": True,
                    },
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_sends_to_targets(self) -> None:
        bus = ServerEventBus()
        dispatcher = NotificationDispatcher(bus)

        mock_targets = [NotificationTarget(channel="telegram", target="123")]

        with (
            patch(
                "app.core.notifications.dispatcher._load_notification_targets",
                new_callable=AsyncMock,
                return_value=mock_targets,
            ),
            patch(
                "app.core.notifications.dispatcher._publish",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.HEALTH_ALERT,
                    data={
                        "component": "test",
                        "status": "fail",
                        "message": "down",
                        "detail": "",
                        "fix_suggestion": "",
                        "layer": "server",
                    },
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_publish.assert_called_once()
        call_args = mock_publish.call_args
        assert call_args[0][0] == mock_targets[0]
        assert "[Myrm AI]" in call_args[0][1]

    @pytest.mark.asyncio
    async def test_dispatch_skips_no_targets(self) -> None:
        bus = ServerEventBus()
        dispatcher = NotificationDispatcher(bus)

        with (
            patch(
                "app.core.notifications.dispatcher._load_notification_targets",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "app.core.notifications.dispatcher._publish",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.HEALTH_ALERT,
                    data={
                        "component": "test",
                        "status": "fail",
                        "message": "down",
                        "detail": "",
                        "fix_suggestion": "",
                        "layer": "server",
                    },
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_skips_unregistered_event(self) -> None:
        bus = ServerEventBus()
        dispatcher = NotificationDispatcher(bus)

        mock_targets = [NotificationTarget(channel="telegram", target="123")]

        with (
            patch(
                "app.core.notifications.dispatcher._load_notification_targets",
                new_callable=AsyncMock,
                return_value=mock_targets,
            ),
            patch(
                "app.core.notifications.dispatcher._publish",
                new_callable=AsyncMock,
            ) as mock_publish,
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

        mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_dispatch_handles_exception_gracefully(self) -> None:
        bus = ServerEventBus()
        dispatcher = NotificationDispatcher(bus)

        with (
            patch(
                "app.core.notifications.dispatcher._load_notification_targets",
                new_callable=AsyncMock,
                side_effect=RuntimeError("DB down"),
            ),
            patch(
                "app.core.notifications.dispatcher._publish",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.HEALTH_ALERT,
                    data={
                        "component": "test",
                        "status": "fail",
                        "message": "err",
                        "detail": "",
                        "fix_suggestion": "",
                        "layer": "server",
                    },
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_publish.assert_not_called()

    @pytest.mark.asyncio
    async def test_stop_handles_unsubscribe_error(self) -> None:
        bus = ServerEventBus()
        dispatcher = NotificationDispatcher(bus)
        await dispatcher.start()

        with patch.object(bus, "unsubscribe", side_effect=ValueError("already removed")):
            await dispatcher.stop()

        assert dispatcher._queue is None
        assert dispatcher._task is None

    @pytest.mark.asyncio
    async def test_dispatch_kanban_terminal_event_to_targets(self) -> None:
        bus = ServerEventBus()
        dispatcher = NotificationDispatcher(bus)

        mock_targets = [NotificationTarget(channel="telegram", target="123")]

        with (
            patch(
                "app.core.notifications.dispatcher._load_notification_targets",
                new_callable=AsyncMock,
                return_value=mock_targets,
            ),
            patch(
                "app.core.notifications.dispatcher._publish",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.KANBAN_TASK_UPDATED,
                    data={"board_id": "b1", "task_id": "t1", "action": "task_completed", "title": "My Task"},
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_publish.assert_called_once()
        text = mock_publish.call_args[0][1]
        assert '"My Task" completed' in text

    @pytest.mark.asyncio
    async def test_dispatch_kanban_lifecycle_event_skipped(self) -> None:
        bus = ServerEventBus()
        dispatcher = NotificationDispatcher(bus)

        mock_targets = [NotificationTarget(channel="telegram", target="123")]

        with (
            patch(
                "app.core.notifications.dispatcher._load_notification_targets",
                new_callable=AsyncMock,
                return_value=mock_targets,
            ),
            patch(
                "app.core.notifications.dispatcher._publish",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.KANBAN_TASK_UPDATED,
                    data={"board_id": "b1", "task_id": "t1", "action": "created", "title": "New Task"},
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        mock_publish.assert_not_called()


class TestLoadNotificationTargets:
    """Verify _load_notification_targets parsing logic."""

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_config(self) -> None:
        from app.core.notifications.dispatcher import _load_notification_targets

        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = None
        mock_session.execute.return_value = mock_result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = mock_session
        ctx.__aexit__.return_value = False

        with patch("app.database.connection.get_session", return_value=ctx):
            targets = await _load_notification_targets()
            assert targets == []

    @pytest.mark.asyncio
    async def test_returns_targets_from_config(self) -> None:
        from types import SimpleNamespace
        from unittest.mock import MagicMock

        from app.core.notifications.dispatcher import _load_notification_targets

        row = SimpleNamespace(
            config_value={
                "notificationDeliveries": [
                    {"channel": "telegram", "target": "123"},
                    {"channel": "whatsapp", "target": "456"},
                    "invalid_item",
                    {"channel": "", "target": "789"},
                ]
            }
        )

        mock_session = AsyncMock()
        sync_result = MagicMock()
        sync_result.scalar_one_or_none.return_value = row
        mock_session.execute.return_value = sync_result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = mock_session
        ctx.__aexit__.return_value = False

        with patch("app.database.connection.get_session", return_value=ctx):
            targets = await _load_notification_targets()
            assert len(targets) == 2
            assert targets[0].channel == "telegram"
            assert targets[1].channel == "whatsapp"

    @pytest.mark.asyncio
    async def test_returns_empty_on_exception(self) -> None:
        from app.core.notifications.dispatcher import _load_notification_targets

        with patch("app.database.connection.get_session", side_effect=RuntimeError("DB error")):
            targets = await _load_notification_targets()
            assert targets == []

    @pytest.mark.asyncio
    async def test_returns_empty_when_no_deliveries_key(self) -> None:
        from types import SimpleNamespace

        from app.core.notifications.dispatcher import _load_notification_targets

        row = SimpleNamespace(config_value={"somethingElse": True})

        mock_session = AsyncMock()
        mock_result = AsyncMock()
        mock_result.scalar_one_or_none.return_value = row
        mock_session.execute.return_value = mock_result

        ctx = AsyncMock()
        ctx.__aenter__.return_value = mock_session
        ctx.__aexit__.return_value = False

        with patch("app.database.connection.get_session", return_value=ctx):
            targets = await _load_notification_targets()
            assert targets == []


class TestPublish:
    """Verify _publish sends through ChannelGateway."""

    @pytest.mark.asyncio
    async def test_publish_sends_outbound_message(self) -> None:
        from app.core.notifications.dispatcher import _publish

        target = NotificationTarget(channel="telegram", target="999")

        with patch("app.core.channel_bridge.channel_gateway") as mock_gw:
            mock_gw.publish = AsyncMock()
            await _publish(target, "[Myrm AI] Test")

        mock_gw.publish.assert_called_once()
        msg = mock_gw.publish.call_args[0][0]
        assert msg.channel == "telegram"
        assert msg.recipient_id == "999"
        assert "[Myrm AI]" in msg.content


class TestMultiTargetDispatch:
    """Verify notification is sent to all configured targets."""

    @pytest.mark.asyncio
    async def test_dispatch_sends_to_multiple_targets(self) -> None:
        bus = ServerEventBus()
        dispatcher = NotificationDispatcher(bus)

        targets = [
            NotificationTarget(channel="telegram", target="111"),
            NotificationTarget(channel="whatsapp", target="222"),
            NotificationTarget(channel="slack", target="333"),
        ]

        with (
            patch(
                "app.core.notifications.dispatcher._load_notification_targets",
                new_callable=AsyncMock,
                return_value=targets,
            ),
            patch(
                "app.core.notifications.dispatcher._publish",
                new_callable=AsyncMock,
            ) as mock_publish,
        ):
            await dispatcher.start()

            bus.publish(
                AppEvent(
                    event_type=AppEventType.KANBAN_TASK_UPDATED,
                    data={"board_id": "b1", "task_id": "t1", "action": "task_completed", "title": "Multi-Target"},
                )
            )

            await asyncio.sleep(0.1)
            await dispatcher.stop()

        assert mock_publish.call_count == 3
        channels = {call.args[0].channel for call in mock_publish.call_args_list}
        assert channels == {"telegram", "whatsapp", "slack"}
