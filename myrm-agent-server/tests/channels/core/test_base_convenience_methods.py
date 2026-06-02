"""Tests for BaseChannel convenience methods: respond() and broadcast()."""

import pytest

from app.channels.core.base import BaseChannel
from app.channels.types import InboundMessage, OutboundMessage


class MockChannel(BaseChannel):
    """Minimal BaseChannel implementation for testing convenience methods."""

    name = "mock"

    def __init__(self) -> None:
        super().__init__()
        self.sent_messages: list[OutboundMessage] = []

    async def send(self, msg: OutboundMessage) -> str | None:
        """Capture sent messages for verification."""
        self.sent_messages.append(msg)
        return "mock_msg_id_123"


@pytest.fixture
def mock_channel() -> MockChannel:
    """Create a mock channel for testing."""
    return MockChannel()


@pytest.fixture
def incoming_msg() -> InboundMessage:
    """Create a sample incoming message."""
    import time

    return InboundMessage(
        channel="mock",
        sender_id="user123",
        content="Hello, bot!",
        sent_at=time.time(),
        sent_timezone="UTC",
        chat_id="chat456",
        user_id="user123",
        message_id="msg789",
    )


# ───────────────────────────────────────────────────────────────────────────
# respond() tests
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_respond_basic(mock_channel: MockChannel, incoming_msg: InboundMessage) -> None:
    """Test respond() automatically infers all required fields."""
    result = await mock_channel.respond(incoming_msg, "Hello, user!")

    assert result == "mock_msg_id_123"
    assert len(mock_channel.sent_messages) == 1

    sent = mock_channel.sent_messages[0]
    assert sent.channel == "mock"  # Auto-inferred from self.name
    assert sent.recipient_id == "chat456"  # Auto-inferred from incoming_msg.chat_id
    assert sent.content == "Hello, user!"
    assert sent.user_id == "user123"  # Auto-inferred from incoming_msg.user_id
    assert sent.reply_to_id == "msg789"  # Auto-inferred (default in_thread=True)


@pytest.mark.asyncio
async def test_respond_with_in_thread_false(mock_channel: MockChannel, incoming_msg: InboundMessage) -> None:
    """Test respond() with in_thread=False (no reply_to_id)."""
    await mock_channel.respond(incoming_msg, "Hello!", in_thread=False)

    sent = mock_channel.sent_messages[0]
    assert sent.reply_to_id is None


@pytest.mark.asyncio
async def test_respond_fallback_to_sender_id(mock_channel: MockChannel) -> None:
    """Test respond() falls back to sender_id when chat_id is None."""
    import time

    incoming_msg = InboundMessage(
        channel="mock",
        sender_id="user123",
        content="Hello",
        sent_at=time.time(),
        sent_timezone="UTC",
        chat_id=None,  # No chat_id (direct message scenario)
        user_id="user123",
    )

    await mock_channel.respond(incoming_msg, "Reply")

    sent = mock_channel.sent_messages[0]
    assert sent.recipient_id == "user123"  # Fallback to sender_id


@pytest.mark.asyncio
async def test_respond_user_id_fallback(mock_channel: MockChannel) -> None:
    """Test respond() falls back to sender_id when user_id is None."""
    import time

    incoming_msg = InboundMessage(
        channel="mock",
        sender_id="user123",
        content="Hello",
        sent_at=time.time(),
        sent_timezone="UTC",
        chat_id="chat456",
        user_id=None,  # No user_id
    )

    await mock_channel.respond(incoming_msg, "Reply")

    sent = mock_channel.sent_messages[0]
    assert sent.user_id == "user123"  # Fallback to sender_id


@pytest.mark.asyncio
async def test_respond_with_additional_kwargs(mock_channel: MockChannel, incoming_msg: InboundMessage) -> None:
    """Test respond() forwards additional **kwargs to OutboundMessage."""
    from app.channels.types import MediaAttachment, MediaType

    media_attachment = MediaAttachment(media_type=MediaType.IMAGE, url="https://example.com/image.png")

    await mock_channel.respond(
        incoming_msg,
        "Reply with media",
        media=(media_attachment,),
        metadata={"custom": "data"},
    )

    sent = mock_channel.sent_messages[0]
    assert len(sent.media) == 1
    assert sent.media[0].url == "https://example.com/image.png"
    assert sent.metadata == {"custom": "data"}


