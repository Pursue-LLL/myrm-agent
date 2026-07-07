"""Integration tests for outbound_notify wiring (no mocks on notify delivery path)."""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import pytest

from pathlib import Path

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import ChannelStatus, OutboundMessage
from app.channels.types.status import ChannelCapabilities
from app.services.agent.outbound_notify import (
    NotifyTarget,
    NotifyToolConfig,
    create_channel_notify_tool,
    create_notification_sender,
)


class RecordingChannel(BaseChannel):
    """Minimal channel that records outbound messages for integration tests."""

    name = "telegram"
    capabilities = ChannelCapabilities(media=True, file_upload=True)

    def __init__(self) -> None:
        super().__init__()
        self._status = ChannelStatus.RUNNING
        self.sent: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        self.sent.append(msg)
        return "msg-1"

    async def start(self) -> None:
        return None

    async def stop(self) -> None:
        return None


@asynccontextmanager
async def wired_gateway(
    channel: BaseChannel,
) -> AsyncIterator[ChannelGateway]:
    """Start gateway with channel registered and channel_bridge wired."""
    gateway = ChannelGateway()
    gateway.register(channel)
    await gateway.start()

    import app.core.channel_bridge as channel_bridge

    previous = channel_bridge.channel_gateway
    channel_bridge.channel_gateway = gateway
    try:
        yield gateway
    finally:
        channel_bridge.channel_gateway = previous
        await gateway.stop()


def _make_tool(
    *,
    channel: BaseChannel | None = None,
    rate_limit: int = 10,
    max_body_length: int = 4000,
    allowed_roots: tuple[str, ...] = (),
) -> tuple[object, RecordingChannel]:
    ch = channel if channel is not None else RecordingChannel()
    targets = ({"channel": ch.name, "recipient_id": "chat_123", "label": "My TG"},)
    sender_result = create_notification_sender(targets)
    assert sender_result is not None
    sender, config = sender_result
    limited = NotifyToolConfig(
        allowed_targets=config.allowed_targets,
        rate_limit_per_session=rate_limit,
        max_body_length=max_body_length,
    )
    return create_channel_notify_tool(sender, limited, allowed_roots=allowed_roots), ch


class FailingSendChannel(RecordingChannel):
    """Channel whose send() always fails (send_tracked returns None)."""

    async def send(self, msg: OutboundMessage) -> str | None:
        return None


@pytest.mark.asyncio
async def test_tool_delivery_through_real_channel_gateway() -> None:
    """channel_notify_tool → ChannelNotificationSender → bus.send_tracked."""
    channel = RecordingChannel()
    async with wired_gateway(channel):
        tool, _ = _make_tool(channel=channel)
        result = await tool.ainvoke({"channel": "telegram", "target": "", "body": "integration hello"})
        assert "success" in result.lower()
        assert len(channel.sent) == 1
        assert channel.sent[0].recipient_id == "chat_123"
        assert channel.sent[0].content == "integration hello"


@pytest.mark.asyncio
async def test_chat_channel_delivery_through_real_channel_gateway() -> None:
    """Real ChatChannel (ORM write) via ChannelGateway — regression for sent_at/sent_timezone."""
    from sqlalchemy import select

    from app.core.channel_bridge.providers.chat import ChatChannel
    from app.database.connection import get_session
    from app.database.models import Message

    recipient_id = f"notify_wiring_{uuid.uuid4().hex[:8]}"
    channel = ChatChannel()
    targets = ({"channel": "chat", "recipient_id": recipient_id, "label": "Wiring"},)
    sender_result = create_notification_sender(targets)
    assert sender_result is not None
    sender, config = sender_result
    limited = NotifyToolConfig(
        allowed_targets=config.allowed_targets,
        rate_limit_per_session=10,
        max_body_length=4000,
    )
    tool = create_channel_notify_tool(sender, limited)

    async with wired_gateway(channel):
        result = await tool.ainvoke({"channel": "chat", "target": "", "body": "chat gateway hello"})
        assert "success" in result.lower()

    async with get_session() as session:
        rows = (
            await session.execute(
                select(Message).where(Message.chat_id == recipient_id),
            )
        ).scalars().all()
        assert len(rows) == 1
        assert rows[0].content == "chat gateway hello"
        assert rows[0].sent_at is not None
        assert rows[0].sent_timezone == "UTC"


