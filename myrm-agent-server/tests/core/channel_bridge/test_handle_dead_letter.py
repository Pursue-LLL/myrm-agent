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
