"""The gateway delivers a reply no message asked for through its router, over the channel the conversation came from."""

from __future__ import annotations

import asyncio
import tempfile
from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import ChannelCapabilities, InboundMessage, MediaAttachment, MediaType, OutboundMessage

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
async def test_a_gateway_without_a_router_delivers_nothing_and_leaves_no_temp_attachment_behind() -> None:
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as handle:
        handle.write(b"image")
    path = Path(handle.name)
    attachment = MediaAttachment(media_type=MediaType.IMAGE, path=str(path), filename=path.name, ephemeral=True)

    try:
        assert await ChannelGateway().deliver_followup(_ORIGIN, "done", (attachment,)) is False

        assert not path.exists()
    finally:
        path.unlink(missing_ok=True)


def test_a_gateway_without_a_router_runs_no_turn_for_any_conversation() -> None:
    assert ChannelGateway().is_session_busy(_ORIGIN) is False


def test_the_gateway_reports_what_its_router_says_about_the_conversation(
    running_gateway: tuple[ChannelGateway, _RecordingChannel],
) -> None:
    gateway, _channel = running_gateway
    router = gateway._router
    assert router is not None
    router.is_session_busy = MagicMock(return_value=True)  # type: ignore[method-assign]

    assert gateway.is_session_busy(_ORIGIN) is True
    router.is_session_busy.assert_called_once_with(_ORIGIN)