def test_profile_resolver_filtering_then_factory() -> None:
    """Same filter as profile_resolver.resolve() before factory wiring."""
    raw_notify: list[object] = [
        {"channel": "telegram", "recipient_id": "123"},
        {"channel": "slack"},
        {"recipient_id": "orphan"},
        "not-a-dict",
    ]
    notify_targets: tuple[dict[str, str], ...] = tuple(
        entry
        for entry in raw_notify
        if isinstance(entry, dict) and "channel" in entry and "recipient_id" in entry
    )
    assert notify_targets == ({"channel": "telegram", "recipient_id": "123"},)

    sender_result = create_notification_sender(notify_targets)
    assert sender_result is not None
    sender, config = sender_result
    assert len(config.allowed_targets) == 1
    assert config.allowed_targets[0] == NotifyTarget(
        channel="telegram",
        recipient_id="123",
        label="",
    )
    assert sender is not None


@pytest.mark.asyncio
async def test_rate_limit_blocks_second_burst_through_gateway() -> None:
    channel = RecordingChannel()
    async with wired_gateway(channel):
        tool, _ = _make_tool(channel=channel, rate_limit=1)
        first = await tool.ainvoke({"channel": "", "target": "", "body": "one"})
        second = await tool.ainvoke({"channel": "", "target": "", "body": "two"})

        assert "success" in first.lower()
        assert "rate limit" in second.lower()
        assert len(channel.sent) == 1


@pytest.mark.asyncio
async def test_empty_body_rejected_without_gateway_send() -> None:
    channel = RecordingChannel()
    async with wired_gateway(channel):
        tool, _ = _make_tool(channel=channel)
        result = await tool.ainvoke({"channel": "telegram", "target": "", "body": "   "})
        assert "empty" in result.lower()
        assert len(channel.sent) == 0


@pytest.mark.asyncio
async def test_target_not_found_without_gateway_send() -> None:
    channel = RecordingChannel()
    async with wired_gateway(channel):
        tool, _ = _make_tool(channel=channel)
        result = await tool.ainvoke({"channel": "discord", "target": "", "body": "hello"})
        assert "not found" in result.lower() or "not allowed" in result.lower()
        assert "telegram:chat_123" in result
        assert len(channel.sent) == 0


@pytest.mark.asyncio
async def test_body_truncation_through_gateway() -> None:
    channel = RecordingChannel()
    async with wired_gateway(channel):
        tool, _ = _make_tool(channel=channel, max_body_length=50)
        long_body = "x" * 120
        result = await tool.ainvoke({"channel": "", "target": "", "body": long_body})
        assert "success" in result.lower()
        assert len(channel.sent) == 1
        assert channel.sent[0].content.endswith("[...truncated]")
        assert len(channel.sent[0].content) <= 50 + len("\n\n[...truncated]")


@pytest.mark.asyncio
async def test_send_tracked_failure_surfaces_delivery_error() -> None:
    """AB' guard: send_tracked returning None must not report success."""
    channel = FailingSendChannel()
    async with wired_gateway(channel):
        tool, _ = _make_tool(channel=channel)
        result = await tool.ainvoke({"channel": "telegram", "target": "", "body": "hello"})
        assert "error" in result.lower()
        assert "failed" in result.lower()
        assert len(channel.sent) == 0


@pytest.mark.asyncio
async def test_gateway_not_initialized_surfaces_error() -> None:
    import app.core.channel_bridge as channel_bridge

    previous = channel_bridge.channel_gateway
    channel_bridge.channel_gateway = None
    try:
        tool, _ = _make_tool()
        result = await tool.ainvoke({"channel": "", "target": "", "body": "hello"})
        assert "error" in result.lower()
        assert "not initialized" in result.lower()
    finally:
        channel_bridge.channel_gateway = previous


def test_empty_notify_targets_skips_sender_factory() -> None:
    """Factory guard: create_notification_sender returns None when no targets."""
    assert create_notification_sender(()) is None


