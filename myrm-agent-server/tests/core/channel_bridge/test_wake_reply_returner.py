"""A wake turn's reply goes back to the conversation its chat lives in, and only when there is one."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.types import InboundMessage
from app.core.channel_bridge.wake_return import ChannelWakeReplyReturner, WakeOrigins

_MSG = InboundMessage(channel="telegram", sender_id="u1", content="research it", chat_id="room-1")


def _returner(origins: WakeOrigins, *, delivered: bool = True) -> tuple[ChannelWakeReplyReturner, AsyncMock]:
    deliver = AsyncMock(return_value=delivered)
    return ChannelWakeReplyReturner(MagicMock(deliver_followup=deliver), origins), deliver


@pytest.mark.asyncio
async def test_the_reply_is_delivered_into_the_conversation_the_chat_was_last_talked_in() -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    returner, deliver = _returner(origins)

    await returner.return_reply("chat-db-1", "The research is done.")

    deliver.assert_awaited_once()
    assert deliver.await_args is not None
    origin, reply = deliver.await_args.args
    assert (origin.channel, origin.chat_id, reply) == ("telegram", "room-1", "The research is done.")


@pytest.mark.asyncio
async def test_a_chat_that_was_not_started_from_a_channel_gets_nothing_sent() -> None:
    returner, deliver = _returner(WakeOrigins())

    await returner.return_reply("chat-db-1", "The research is done.")

    deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_reply_the_router_withheld_is_not_an_error() -> None:
    origins = WakeOrigins()
    origins.remember("chat-db-1", _MSG)
    returner, deliver = _returner(origins, delivered=False)

    await returner.return_reply("chat-db-1", "[SILENT]")

    deliver.assert_awaited_once()
