"""Tests for NotificationDispatcher — dispatch logic, target loading and publishing."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from app.core.notifications.dispatcher import (
    NotificationDispatcher,
    NotificationTarget,
)
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus


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
