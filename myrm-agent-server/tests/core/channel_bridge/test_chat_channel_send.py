"""ChatChannel outbound delivery — Message ORM required fields."""

from __future__ import annotations

import pytest

from app.channels.types import OutboundMessage
from app.channels.types.messages import MessagePriority
from app.core.channel_bridge.providers.chat import ChatChannel
from app.database.connection import get_session
from app.database.models import Chat, Message
from sqlalchemy import select


@pytest.mark.asyncio
async def test_chat_channel_send_persists_message_with_sent_fields() -> None:
    """ChatChannel.send must populate sent_at/sent_timezone (NOT NULL on messages)."""
    recipient_id = "chat-channel-unit-recipient"
    channel = ChatChannel()
    msg = OutboundMessage(
        channel="chat",
        recipient_id=recipient_id,
        content="notify body",
        user_id="local",
        priority=MessagePriority.NORMAL,
    )

    message_id = await channel.send(msg)
    assert message_id is not None

    async with get_session() as session:
        chat = (await session.execute(select(Chat).where(Chat.id == recipient_id))).scalar_one_or_none()
        assert chat is not None
        row = (await session.execute(select(Message).where(Message.id == message_id))).scalar_one()
        assert row.content == "notify body"
        assert row.sent_at is not None
        assert row.sent_timezone == "UTC"
