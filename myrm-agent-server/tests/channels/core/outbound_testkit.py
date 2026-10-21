"""Shared fixtures for message-bus delivery tests: a scriptable provider and a running bus."""

from __future__ import annotations

import tempfile
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
from app.channels.reliability.retry import RetryConfig
from app.channels.types import ChannelCapabilities, ChannelStatus, MediaAttachment, MediaType, OutboundMessage

CP_MODULE = "app.services.channels.cp_egress_client"


class ProbeChannel(BaseChannel):
    """Configurable provider: returns ``result`` or raises ``error`` and records every send."""

    name = "probe"
    retry_config = RetryConfig(max_retries=3, base_delay=0.0, jitter=0.0)

    def __init__(
        self,
        *,
        capabilities: ChannelCapabilities | None = None,
        result: str | None = "mid-1",
        error: Exception | None = None,
        error_only_with_media: bool = False,
    ) -> None:
        super().__init__()
        self.capabilities = capabilities or ChannelCapabilities(media=True, file_upload=True)
        self.result = result
        self.error = error
        self.error_only_with_media = error_only_with_media
        self.sent: list[OutboundMessage] = []
        self._status = ChannelStatus.RUNNING

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        if self.error is not None and (msg.media or not self.error_only_with_media):
            raise self.error
        return self.result


def make_msg(content: str = "hello", *, media: tuple[MediaAttachment, ...] = ()) -> OutboundMessage:
    return OutboundMessage(channel="probe", recipient_id="chat-1", content=content, user_id="u1", media=media)


def make_doc(name: str) -> MediaAttachment:
    return MediaAttachment(media_type=MediaType.DOCUMENT, path=f"/tmp/{name}")


@asynccontextmanager
async def running_bus(tmp_path: Path | None, channel: BaseChannel | None = None) -> AsyncIterator[MessageBus]:
    """A started bus; ``tmp_path=None`` runs it without a durable outbox."""
    bus = MessageBus(dlq_dir=tmp_path)
    if channel is not None:
        bus.register_channel(channel)
    await bus.start()
    try:
        yield bus
    finally:
        await bus.stop()


def make_ephemeral_doc(name: str) -> MediaAttachment:
    """A bus-owned temp file that really exists on disk, named ``name`` for the recipient."""
    with tempfile.NamedTemporaryFile(prefix="outbound_testkit_", suffix=f"_{name}", delete=False) as tmp:
        tmp.write(b"payload")
    return MediaAttachment(media_type=MediaType.DOCUMENT, path=tmp.name, filename=name, ephemeral=True)
