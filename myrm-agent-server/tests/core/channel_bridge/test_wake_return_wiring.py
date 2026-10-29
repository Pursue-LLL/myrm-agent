"""The running gateway is what lets a wake turn wait for the member's IM turn and reply in that chat; stopping it takes that away."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.types import InboundMessage
from app.core.channel_bridge import channel_gateway, setup
from app.core.channel_bridge.wake_return import WakeOrigins, origins, register_wake_im_ports
from app.services.agent.adaptive_wakeup.chat_busy import is_chat_busy, set_chat_busy_probe
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
    set_chat_busy_probe(None)
    yield recorded
    set_wake_reply_returner(None)
    set_chat_busy_probe(None)


@pytest.mark.asyncio
async def test_a_turn_that_talked_in_a_chat_lets_the_wake_reply_of_that_chat_reach_the_gateway(deliver: AsyncMock) -> None:
    register_wake_im_ports(channel_gateway)
    origins.get_wake_origins().remember("chat-db-1", _MSG)

    await return_wake_reply("chat-db-1", "The research is done.")

    deliver.assert_awaited_once()
    assert deliver.await_args is not None
    assert deliver.await_args.args[1] == "The research is done."


@pytest.mark.asyncio
async def test_a_chat_no_turn_talked_in_is_not_sent_anywhere(deliver: AsyncMock) -> None:
    register_wake_im_ports(channel_gateway)

    await return_wake_reply("chat-db-2", "The research is done.")

    deliver.assert_not_awaited()


@pytest.mark.asyncio
async def test_a_stopped_gateway_returns_nothing(deliver: AsyncMock) -> None:
    register_wake_im_ports(channel_gateway)
    origins.get_wake_origins().remember("chat-db-1", _MSG)

    await setup.stop_channel_gateway()
    await return_wake_reply("chat-db-1", "The research is done.")

    deliver.assert_not_awaited()


def test_the_running_gateway_tells_a_wake_turn_which_chats_its_router_runs_a_turn_for(
    deliver: AsyncMock, monkeypatch: pytest.MonkeyPatch
) -> None:
    busy = MagicMock(return_value=True)
    monkeypatch.setattr(channel_gateway, "is_session_busy", busy)
    register_wake_im_ports(channel_gateway)
    origins.get_wake_origins().remember("chat-db-1", _MSG)

    assert is_chat_busy("chat-db-1") is True
    assert is_chat_busy("chat-db-2") is False
    busy.assert_called_once()


@pytest.mark.asyncio
async def test_a_stopped_gateway_leaves_no_chat_busy(deliver: AsyncMock, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_gateway, "is_session_busy", MagicMock(return_value=True))
    register_wake_im_ports(channel_gateway)
    origins.get_wake_origins().remember("chat-db-1", _MSG)

    await setup.stop_channel_gateway()

    assert is_chat_busy("chat-db-1") is False
