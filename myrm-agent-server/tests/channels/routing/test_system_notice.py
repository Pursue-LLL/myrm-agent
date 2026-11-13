"""The notices the router sends on its own (mute, busy, quota) reach the right chat, as the member, in the system lane."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.routing.message_effects import MessageEffects
from app.channels.types import InboundMessage, MessagePriority, OutboundMessage

Sender = Callable[[MessageEffects, InboundMessage], Awaitable[None]]


async def _mute(fx: MessageEffects, msg: InboundMessage) -> None:
    await fx.send_mute_reply(msg)


async def _busy(fx: MessageEffects, msg: InboundMessage) -> None:
    await fx.send_busy_ack(msg, position=1, max_pending=5)


async def _quota(fx: MessageEffects, msg: InboundMessage) -> None:
    await fx.send_quota_exceeded_reply(msg, quota=3)


def _message(*, is_group: bool, chat_id: str) -> InboundMessage:
    return InboundMessage(
        channel="test", sender_id="u1", content="hi", chat_id=chat_id, is_group=is_group, user_id="member-7", thread_id="t-9"
    )


async def _sent(sender: Sender, msg: InboundMessage) -> OutboundMessage:
    bus = MagicMock()
    bus.publish_outbound = AsyncMock()
    await sender(MessageEffects(bus), msg)
    sent: OutboundMessage = bus.publish_outbound.call_args[0][0]
    return sent


@pytest.mark.asyncio
@pytest.mark.parametrize("sender", [_mute, _busy, _quota], ids=["mute", "busy", "quota"])
class TestSystemNotice:
    async def test_a_group_message_is_answered_in_its_chat(self, sender: Sender) -> None:
        assert (await _sent(sender, _message(is_group=True, chat_id="grp-1"))).recipient_id == "grp-1"

    async def test_a_direct_message_is_answered_to_its_sender_even_when_it_carries_a_chat_id(self, sender: Sender) -> None:
        assert (await _sent(sender, _message(is_group=False, chat_id="dm-chat"))).recipient_id == "u1"

    async def test_a_group_message_without_a_chat_id_is_answered_to_its_sender(self, sender: Sender) -> None:
        assert (await _sent(sender, _message(is_group=True, chat_id=""))).recipient_id == "u1"

    async def test_the_notice_belongs_to_the_member_and_keeps_the_thread_in_the_system_lane(self, sender: Sender) -> None:
        sent = await _sent(sender, _message(is_group=True, chat_id="grp-1"))
        assert (sent.user_id, sent.thread_id, sent.priority) == ("member-7", "t-9", MessagePriority.SYSTEM)
