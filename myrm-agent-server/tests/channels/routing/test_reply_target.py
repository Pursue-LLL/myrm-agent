"""A system reply quotes the inbound message id, else the id the channel carried in metadata, else nothing."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.message_effects import MessageEffects
from app.channels.types import InboundMessage, OutboundMessage

Sender = Callable[[MessageEffects, InboundMessage], Awaitable[None]]


def _msg(*, message_id: str | None, metadata: dict[str, object]) -> InboundMessage:
    return InboundMessage(
        channel="test",
        sender_id="u1",
        content="hi",
        chat_id="grp",
        is_group=True,
        message_id=message_id,
        metadata=metadata,
    )


async def _mute(fx: MessageEffects, msg: InboundMessage) -> None:
    await fx.send_mute_reply(msg)


async def _busy(fx: MessageEffects, msg: InboundMessage) -> None:
    await fx.send_busy_ack(msg, position=1, max_pending=5)


async def _quota(fx: MessageEffects, msg: InboundMessage) -> None:
    await fx.send_quota_exceeded_reply(msg, quota=3)


async def _reply_to(sender: Sender, msg: InboundMessage) -> str | None:
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    await sender(MessageEffects(bus), msg)
    sent: OutboundMessage = bus.publish_outbound.call_args[0][0]
    return sent.reply_to_id


@pytest.mark.asyncio
@pytest.mark.parametrize("sender", [_mute, _busy, _quota])
class TestReplyTarget:
    async def test_the_inbound_id_wins_over_the_metadata_id(self, sender: Sender) -> None:
        assert await _reply_to(sender, _msg(message_id="m1", metadata={"message_id": "m2"})) == "m1"

    async def test_the_metadata_id_is_quoted_when_the_inbound_has_none(self, sender: Sender) -> None:
        assert await _reply_to(sender, _msg(message_id=None, metadata={"message_id": "m2"})) == "m2"

    async def test_a_numeric_metadata_id_is_quoted_as_text(self, sender: Sender) -> None:
        assert await _reply_to(sender, _msg(message_id=None, metadata={"message_id": 99})) == "99"

    async def test_nothing_is_quoted_when_no_id_exists(self, sender: Sender) -> None:
        assert await _reply_to(sender, _msg(message_id=None, metadata={})) is None
