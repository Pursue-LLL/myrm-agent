"""``MessageBus.drain_outbound``: a shutdown waits for what was just published, but never forever."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.channels.core.bus import MessageBus
from app.channels.types import OutboundMessage
from tests.channels.core.outbound_testkit import ProbeChannel, make_msg, running_bus


class _SlowChannel(ProbeChannel):
    """A provider whose send takes ``latency`` seconds; ``delivered`` lists what its sends finished."""

    def __init__(self, latency: float) -> None:
        super().__init__()
        self._latency = latency
        self.delivered: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        await asyncio.sleep(self._latency)
        self.delivered.append(msg)
        return "mid-1"


class _StuckChannel(ProbeChannel):
    """A provider whose send never returns."""

    async def send(self, msg: OutboundMessage) -> str | None:
        await asyncio.Event().wait()
        return None


@pytest.mark.asyncio
async def test_a_drain_waits_for_the_message_that_is_still_being_sent() -> None:
    channel = _SlowChannel(latency=0.2)
    async with running_bus(None, channel) as bus:
        await bus.publish_outbound(make_msg("last words"))
        await asyncio.sleep(0.05)  # picked up by the dispatch loop, mid-send

        assert await bus.drain_outbound(timeout=5) is True

        assert [m.content for m in channel.delivered] == ["last words"]


@pytest.mark.asyncio
async def test_a_drain_waits_for_every_queued_message() -> None:
    channel = _SlowChannel(latency=0.05)
    async with running_bus(None, channel) as bus:
        for text in ("one", "two", "three"):
            await bus.publish_outbound(make_msg(text))

        assert await bus.drain_outbound(timeout=5) is True

        assert [m.content for m in channel.delivered] == ["one", "two", "three"]


@pytest.mark.asyncio
async def test_a_drain_returns_at_once_when_nothing_is_queued() -> None:
    async with running_bus(None, ProbeChannel()) as bus:
        started = time.monotonic()

        assert await bus.drain_outbound(timeout=5) is True

        assert time.monotonic() - started < 1


@pytest.mark.asyncio
async def test_a_bus_that_never_started_has_nothing_to_drain() -> None:
    assert await MessageBus().drain_outbound(timeout=5) is True


@pytest.mark.asyncio
async def test_a_drain_gives_up_at_the_timeout_when_a_send_never_returns() -> None:
    async with running_bus(None, _StuckChannel()) as bus:
        await bus.publish_outbound(make_msg("stuck"))
        started = time.monotonic()

        assert await bus.drain_outbound(timeout=0.2) is False

        assert time.monotonic() - started < 2


@pytest.mark.asyncio
async def test_a_drain_does_not_wait_for_a_dispatch_loop_that_is_not_running() -> None:
    bus = MessageBus()
    await bus.publish_outbound(make_msg("nobody is delivering this"))
    started = time.monotonic()

    assert await bus.drain_outbound(timeout=5) is False

    assert time.monotonic() - started < 1
