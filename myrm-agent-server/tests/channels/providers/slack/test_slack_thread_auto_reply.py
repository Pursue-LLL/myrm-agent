"""Unit tests for Slack thread auto-reply with ThreadTracker."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.providers.slack.channel import SlackChannel
from app.channels.types import OutboundMessage


class TestSlackThreadAutoReply:
    """Test Slack thread auto-reply functionality."""

    @pytest.mark.asyncio
    async def test_thread_auto_reply_after_bot_participation(self) -> None:
        """Test thread auto-reply when bot has participated."""
        channel = SlackChannel("xoxb-test", require_thread_mention=False)
        channel._bot_user_id = "BOT123"
        channel._api = MagicMock()
        channel._api.post_message = AsyncMock(return_value="1234.5678")

        # Bot sends a thread reply
        msg = OutboundMessage(
            channel="slack",
            user_id="U_USER",
            recipient_id="C123",
            content="Hello thread!",
            metadata={"thread_ts": "1234.0000"},
        )
        await channel.send(msg)

        # User replies without @mention
        event = {
            "user": "U123",
            "text": "Follow-up question",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1234.9999",
            "thread_ts": "1234.0000",
        }

        inbound = await channel._parse_message_event(event)

        assert inbound is not None
        assert inbound.mentioned is True  # Auto-replied without @mention

    @pytest.mark.asyncio
    async def test_no_auto_reply_when_bot_not_participated(self) -> None:
        """Test no auto-reply when bot hasn't participated in thread."""
        channel = SlackChannel("xoxb-test", require_thread_mention=False)
        channel._bot_user_id = "BOT123"

        # User starts a thread without @mention
        event = {
            "user": "U123",
            "text": "Follow-up question",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1234.9999",
            "thread_ts": "1234.0000",
        }

        inbound = await channel._parse_message_event(event)

        assert inbound is not None
        assert inbound.mentioned is False  # No auto-reply

    @pytest.mark.asyncio
    async def test_require_thread_mention_disables_auto_reply(self) -> None:
        """Test require_thread_mention=True disables auto-reply."""
        channel = SlackChannel("xoxb-test", require_thread_mention=True)
        channel._bot_user_id = "BOT123"
        channel._api = MagicMock()
        channel._api.post_message = AsyncMock(return_value="1234.5678")

        # Bot participates in thread
        msg = OutboundMessage(
            channel="slack",
            user_id="U_USER",
            recipient_id="C123",
            content="Hello thread!",
            metadata={"thread_ts": "1234.0000"},
        )
        await channel.send(msg)

        # User replies without @mention
        event = {
            "user": "U123",
            "text": "Follow-up question",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1234.9999",
            "thread_ts": "1234.0000",
        }

        inbound = await channel._parse_message_event(event)

        assert inbound is not None
        assert inbound.mentioned is False  # Auto-reply disabled

    @pytest.mark.asyncio
    async def test_explicit_mention_always_works(self) -> None:
        """Test explicit @mention always triggers response."""
        channel = SlackChannel("xoxb-test", require_thread_mention=True)
        channel._bot_user_id = "BOT123"

        # User @mentions bot in thread
        event = {
            "user": "U123",
            "text": "<@BOT123> Follow-up question",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1234.9999",
            "thread_ts": "1234.0000",
        }

        inbound = await channel._parse_message_event(event)

        assert inbound is not None
        assert inbound.mentioned is True


class TestSlackThreadTrackerMetrics:
    """Test SlackChannel thread_tracker_metrics property."""

    @pytest.mark.asyncio
    async def test_metrics_property(self) -> None:
        """Test thread_tracker_metrics property exposes metrics."""
        channel = SlackChannel("xoxb-test")

        metrics = channel.thread_tracker_metrics

        assert metrics.hit_count == 0
        assert metrics.miss_count == 0
        assert metrics.current_size == 0

    @pytest.mark.asyncio
    async def test_metrics_update_after_operations(self) -> None:
        """Test metrics update after thread operations."""
        channel = SlackChannel("xoxb-test", require_thread_mention=False)
        channel._bot_user_id = "BOT123"
        channel._api = MagicMock()
        channel._api.post_message = AsyncMock(return_value="1234.5678")

        # Bot sends thread reply
        msg = OutboundMessage(
            channel="slack",
            user_id="U_USER",
            recipient_id="C123",
            content="Hello!",
            metadata={"thread_ts": "1234.0000"},
        )
        await channel.send(msg)

        # Parse event (triggers contains check)
        event = {
            "user": "U123",
            "text": "Reply",
            "channel": "C123",
            "channel_type": "channel",
            "ts": "1234.9999",
            "thread_ts": "1234.0000",
        }
        await channel._parse_message_event(event)

        metrics = channel.thread_tracker_metrics

        assert metrics.hit_count == 1
        assert metrics.current_size == 1
