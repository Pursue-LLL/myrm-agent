"""Integration-style tests for Telegram notification kwargs on send paths."""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest

from app.channels.providers.telegram import TelegramChannel
from app.channels.providers.telegram.helpers import send_media_attachment
from app.channels.types import (
    MediaAttachment,
    MediaType,
    MessagePriority,
    OutboundMessage,
)
from app.channels.types.notification import (
    ChannelNotificationMode,
    with_final_notify,
)


def _channel(*, mode: ChannelNotificationMode = ChannelNotificationMode.IMPORTANT) -> TelegramChannel:
    ch = TelegramChannel(bot_token="000000000:AAAAAAAAAA_test_token_for_unit_test")
    ch._notifications_mode = mode
    return ch


@pytest.mark.asyncio
async def test_send_message_uses_silent_kwargs_in_important_mode() -> None:
    ch = _channel()
    ch._client.send_message = AsyncMock(return_value={"message_id": 1})

    await ch.send(
        OutboundMessage(
            channel="telegram",
            recipient_id="42",
            content="hello",
            user_id="u1",
        )
    )

    ch._client.send_message.assert_awaited_once()
    assert ch._client.send_message.await_args.kwargs.get("disable_notification") is True


@pytest.mark.asyncio
async def test_send_message_rings_after_with_final_notify() -> None:
    ch = _channel()
    ch._client.send_message = AsyncMock(return_value={"message_id": 1})

    msg = with_final_notify(
        OutboundMessage(
            channel="telegram",
            recipient_id="42",
            content="final",
            user_id="u1",
        )
    )
    await ch.send(msg)

    assert "disable_notification" not in ch._client.send_message.await_args.kwargs


@pytest.mark.asyncio
async def test_send_media_attachment_passes_disable_notification() -> None:
    client = AsyncMock()
    client.send_photo = AsyncMock(return_value={"message_id": 2})
    attachment = MediaAttachment(media_type=MediaType.IMAGE, path=__file__)

    with patch(
        "app.channels.providers.telegram.helpers.Path.read_bytes",
        return_value=b"fake-image",
    ):
        await send_media_attachment(
            client,
            "42",
            attachment,
            None,
            notification_kwargs={"disable_notification": True},
        )

    assert client.send_photo.await_args.kwargs.get("disable_notification") is True


@pytest.mark.asyncio
async def test_send_media_on_outbound_uses_notify_policy() -> None:
    ch = _channel()
    ch._client.send_photo = AsyncMock(return_value={"message_id": 3})
    ch._client.send_message = AsyncMock(return_value={"message_id": 4})

    await ch.send(
        OutboundMessage(
            channel="telegram",
            recipient_id="42",
            content="caption text",
            user_id="u1",
            media=(MediaAttachment(media_type=MediaType.IMAGE, path=__file__),),
        )
    )

    assert ch._client.send_photo.await_args.kwargs.get("disable_notification") is True
    assert ch._client.send_message.await_args.kwargs.get("disable_notification") is True


@pytest.mark.asyncio
async def test_system_priority_outbound_rings_in_important_mode() -> None:
    ch = _channel()
    ch._client.send_message = AsyncMock(return_value={"message_id": 5})

    await ch.send(
        OutboundMessage(
            channel="telegram",
            recipient_id="42",
            content="system alert",
            user_id="u1",
            priority=MessagePriority.SYSTEM,
        )
    )

    assert "disable_notification" not in ch._client.send_message.await_args.kwargs
