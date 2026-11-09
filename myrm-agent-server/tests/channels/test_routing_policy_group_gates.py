"""PolicyResolver tests — group follow-up exemption (thread, mute, free-response chats) and the bot-sender gate."""

from __future__ import annotations

import asyncio
from typing import cast
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.pairing import (
    DmPolicy,
    GroupPolicy,
    GroupTriggerMode,
)
from app.channels.routing.bot_loop_guard import BotLoopGuard
from app.channels.types import InboundMessage
from tests.channels.policy_resolver_testkit import make_message, make_resolver
from tests.support.fake_secrets import github_token


class TestGroupFollowUpExemption:
    @pytest.mark.asyncio
    async def test_tracker_lru_and_ttl(self) -> None:
        """Test GroupFollowUpTracker TTL expiration and LRU eviction limits."""
        import asyncio

        from app.channels.routing.policy_resolver_support import GroupFollowUpTracker

        # 1. Verify strict TTL expiration
        tracker = GroupFollowUpTracker(ttl_seconds=0.1, max_size=3)
        tracker.activate("key1")
        assert tracker.is_active("key1") is True
        await asyncio.sleep(0.15)
        assert tracker.is_active("key1") is False

        # 2. Verify LRU eviction of oldest active key
        tracker = GroupFollowUpTracker(ttl_seconds=100.0, max_size=3)
        tracker.activate("key1")
        await asyncio.sleep(0.01)
        tracker.activate("key2")
        await asyncio.sleep(0.01)
        tracker.activate("key3")
        assert len(tracker._active_threads) == 3

        tracker.activate("key4")
        assert len(tracker._active_threads) == 3
        # oldest 'key1' should be evicted
        assert tracker.is_active("key1") is False
        assert tracker.is_active("key2") is True
        assert tracker.is_active("key3") is True
        assert tracker.is_active("key4") is True

    @pytest.mark.asyncio
    async def test_thread_aware_exemption_and_mute(self) -> None:
        """Test thread-aware exempt-mention dynamics and mute command interception."""
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"chat-123"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.MENTION_ONLY, []))
        policy.get_default_user_id = AsyncMock(return_value="user1")
        policy.get_free_response_chats = AsyncMock(return_value=set())
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value="user1")

        r = make_resolver(pairing=pairing, policy=policy)

        # 1. In MENTION_ONLY mode, inbound messages without mention or active thread should be ignored
        msg1 = InboundMessage(channel="test", sender_id="u1", chat_id="chat-123", content="hello", is_group=True, mentioned=False)
        res1 = await r.resolve_group_user(msg1)
        assert res1 is None

        # 2. Explicit mention triggers the activation sequence
        msg2 = InboundMessage(
            channel="test",
            sender_id="u1",
            chat_id="chat-123",
            content="hello",
            is_group=True,
            mentioned=True,
            thread_id="thread-456",
        )
        res2 = await r.resolve_group_user(msg2)
        assert res2 is not None
        assert res2[0] == "user1"

        # 3. The thread is active now, so subsequent messages in the same thread are exempted
        msg3 = InboundMessage(
            channel="test",
            sender_id="u1",
            chat_id="chat-123",
            content="continue...",
            is_group=True,
            mentioned=False,
            thread_id="thread-456",
        )
        res3 = await r.resolve_group_user(msg3)
        assert res3 is not None
        assert res3[0] == "user1"

        # 4. Mute command deactivates the thread immediately
        msg4 = InboundMessage(
            channel="test",
            sender_id="u1",
            chat_id="chat-123",
            content="/mute",
            is_group=True,
            mentioned=False,
            thread_id="thread-456",
        )
        res4 = await r.resolve_group_user(msg4)
        assert res4 is None

        # 5. Verify the thread is muted and confirmation reply is sent
        assert r._tracker.is_active("test:chat-123:thread-456") is False
        cast(AsyncMock, r._fx.send_mute_reply).assert_called_once_with(msg4)

        msg5 = InboundMessage(
            channel="test",
            sender_id="u1",
            chat_id="chat-123",
            content="any follow-ups?",
            is_group=True,
            mentioned=False,
            thread_id="thread-456",
        )
        res5 = await r.resolve_group_user(msg5)
        assert res5 is None

    @pytest.mark.asyncio
    async def test_free_response_chats_whitelist(self) -> None:
        """Test group whitelist exemption using freeResponseChats."""
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"chat-123"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.MENTION_ONLY, []))
        policy.get_default_user_id = AsyncMock(return_value="user1")
        # Configure chat-123 in free response whitelist
        policy.get_free_response_chats = AsyncMock(return_value={"chat-123"})
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value="user1")

        r = make_resolver(pairing=pairing, policy=policy)

        msg = InboundMessage(channel="test", sender_id="u1", chat_id="chat-123", content="hello", is_group=True, mentioned=False)
        res = await r.resolve_group_user(msg)
        assert res is not None
        assert res[0] == "user1"


