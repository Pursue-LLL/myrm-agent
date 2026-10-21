"""Tests for handle_dead_letter suppress_im_notification metadata."""

from __future__ import annotations

from unittest.mock import patch

import pytest

from app.core.channel_bridge import handle_dead_letter
from app.services.agent.outbound_notify.constants import METADATA_KEY_NOTIFY_SOURCE, NOTIFY_SOURCE_AGENT
from app.services.event.app_event_bus import AppEventType


@pytest.mark.asyncio
async def test_handle_dead_letter_sets_suppress_im_for_agent_notify() -> None:
    delivery = type(
        "Delivery",
        (),
        {
            "channel": "telegram",
            "id": "d1",
            "content": {"metadata": {METADATA_KEY_NOTIFY_SOURCE: NOTIFY_SOURCE_AGENT}},
        },
    )()

    published: list[object] = []

    class FakeBus:
        def publish(self, event: object) -> None:
            published.append(event)

    with (
        patch("app.services.event.app_event_bus.get_event_bus", return_value=FakeBus()),
        patch("asyncio.get_running_loop") as mock_loop,
    ):
        mock_loop.return_value.create_task = lambda _coro: None
        await handle_dead_letter(delivery, "send failed")

    assert len(published) == 1
    event = published[0]
    assert event.event_type == AppEventType.MESSAGE_DEAD_LETTERED
    assert event.data["suppress_im_notification"] is True


@pytest.mark.asyncio
async def test_handle_dead_letter_does_not_suppress_im_without_agent_metadata() -> None:
    delivery = type(
        "Delivery",
        (),
        {
            "channel": "telegram",
            "id": "d2",
            "content": {"metadata": {}},
        },
    )()

    published: list[object] = []

    class FakeBus:
        def publish(self, event: object) -> None:
            published.append(event)

    with (
        patch("app.services.event.app_event_bus.get_event_bus", return_value=FakeBus()),
        patch("asyncio.get_running_loop") as mock_loop,
    ):
        mock_loop.return_value.create_task = lambda _coro: None
        await handle_dead_letter(delivery, "send failed")

    assert published[0].data["suppress_im_notification"] is False


@pytest.mark.asyncio
async def test_handle_dead_letter_stores_catalog_keys_and_english_fallback() -> None:
    """The persisted copy carries catalog keys so the notification center localizes it.

    Title/message stay English for consumers without i18n (web push, adaptive cards).
    """
    delivery = type(
        "Delivery",
        (),
        {"channel": "telegram", "id": "d3", "content": {"metadata": {}}},
    )()

    persisted: list[dict[str, object]] = []

    class FakeNotificationService:
        @staticmethod
        async def create_notification(**kwargs: object) -> str:
            persisted.append(kwargs)
            return "n1"

    scheduled: list[object] = []

    class FakeBus:
        def publish(self, event: object) -> None:
            pass

    with (
        patch("app.services.event.app_event_bus.get_event_bus", return_value=FakeBus()),
        patch("asyncio.get_running_loop") as mock_loop,
        patch(
            "app.services.infra.system_notification.SystemNotificationService",
            FakeNotificationService,
        ),
    ):
        mock_loop.return_value.create_task = lambda coro: scheduled.append(coro)
        await handle_dead_letter(delivery, "timeout")

    for coro in scheduled:
        await coro  # type: ignore[misc]

    assert len(persisted) == 1
    meta = persisted[0]["meta_data"]
    assert isinstance(meta, dict)
    assert meta["delivery_id"] == "d3"
    assert meta["i18n_message_key"] == "notifications.messageDeadLettered"
    assert meta["i18n_title_key"] == "chat.messageFailed.title"
    assert meta["i18n_params"] == {"channel": "telegram", "reason": "timeout"}
    assert not any("\u4e00" <= ch <= "\u9fff" for ch in str(persisted[0]["title"]) + str(persisted[0]["message"]))