@pytest.mark.asyncio
async def test_attachment_delivered_through_real_channel_gateway() -> None:
    """channel_notify_tool with attachments → media flows through ChannelGateway to channel."""
    import tempfile

    channel = RecordingChannel()

    with tempfile.NamedTemporaryFile(suffix=".pdf", delete=False) as f:
        f.write(b"fake pdf")
        tmp_file = f.name

    try:
        async with wired_gateway(channel):
            tool, _ = _make_tool(
                channel=channel,
                allowed_roots=(str(Path(tmp_file).parent),),
            )
            result = await tool.ainvoke({
                "channel": "telegram",
                "target": "",
                "body": "Report ready",
                "attachments": [tmp_file],
            })
            assert "success" in result.lower()
            assert "1 attachment" in result.lower()
            assert len(channel.sent) == 1
            msg = channel.sent[0]
            assert msg.content == "Report ready"
            assert len(msg.media) == 1
            assert msg.media[0].path == tmp_file
            assert msg.media[0].media_type.value == "document"
    finally:
        import os

        os.unlink(tmp_file)


@pytest.mark.asyncio
async def test_url_attachment_delivered_through_gateway() -> None:
    """URL attachment flows through to OutboundMessage.media."""
    channel = RecordingChannel()
    async with wired_gateway(channel):
        tool, _ = _make_tool(channel=channel)
        result = await tool.ainvoke({
            "channel": "",
            "target": "",
            "body": "See image",
            "attachments": ["https://example.com/chart.png"],
        })
        assert "success" in result.lower()
        assert len(channel.sent) == 1
        msg = channel.sent[0]
        assert len(msg.media) == 1
        assert msg.media[0].url == "https://example.com/chart.png"
        assert msg.media[0].media_type.value == "image"


@pytest.mark.asyncio
async def test_attachment_only_no_body_through_gateway() -> None:
    """Attachment-only message (empty body) flows through ChannelGateway."""
    channel = RecordingChannel()
    async with wired_gateway(channel):
        tool, _ = _make_tool(channel=channel)
        result = await tool.ainvoke({
            "channel": "",
            "target": "",
            "body": "",
            "attachments": ["https://example.com/report.pdf"],
        })
        assert "success" in result.lower()
        assert len(channel.sent) == 1
        msg = channel.sent[0]
        assert msg.content == ""
        assert len(msg.media) == 1
        assert msg.media[0].media_type.value == "document"


@pytest.mark.asyncio
async def test_multiple_attachments_through_gateway() -> None:
    """Multiple attachments all reach the channel via ChannelGateway."""
    import tempfile

    channel = RecordingChannel()

    with tempfile.NamedTemporaryFile(suffix=".csv", delete=False) as f:
        f.write(b"col1,col2")
        tmp_file = f.name

    try:
        async with wired_gateway(channel):
            tool, _ = _make_tool(
                channel=channel,
                allowed_roots=(str(Path(tmp_file).parent),),
            )
            result = await tool.ainvoke({
                "channel": "",
                "target": "",
                "body": "Multiple files",
                "attachments": [
                    tmp_file,
                    "https://cdn.example.com/photo.jpg",
                ],
            })
            assert "success" in result.lower()
            assert "2 attachment" in result.lower()
            assert len(channel.sent) == 1
            msg = channel.sent[0]
            assert len(msg.media) == 2
            assert msg.media[0].path == tmp_file
            assert msg.media[1].url == "https://cdn.example.com/photo.jpg"
            assert msg.media[1].media_type.value == "image"
    finally:
        import os

        os.unlink(tmp_file)


@pytest.mark.asyncio
async def test_attachment_file_not_found_blocks_gateway_send(tmp_path: Path) -> None:
    """Nonexistent file attachment aborts before reaching ChannelGateway."""
    channel = RecordingChannel()
    missing = str(tmp_path / "missing-report.pdf")
    async with wired_gateway(channel):
        tool, _ = _make_tool(channel=channel, allowed_roots=(str(tmp_path),))
        result = await tool.ainvoke({
            "channel": "",
            "target": "",
            "body": "Report",
            "attachments": [missing],
        })
        assert "file not found" in result.lower()
        assert len(channel.sent) == 0
