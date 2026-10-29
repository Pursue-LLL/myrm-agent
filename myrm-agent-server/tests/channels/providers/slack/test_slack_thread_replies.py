"""SlackChannel thread auto-reply: which messages in a bot-started thread are answered without a mention."""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, patch

import pytest

from tests.channels.providers.slack.support import make_channel, ok_json


class TestSlackThreadAutoReply:
    """Tests for thread auto-reply (Task #60) — replies without @mention."""

    @pytest.mark.asyncio
    async def test_thread_reply_bot_initiated_no_mention(self) -> None:
        """Thread initiated by bot → replies auto-respond without @mention."""
        ch = make_channel()

        # Mock _fetch_thread_parent to return bot as sender
        parent_resp = ok_json(
            {
                "messages": [
                    {
                        "user": "U_BOT",
                        "text": "Bot started this thread",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=parent_resp):
            event: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply without mention",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            msg = await ch._parse_message_event(event)

        assert msg is not None
        assert msg.mentioned is True  # Auto-reply enabled
        assert msg.content == "reply without mention"

    @pytest.mark.asyncio
    async def test_thread_reply_parent_has_mention_no_current_mention(self) -> None:
        """Parent has @mention → replies auto-respond without @mention."""
        ch = make_channel()

        parent_resp = ok_json(
            {
                "messages": [
                    {
                        "user": "U_USER",
                        "text": "<@U_BOT> please help",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=parent_resp):
            event: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "follow up question",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0002",
                "thread_ts": "1111.0000",
            }
            msg = await ch._parse_message_event(event)

        assert msg is not None
        assert msg.mentioned is True
        assert msg.content == "follow up question"

    @pytest.mark.asyncio
    async def test_thread_reply_unrelated_thread_requires_mention(self) -> None:
        """Unrelated thread (not bot-initiated, no parent @mention) → requires @mention."""
        ch = make_channel()

        parent_resp = ok_json(
            {
                "messages": [
                    {
                        "user": "U_OTHER",
                        "text": "unrelated topic",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=parent_resp):
            event: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply without mention",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0003",
                "thread_ts": "1111.0000",
            }
            msg = await ch._parse_message_event(event)

        assert msg is not None
        assert msg.mentioned is False  # No auto-reply

    @pytest.mark.asyncio
    async def test_thread_reply_cache_hit(self) -> None:
        """LRU Cache: Second call should not trigger API request."""
        ch = make_channel()

        parent_resp = ok_json(
            {
                "messages": [
                    {
                        "user": "U_BOT",
                        "text": "Bot started",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        mock_post = AsyncMock(return_value=parent_resp)
        with patch.object(ch._api._http, "post", mock_post):
            # First call: API request
            event1: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 1",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            msg1 = await ch._parse_message_event(event1)
            assert msg1 is not None
            assert msg1.mentioned is True

            # Second call: Cache hit (no API request)
            event2: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 2",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0002",
                "thread_ts": "1111.0000",
            }
            msg2 = await ch._parse_message_event(event2)
            assert msg2 is not None
            assert msg2.mentioned is True

        # Verify 3 API calls
        # First event: 1 conversations.history + 2 users.info (U_USER sender + U_BOT parent) = 3 calls
        # Second event: all cached = 0 calls
        # Total: 3 calls
        assert mock_post.call_count == 3

    @pytest.mark.asyncio
    async def test_thread_reply_cache_ttl_expired(self) -> None:
        """LRU Cache: Expired cache should trigger new API request."""
        ch = make_channel()
        ch._cache_ttl = 0.1  # 100ms TTL for test

        parent_resp = ok_json(
            {
                "messages": [
                    {
                        "user": "U_BOT",
                        "text": "Bot started",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        mock_post = AsyncMock(return_value=parent_resp)
        with patch.object(ch._api._http, "post", mock_post):
            event1: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 1",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            await ch._parse_message_event(event1)

            # Wait for TTL expiration
            await asyncio.sleep(0.15)

            event2: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 2",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0002",
                "thread_ts": "1111.0000",
            }
            await ch._parse_message_event(event2)

        # Verify 4 API calls
        # First event: 1 conversations.history + 2 users.info (U_USER sender + U_BOT parent) = 3 calls
        # Second event (after TTL): 1 conversations.history (expired) + 0 users.info (still valid, 1h TTL) = 1 call
        # Total: 4 calls
        assert mock_post.call_count == 4

    @pytest.mark.asyncio
    async def test_thread_reply_lru_eviction(self) -> None:
        """LRU Cache: Oldest entry should be evicted when cache exceeds max size."""
        ch = make_channel()
        ch._cache_max_size = 2

        parent_resp = ok_json(
            {
                "messages": [
                    {
                        "user": "U_BOT",
                        "text": "Bot message",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        with patch.object(ch._api._http, "post", new_callable=AsyncMock, return_value=parent_resp):
            # Add 3 entries (exceeds max_size=2)
            for i in range(3):
                event: dict[str, object] = {
                    "type": "message",
                    "user": "U_USER",
                    "text": f"reply {i}",
                    "channel": "C_CHAN",
                    "channel_type": "channel",
                    "ts": f"{2222 + i}.0001",
                    "thread_ts": f"{1111 + i}.0000",
                }
                await ch._parse_message_event(event)

        # Verify cache size does not exceed max_size
        assert len(ch._thread_parent_cache) <= ch._cache_max_size

    @pytest.mark.asyncio
    async def test_thread_reply_cache_none_result(self) -> None:
        """Cache should also store None results (failed API calls)."""
        ch = make_channel()

        parent_resp = ok_json({"messages": []})  # Empty messages (parent not found)

        mock_post = AsyncMock(return_value=parent_resp)
        with patch.object(ch._api._http, "post", mock_post):
            # First call: API request returns None
            event1: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 1",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            msg1 = await ch._parse_message_event(event1)
            assert msg1 is not None
            assert msg1.mentioned is False  # No parent found

            # Second call: Cache hit (no API request)
            event2: dict[str, object] = {
                "type": "message",
                "user": "U_USER",
                "text": "reply 2",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0002",
                "thread_ts": "1111.0000",
            }
            msg2 = await ch._parse_message_event(event2)
            assert msg2 is not None
            assert msg2.mentioned is False

        # Verify 2 API calls (conversations.history + users.info for U_USER sender)
        # Second event: both cached = 0 calls
        assert mock_post.call_count == 2

    @pytest.mark.asyncio
    async def test_thread_reply_sender_name_resolved(self) -> None:
        """Thread parent sender_name should be resolved via UserResolver."""
        ch = make_channel()

        # Mock conversations.history response (parent message)
        parent_resp = ok_json(
            {
                "messages": [
                    {
                        "user": "U_PARENT",
                        "text": "Parent message",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        # Mock users.info response (parent sender name)
        user_resp = ok_json(
            {
                "user": {
                    "id": "U_PARENT",
                    "profile": {
                        "display_name": "Parent User",
                        "real_name": "Parent Real Name",
                    },
                }
            }
        )

        # Mock API: first call (conversations.history), second call (users.info)
        mock_post = AsyncMock(side_effect=[parent_resp, user_resp])

        with patch.object(ch._api._http, "post", mock_post):
            event: dict[str, object] = {
                "type": "message",
                "user": "U_REPLY",
                "text": "Reply to thread",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            msg = await ch._parse_message_event(event)

            # Verify InboundMessage has reply_to with sender_name
            assert msg is not None
            assert msg.reply_to is not None
            assert msg.reply_to.message_id == "1111.0000"
            assert msg.reply_to.content == "Parent message"
            assert msg.reply_to.sender_id == "U_PARENT"
            assert msg.reply_to.sender_name == "Parent User"  # Resolved via UserResolver!

        # Verify 3 API calls: conversations.history + users.info (U_PARENT) + users.info (U_REPLY sender)
        assert mock_post.call_count == 3

    @pytest.mark.asyncio
    async def test_thread_reply_sender_name_none_on_api_failure(self) -> None:
        """Thread parent sender_name should be None if API resolution fails."""
        ch = make_channel()

        # Mock conversations.history response (parent message)
        parent_resp = ok_json(
            {
                "messages": [
                    {
                        "user": "U_PARENT",
                        "text": "Parent message",
                        "ts": "1111.0000",
                    }
                ]
            }
        )

        # Mock users.info response (API failure)
        user_resp = ok_json({"ok": False, "error": "user_not_found"})

        # Mock API: first call (conversations.history), second call (users.info fails)
        mock_post = AsyncMock(side_effect=[parent_resp, user_resp])

        with patch.object(ch._api._http, "post", mock_post):
            event: dict[str, object] = {
                "type": "message",
                "user": "U_REPLY",
                "text": "Reply to thread",
                "channel": "C_CHAN",
                "channel_type": "channel",
                "ts": "2222.0001",
                "thread_ts": "1111.0000",
            }
            msg = await ch._parse_message_event(event)

            # Verify InboundMessage has reply_to with sender_name=None (API failed)
            assert msg is not None
            assert msg.reply_to is not None
            assert msg.reply_to.message_id == "1111.0000"
            assert msg.reply_to.content == "Parent message"
            assert msg.reply_to.sender_id == "U_PARENT"
            assert msg.reply_to.sender_name is None  # API failed, no name available

        # Verify 3 API calls: conversations.history + users.info (U_PARENT, failed) + users.info (U_REPLY sender)
        assert mock_post.call_count == 3