# ───────────────────────────────────────────────────────────────────────────
# broadcast() tests
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_broadcast_basic(mock_channel: MockChannel) -> None:
    """Test broadcast() sends proactive message with explicit user_id."""
    result = await mock_channel.broadcast(
        "channel123",
        "Cron job completed!",
        user_id="user456",
    )

    assert result == "mock_msg_id_123"
    assert len(mock_channel.sent_messages) == 1

    sent = mock_channel.sent_messages[0]
    assert sent.channel == "mock"  # Auto-inferred from self.name
    assert sent.recipient_id == "channel123"
    assert sent.content == "Cron job completed!"
    assert sent.user_id == "user456"
    assert sent.metadata is None


@pytest.mark.asyncio
async def test_broadcast_with_thread_ts(mock_channel: MockChannel) -> None:
    """Test broadcast() with thread_ts adds it to metadata."""
    await mock_channel.broadcast(
        "channel123",
        "Thread message",
        user_id="user456",
        thread_ts="1234.5678",
    )

    sent = mock_channel.sent_messages[0]
    assert sent.metadata == {"thread_ts": "1234.5678"}


@pytest.mark.asyncio
async def test_broadcast_with_existing_metadata(mock_channel: MockChannel) -> None:
    """Test broadcast() merges thread_ts with existing metadata."""
    await mock_channel.broadcast(
        "channel123",
        "Message",
        user_id="user456",
        thread_ts="1234.5678",
        metadata={"job_name": "daily_report"},
    )

    sent = mock_channel.sent_messages[0]
    # thread_ts should be added to existing metadata
    assert sent.metadata == {"job_name": "daily_report", "thread_ts": "1234.5678"}


@pytest.mark.asyncio
async def test_broadcast_with_additional_kwargs(mock_channel: MockChannel) -> None:
    """Test broadcast() forwards additional **kwargs to OutboundMessage."""
    from app.channels.types import MediaAttachment, MediaType, MessagePriority

    media_attachment = MediaAttachment(media_type=MediaType.DOCUMENT, path="/path/to/file.pdf")

    await mock_channel.broadcast(
        "channel123",
        "Alert!",
        user_id="user456",
        media=(media_attachment,),
        priority=MessagePriority.SYSTEM,
    )

    sent = mock_channel.sent_messages[0]
    assert len(sent.media) == 1
    assert sent.media[0].path == "/path/to/file.pdf"
    assert sent.priority == MessagePriority.SYSTEM


@pytest.mark.asyncio
async def test_broadcast_with_empty_metadata(mock_channel: MockChannel) -> None:
    """Test broadcast() sets metadata=None when empty."""
    await mock_channel.broadcast(
        "channel123",
        "Message",
        user_id="user456",
    )

    sent = mock_channel.sent_messages[0]
    assert sent.metadata is None


# ───────────────────────────────────────────────────────────────────────────
# Integration: respond() vs send() comparison
# ───────────────────────────────────────────────────────────────────────────


@pytest.mark.asyncio
async def test_respond_equivalent_to_send(mock_channel: MockChannel, incoming_msg: InboundMessage) -> None:
    """Test respond() produces same result as manual send(OutboundMessage())."""
    # Manual send (verbose)
    await mock_channel.send(
        OutboundMessage(
            channel="mock",
            recipient_id=incoming_msg.chat_id or incoming_msg.sender_id,
            content="Manual reply",
            user_id=incoming_msg.user_id or incoming_msg.sender_id,
            reply_to_id=incoming_msg.message_id,
        )
    )

    # Convenience respond
    await mock_channel.respond(incoming_msg, "Manual reply")

    # Should produce identical messages
    manual_sent = mock_channel.sent_messages[0]
    convenience_sent = mock_channel.sent_messages[1]

    assert manual_sent.channel == convenience_sent.channel
    assert manual_sent.recipient_id == convenience_sent.recipient_id
    assert manual_sent.content == convenience_sent.content
    assert manual_sent.user_id == convenience_sent.user_id
    assert manual_sent.reply_to_id == convenience_sent.reply_to_id


@pytest.mark.asyncio
async def test_broadcast_equivalent_to_send(mock_channel: MockChannel) -> None:
    """Test broadcast() produces same result as manual send(OutboundMessage())."""
    # Manual send (verbose)
    await mock_channel.send(
        OutboundMessage(
            channel="mock",
            recipient_id="channel123",
            content="Cron completed",
            user_id="user456",
        )
    )

    # Convenience broadcast
    await mock_channel.broadcast("channel123", "Cron completed", user_id="user456")

    # Should produce identical messages
    manual_sent = mock_channel.sent_messages[0]
    convenience_sent = mock_channel.sent_messages[1]

    assert manual_sent.channel == convenience_sent.channel
    assert manual_sent.recipient_id == convenience_sent.recipient_id
    assert manual_sent.content == convenience_sent.content
    assert manual_sent.user_id == convenience_sent.user_id