class TestBotSenderGate:
    """R1: bot-authored messages only trigger via explicit mention; BotLoopGuard caps loops.

    Co-resident bots (alert feeds, other AI agents) must not burn LLM turns in
    free-response groups, and two bots replying to each other must not loop.
    """

    @staticmethod
    def _group_policy(*, free_response: set[str] | None = None) -> MagicMock:
        # None → default whitelist; an explicitly passed set() must stay empty.
        # (set() is falsy, so `or` cannot distinguish it — hence the is-not-None check.)
        chats = free_response if free_response is not None else {"grp-1"}
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_free_response_chats = AsyncMock(return_value=chats)
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.MENTION_ONLY, []))
        policy.get_default_user_id = AsyncMock(return_value="default-uid")
        return policy

    @pytest.mark.asyncio
    async def test_bot_chatter_ignored_even_in_free_response_group(self) -> None:
        r = make_resolver(policy=self._group_policy())
        result = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1", mentioned=False, is_bot=True))
        assert result is None

    @pytest.mark.asyncio
    async def test_bot_explicit_mention_triggers(self) -> None:
        r = make_resolver(policy=self._group_policy())
        result = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1", mentioned=True, is_bot=True))
        assert result is not None

    @pytest.mark.asyncio
    async def test_bot_mention_blocked_after_guard_trips(self) -> None:
        r = make_resolver(policy=self._group_policy())
        r._bot_loop_guard = BotLoopGuard(max_events=1, window_seconds=300.0, cooldown_seconds=600.0)
        first = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1", mentioned=True, is_bot=True))
        assert first is not None
        second = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1", mentioned=True, is_bot=True))
        assert second is None

    @pytest.mark.asyncio
    async def test_human_mention_unaffected_by_guard(self) -> None:
        r = make_resolver(policy=self._group_policy())
        r._bot_loop_guard = BotLoopGuard(max_events=1, window_seconds=300.0, cooldown_seconds=600.0)
        first = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1", mentioned=True, is_bot=False))
        second = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1", mentioned=True, is_bot=False))
        assert first is not None
        assert second is not None

    @pytest.mark.asyncio
    async def test_bot_dm_dropped_after_guard_trips(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value="uid-1")
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.OPEN)
        r = make_resolver(pairing=pairing, policy=policy)
        r._bot_loop_guard = BotLoopGuard(max_events=1, window_seconds=300.0, cooldown_seconds=600.0)
        first = await r.resolve_dm_user(make_message(is_bot=True, chat_id="dm-1"))
        assert first == "uid-1"
        second = await r.resolve_dm_user(make_message(is_bot=True, chat_id="dm-1"))
        assert second is None

    @pytest.mark.asyncio
    async def test_bot_chatter_not_buffered_for_context(self) -> None:
        r = make_resolver(policy=self._group_policy(free_response=set()))
        await r.resolve_group_user(
            make_message(content="beep boop", is_group=True, chat_id="grp-1", mentioned=False, is_bot=True)
        )
        assert r._context_buffer.drain("grp-1") == ()
        await r.resolve_group_user(make_message(content="hello team", is_group=True, chat_id="grp-1", mentioned=False))
        buffered = r._context_buffer.drain("grp-1")
        assert len(buffered) == 1
        assert buffered[0].content == "hello team"

    @pytest.mark.asyncio
    async def test_buffered_chatter_has_credentials_masked(self) -> None:
        """The in-memory fallback reaches a later prompt like the ledger rows do, so it never keeps a raw credential."""
        token = github_token("a1B2c3D4e5F6g7H8i9J0k1L2m3N4o5P6q7R8")
        r = make_resolver(policy=self._group_policy(free_response=set()))
        with patch(
            "app.channels.routing.channel_data_plane.ChannelDataPlaneService.record_inbound",
            new=AsyncMock(),
        ):
            await r.resolve_group_user(
                make_message(content=f"my token {token} ok", is_group=True, chat_id="grp-1", mentioned=False)
            )
        buffered = r._context_buffer.drain("grp-1")
        assert len(buffered) == 1
        assert token[6:-4] not in buffered[0].content
        assert buffered[0].content.startswith("my token ")

    @pytest.mark.asyncio
    async def test_trigger_attribution_single_write(self) -> None:
        """R3 regression: trigger attribution recorded exactly once, at the resolver."""
        r = make_resolver(policy=self._group_policy(free_response=set()))
        with patch(
            "app.channels.routing.channel_data_plane.ChannelDataPlaneService.record_inbound",
            new=AsyncMock(),
        ) as mock_record:
            await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1", mentioned=False))
            await asyncio.sleep(0)
            mock_record.assert_called_once()
            assert mock_record.call_args.kwargs["is_trigger"] is False

            await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1", mentioned=True))
            await asyncio.sleep(0)
            assert mock_record.call_count == 2
            assert mock_record.call_args.kwargs["is_trigger"] is True
