"""A channel asks the access policy about a sender outside the inbound pipeline.

A platform can let a user act on the bot without sending it a message (a Discord slash command that moves the bot
between voice channels). Such an action must follow the same sender policy as a message from that user. The bus hands
every channel it registers a way to ask, and whatever answers (the router) is set on the bus once: a channel registered
before or after it asks the same gate. Nothing wired, or a channel off the bus, admits no one.
"""

from __future__ import annotations

from unittest.mock import AsyncMock

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.types import InboundMessage, OutboundMessage


class _Channel(BaseChannel):
    name = "gate-test"

    async def send(self, msg: OutboundMessage) -> str | None:
        return None


def _msg() -> InboundMessage:
    return InboundMessage(channel="gate-test", sender_id="u1", user_id="u1", chat_id="c1", content="/act", is_group=True)


async def test_a_channel_nobody_wired_admits_no_one() -> None:
    assert await _Channel().is_sender_admitted(_msg()) is False


async def test_a_bus_without_a_gate_admits_no_one() -> None:
    bus = MessageBus()
    channel = _Channel()
    bus.register_channel(channel)

    assert await channel.is_sender_admitted(_msg()) is False


async def test_a_registered_channel_asks_the_gate_of_the_bus() -> None:
    bus = MessageBus()
    gate = AsyncMock(return_value=True)
    bus.set_sender_gate(gate)
    channel = _Channel()
    bus.register_channel(channel)
    msg = _msg()

    assert await channel.is_sender_admitted(msg) is True

    gate.assert_awaited_once_with(msg)


async def test_the_gate_decides_each_time_it_is_asked() -> None:
    bus = MessageBus()
    gate = AsyncMock(side_effect=[True, False])
    bus.set_sender_gate(gate)
    channel = _Channel()
    bus.register_channel(channel)

    assert await channel.is_sender_admitted(_msg()) is True
    assert await channel.is_sender_admitted(_msg()) is False


async def test_a_gate_set_after_the_channel_registered_applies_to_it() -> None:
    bus = MessageBus()
    channel = _Channel()
    bus.register_channel(channel)
    bus.set_sender_gate(AsyncMock(return_value=True))

    assert await channel.is_sender_admitted(_msg()) is True


async def test_a_channel_removed_from_the_bus_admits_no_one() -> None:
    bus = MessageBus()
    bus.set_sender_gate(AsyncMock(return_value=True))
    channel = _Channel()
    bus.register_channel(channel)

    bus.unregister_channel(channel.name)

    assert await channel.is_sender_admitted(_msg()) is False
