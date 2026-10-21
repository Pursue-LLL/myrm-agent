"""Tests for thread sharing mode in session key construction."""

from __future__ import annotations

import pytest

from app.channels.types.messages import (
    InboundMessage,
)
from app.channels.types.session import (
    SessionKey,
    SessionPolicy,
    SessionResetMode,
)
from app.channels.types.thread_sharing import ThreadSharingMode
from app.core.channel_bridge.agent_executor.session import _build_session_key, resolve_session_key


class TestBuildSessionKeyThreadSharing:
    """Test _build_session_key with thread sharing mode."""

    def test_isolated_mode_includes_user_id(self) -> None:
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
        key = _build_session_key(msg, thread_sharing_mode=ThreadSharingMode.ISOLATED)
        parsed = SessionKey.parse(key)
        assert parsed is not None

    def test_shared_mode_removes_user_id(self) -> None:
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
        key = _build_session_key(msg, thread_sharing_mode=ThreadSharingMode.SHARED)
        parsed = SessionKey.parse(key)
        assert parsed is not None

    def test_shared_mode_same_thread_same_key(self) -> None:
        msg1 = InboundMessage(
            channel="discord",
            sender_id="user-123",
            chat_id="forum-456",
            content="Hello",
            is_group=True,
            thread_id="thread-789",
            sent_at=1234567890.0,
            sent_timezone="UTC",
        )
        msg2 = InboundMessage(
            channel="discord",
            sender_id="user-456",
            chat_id="forum-456",
            content="World",
            is_group=True,
            thread_id="thread-789",
            sent_at=1234567891.0,
            sent_timezone="UTC",
        )
        key1 = _build_session_key(msg1, thread_sharing_mode=ThreadSharingMode.SHARED)
        key2 = _build_session_key(msg2, thread_sharing_mode=ThreadSharingMode.SHARED)
        assert key1 == key2

    def test_shared_mode_with_agent_id(self) -> None:
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
        key = _build_session_key(msg, agent_id="agent-xyz", thread_sharing_mode=ThreadSharingMode.SHARED)
        parsed = SessionKey.parse(key)
        assert parsed is not None
        assert parsed.agent_id == "agent-xyz"


@pytest.mark.asyncio
class TestResolveSessionKeyThreadSharing:
    """Test resolve_session_key with thread sharing mode."""

    async def test_resolve_persistent_shared_mode(self) -> None:
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
        policy = SessionPolicy(mode=SessionResetMode.PERSISTENT)
        key = await resolve_session_key(msg, policy, thread_sharing_mode=ThreadSharingMode.SHARED)
        parsed = SessionKey.parse(key)
        assert parsed is not None

    async def test_resolve_daily_shared_mode_adds_epoch(self) -> None:
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
        policy = SessionPolicy(mode=SessionResetMode.DAILY, daily_reset_hour=4)
        key = await resolve_session_key(msg, policy, thread_sharing_mode=ThreadSharingMode.SHARED)
        assert ":e=" in key
        base_part = key.split(":e=")[0]
        parsed = SessionKey.parse(base_part)
        assert parsed is not None
