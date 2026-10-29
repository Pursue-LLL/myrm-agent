"""``deliver_chunks`` behind the real message bus: what the recipient holds, and what the bus records."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.channels.core.chunk_delivery import deliver_chunks
from app.channels.core.exceptions import ChannelSendError
from app.channels.types import OutboundMessage
from tests.channels.core.outbound_testkit import ProbeChannel, make_msg, running_bus


class _ChunkingChannel(ProbeChannel):
    """Posts the ``|``-separated parts of a reply one request each; ``refusals`` maps a part to how often the platform refuses it."""

    def __init__(self, refusals: dict[str, int]) -> None:
        super().__init__()
        self.refusals = dict(refusals)
        self.attempts: list[str] = []
        self.received: list[str] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        async def post(chunk: str, index: int) -> str | None:
            self.attempts.append(chunk)
            if self.refusals.get(chunk, 0) > 0:
                self.refusals[chunk] -= 1
                raise ChannelSendError(f"HTTP 503 on {chunk}", channel=self.name, status_code=503)
            self.received.append(chunk)
            return f"mid-{index}"

        return await deliver_chunks(self, msg.content.split("|"), post)


@pytest.mark.asyncio
async def test_a_later_part_that_fails_once_is_retried_alone_and_nothing_is_recorded(tmp_path: Path) -> None:
    channel = _ChunkingChannel({"two": 1})
    async with running_bus(tmp_path, channel) as bus:
        assert await bus.send_now(make_msg("one|two|three")) == "mid-2"

        assert channel.received == ["one", "two", "three"]
        assert channel.attempts == ["one", "two", "two", "three"]
        assert await bus.get_dlq_messages() == []


@pytest.mark.asyncio
async def test_a_first_part_that_fails_once_is_retried_by_the_bus_and_arrives_once(tmp_path: Path) -> None:
    channel = _ChunkingChannel({"one": 1})
    async with running_bus(tmp_path, channel) as bus:
        await bus.send_now(make_msg("one|two|three"))

        assert channel.received == ["one", "two", "three"]
        assert channel.attempts == ["one", "one", "two", "three"]


@pytest.mark.asyncio
async def test_a_later_part_that_keeps_failing_is_recorded_once_and_the_delivered_parts_are_not_resent(
    tmp_path: Path,
) -> None:
    channel = _ChunkingChannel({"two": 99})
    async with running_bus(tmp_path, channel) as bus:
        with pytest.raises(ChannelSendError) as exc_info:
            await bus.send_now(make_msg("one|two|three"))

        assert exc_info.value.accepted is True
        assert channel.received == ["one"]
        assert channel.attempts.count("one") == 1
        assert len(await bus.get_dlq_messages()) == 1
