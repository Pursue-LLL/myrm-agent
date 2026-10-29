"""The gateway delivers a reply no message asked for through its router, over the channel the conversation came from."""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import ChannelCapabilities, InboundMessage, OutboundMessage

_ORIGIN = InboundMessage(channel="pingchat", sender_id="u1", chat_id="room-1", content="research it", metadata={"locale": "en"})


class _RecordingChannel(BaseChannel):
    name = "pingchat"
    capabilities = ChannelCapabilities()

    def __init__(self) -> None:
        super().__init__()
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "mid-1"


@pytest.fixture
async def running_gateway() -> AsyncIterator[tuple[ChannelGateway, _RecordingChannel]]:
    channel = _RecordingChannel()
    gateway = ChannelGateway()
    gateway.register(channel)
    gateway.enable_bidirectional(pairing_store=MagicMock(), agent_executor=MagicMock())
    router = gateway._router
    assert router is not None
    router._attach_web_handoff = AsyncMock(side_effect=lambda result, _msg: result)  # type: ignore[method-assign]
    await gateway.start()
    yield gateway, channel
    await gateway.stop()


@pytest.mark.asyncio
async def test_the_reply_reaches_the_channel_of_the_conversation(
    running_gateway: tuple[ChannelGateway, _RecordingChannel],
) -> None:
    gateway, channel = running_gateway

    assert await gateway.deliver_followup(_ORIGIN, "The research is done.") is True
    for _ in range(200):
        if channel.sent:
            break
        await asyncio.sleep(0.01)

    assert [(sent.recipient_id, sent.content) for sent in channel.sent] == [("room-1", "The research is done.")]


@pytest.mark.asyncio
async def test_a_gateway_without_a_router_delivers_nothing() -> None:
    assert await ChannelGateway().deliver_followup(_ORIGIN, "done") is False
