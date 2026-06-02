"""Tests for thread sharing mode functionality."""

from __future__ import annotations

from dataclasses import FrozenInstanceError

import pytest

from app.channels.types.messages import (
    InboundMessage,
    TopicContext,
)
from app.channels.types.session import SessionKey
from app.channels.types.thread_sharing import ThreadSharingMode


class TestThreadSharingModeEnum:
    """Test ThreadSharingMode enumeration."""

    def test_values(self) -> None:
        assert ThreadSharingMode.ISOLATED == "isolated"
        assert ThreadSharingMode.SHARED == "shared"

    def test_str_enum_behavior(self) -> None:
        assert str(ThreadSharingMode.ISOLATED) == "isolated"
        assert ThreadSharingMode.SHARED.value == "shared"


class TestTopicContextThreadSharing:
    """Test TopicContext thread_sharing_mode field."""

    def test_default_isolated(self) -> None:
        ctx = TopicContext(topic_id="test-topic")
        assert ctx.thread_sharing_mode == ThreadSharingMode.ISOLATED

    def test_explicit_shared(self) -> None:
        ctx = TopicContext(topic_id="test-topic", thread_sharing_mode=ThreadSharingMode.SHARED)
        assert ctx.thread_sharing_mode == ThreadSharingMode.SHARED

    def test_explicit_isolated(self) -> None:
        ctx = TopicContext(topic_id="test-topic", thread_sharing_mode=ThreadSharingMode.ISOLATED)
        assert ctx.thread_sharing_mode == ThreadSharingMode.ISOLATED

    def test_frozen_dataclass(self) -> None:
        ctx = TopicContext(topic_id="test-topic")
        with pytest.raises(FrozenInstanceError):
            ctx.thread_sharing_mode = ThreadSharingMode.SHARED


class TestSessionKeyThreadSharing:
    """Test SessionKey behavior in thread sharing scenarios (no user_id dimension)."""

    def test_shared_thread_key_format(self) -> None:
        key = SessionKey(
            channel="discord",
            peer_kind="group",
            peer_id="forum-123",
            thread_id="thread-456",
        )
        result = key.to_str()
        assert result.startswith("discord:group:forum-123")
        assert ":thread:thread-456" in result

    def test_shared_thread_roundtrip(self) -> None:
        key = SessionKey(
            channel="discord",
            peer_kind="group",
            peer_id="forum-123",
        )
        serialized = key.to_str()
        parsed = SessionKey.parse(serialized)
        assert parsed is not None
        assert parsed.channel == "discord"

    def test_different_threads_produce_different_keys(self) -> None:
        key_thread_a = SessionKey(
            channel="discord",
            peer_kind="group",
            peer_id="forum-123",
            thread_id="thread-456",
        )
        key_thread_b = SessionKey(
            channel="discord",
            peer_kind="group",
            peer_id="forum-123",
            thread_id="thread-789",
        )
        assert key_thread_a.to_str() != key_thread_b.to_str()


class TestInboundMessageWithThreadSharing:
    """Test InboundMessage integration with thread sharing."""

    def test_inbound_message_thread_id_present(self) -> None:
        msg = InboundMessage(
            channel="discord",
            sender_id="user-123",
            chat_id="forum-456",
            content="Hello",
            is_group=True,
            thread_id="thread-789",
            sent_at=1234567890.0,
            sent_timezone="UTC",
        )
        assert msg.thread_id == "thread-789"

    def test_inbound_message_no_thread_id(self) -> None:
        msg = InboundMessage(
            channel="discord",
            sender_id="user-123",
            chat_id="dm-456",
            content="Hello",
            is_group=False,
            sent_at=1234567890.0,
            sent_timezone="UTC",
        )
        assert msg.thread_id is None
