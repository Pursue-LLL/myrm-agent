"""Tests for NotificationDispatcher delivery to each configured target: fan-out and per-channel cards."""

from __future__ import annotations

import asyncio
from collections.abc import Callable
from unittest.mock import AsyncMock, patch

import pytest

from app.core.notifications.dispatcher import NotificationDispatcher, NotificationTarget
from app.services.event.app_event_bus import AppEvent, AppEventType, ServerEventBus


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


async def _until(predicate: Callable[[], bool], timeout: float = 5.0) -> None:
    async with asyncio.timeout(timeout):
        while not predicate():
            await asyncio.sleep(0.01)


class TestApprovalCardDispatch:
    """An approval request is formatted for each target channel, in the owner's language."""

    @staticmethod
    def _draft_event() -> AppEvent:
        return AppEvent(
            event_type=AppEventType.APPROVAL_REQUIRED,
            data={
                "approval_id": "appr_1",
                "action_type": "outbound_draft",
                "severity": "info",
                "payload": {"draft_content": "Refund approved.", "original_content": "Where is my refund?"},
            },
        )

    @staticmethod
    async def _dispatch(
        event: AppEvent, targets: list[NotificationTarget], *, locale: str, publishes: int
    ) -> tuple[AsyncMock, AsyncMock]:
        bus = ServerEventBus()
        dispatcher = NotificationDispatcher(bus)
        with (
            patch(
                "app.core.notifications.dispatcher._load_notification_targets",
                new_callable=AsyncMock,
                return_value=targets,
            ),
            patch("app.core.notifications.dispatcher._publish", new_callable=AsyncMock) as mock_publish,
            patch(
                "app.core.channel_bridge.locale_provider.resolve_user_locale",
                new_callable=AsyncMock,
                return_value=locale,
            ) as mock_locale,
        ):
            await dispatcher.start()
            bus.publish(event)
            await _until(lambda: mock_publish.await_count >= publishes)
            await dispatcher.stop()
        return mock_publish, mock_locale

    @pytest.mark.asyncio
    async def test_only_channels_that_can_resolve_a_click_get_buttons(self) -> None:
        targets = [
            NotificationTarget(channel="telegram", target="111"),
            NotificationTarget(channel="slack", target="333"),
        ]

        publish, locale = await self._dispatch(self._draft_event(), targets, locale="en", publishes=2)

        by_channel = {call.args[0].channel: call for call in publish.call_args_list}
        assert [b.action_id for b in by_channel["telegram"].kwargs["components"][0]] == [
            "approval:approve:appr_1",
            "approval:deny:appr_1",
        ]
        assert by_channel["slack"].kwargs["components"] == ()
        assert by_channel["slack"].args[1].endswith("Open the Myrm AI app to review and decide.")
        assert locale.await_count == 1, "the owner's language is looked up once per event, not once per target"

    @pytest.mark.asyncio
    async def test_the_card_is_written_in_the_owners_language(self) -> None:
        publish, _ = await self._dispatch(
            self._draft_event(), [NotificationTarget(channel="telegram", target="111")], locale="zh-CN", publishes=1
        )

        assert "有一条回复等待你审核" in publish.call_args.args[1]

    @pytest.mark.asyncio
    async def test_events_without_a_localized_card_skip_the_language_lookup(self) -> None:
        event = AppEvent(
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

        publish, locale = await self._dispatch(
            event, [NotificationTarget(channel="telegram", target="111")], locale="zh-CN", publishes=1
        )

        assert "[Myrm AI]" in publish.call_args.args[1]
        locale.assert_not_awaited()
