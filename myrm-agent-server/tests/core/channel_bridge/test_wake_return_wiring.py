"""The running gateway is what lets a wake turn's reply reach the IM chat; stopping it takes that away."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock

import pytest

from app.channels.types import InboundMessage
from app.core.channel_bridge import channel_gateway, setup
from app.core.channel_bridge.wake_return import WakeOrigins, origins
from app.services.agent.adaptive_wakeup.reply_return import return_wake_reply, set_wake_reply_returner

_MSG = InboundMessage(channel="telegram", sender_id="u1", content="research it", chat_id="room-1")


@pytest.fixture
def deliver(monkeypatch: pytest.MonkeyPatch) -> Iterator[AsyncMock]:
    """The gateway's delivery, recorded, with the IM chats the turns have been talked in starting empty."""
    recorded = AsyncMock(return_value=True)
    monkeypatch.setattr(channel_gateway, "deliver_followup", recorded)
    monkeypatch.setattr(channel_gateway, "stop", AsyncMock())
    monkeypatch.setattr(origins, "_origins", WakeOrigins())
    set_wake_reply_returner(None)
    yield recorded
    set_wake_reply_returner(None)


@pytest.mark.asyncio
async def test_a_turn_that_talked_in_a_chat_lets_the_wake_reply_of_that_chat_reach_the_gateway(deliver: AsyncMock) -> None:
    setup._register_wake_reply_returner()
    origins.get_wake_origins().remember("chat-db-1", _MSG)

    await return_wake_reply("chat-db-1", "The research is done.")

    deliver.assert_awaited_once()
    assert deliver.await_args is not None
    assert deliver.await_args.args[1] == "The research is done."


@pytest.mark.asyncio
async def test_a_chat_no_turn_talked_in_is_not_sent_anywhere(deliver: AsyncMock) -> None:
    setup._register_wake_reply_returner()

    await return_wake_reply("chat-db-2", "The research is done.")

    deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_stopped_gateway_returns_nothing(deliver: AsyncMock) -> None:
    setup._register_wake_reply_returner()
    origins.get_wake_origins().remember("chat-db-1", _MSG)

    await setup.stop_channel_gateway()
    await return_wake_reply("chat-db-1", "The research is done.")

    deliver.assert_not_awaited()
