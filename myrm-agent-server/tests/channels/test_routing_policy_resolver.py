"""PolicyResolver tests — DM/group policy, pairing, LID fallback."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.protocols.pairing import (
    DmPolicy,
    GroupPolicy,
    GroupTriggerMode,
    PairingStatus,
)
from app.channels.routing.context_buffer import GroupContextBuffer
from app.channels.routing.message_effects import MessageEffects
from app.channels.routing.policy_resolver import PolicyResolver
from app.channels.types import METADATA_EXPLICIT_MENTION_KEY, InboundMessage


def _msg(
    content: str = "hi",
    *,
    channel: str = "test",
    sender_id: str = "u1",
    chat_id: str = "",
    is_group: bool = False,
    mentioned: bool = False,
    user_id: str = "",
    metadata: dict[str, object] | None = None,
    thread_id: str = "",
) -> InboundMessage:
    return InboundMessage(
        channel=channel,
        sender_id=sender_id,
        content=content,
        chat_id=chat_id,
        is_group=is_group,
        mentioned=mentioned,
        user_id=user_id,
        metadata=metadata or {},
        thread_id=thread_id,
    )


def _make_resolver(
    *,
    pairing: MagicMock | None = None,
    policy: MagicMock | None = None,
    get_channel: MagicMock | None = None,
) -> PolicyResolver:
    if pairing is None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=None)
        pairing.bind = AsyncMock()

    fx = MagicMock(spec=MessageEffects)
    fx.send_pending_reply = AsyncMock()
    fx.send_pairing_request_reply = AsyncMock()
    fx.send_mute_reply = AsyncMock()

    if (
        policy is not None
        and isinstance(policy, MagicMock)
        and not isinstance(getattr(policy, "get_free_response_chats", None), AsyncMock)
    ):
        policy.get_free_response_chats = AsyncMock(return_value=set())
    if (
        policy is not None
        and isinstance(policy, MagicMock)
        and not isinstance(getattr(policy, "get_guest_mode", None), AsyncMock)
    ):
        policy.get_guest_mode = AsyncMock(return_value=False)
    if (
        policy is not None
        and isinstance(policy, MagicMock)
        and not isinstance(getattr(policy, "get_enabled_groups", None), AsyncMock)
    ):
        policy.get_enabled_groups = AsyncMock(return_value=set())

    return PolicyResolver(
        pairing=pairing,
        policy=policy,
        context_buffer=GroupContextBuffer(),
        fx=fx,
        get_channel=get_channel or MagicMock(return_value=None),
    )


class TestResolveDmUser:
    @pytest.mark.asyncio
    async def test_returns_existing_user_id(self) -> None:
        r = _make_resolver()
        msg = _msg(user_id="existing-uid")
        result = await r.resolve_dm_user(msg)
        assert result == "existing-uid"

    @pytest.mark.asyncio
    async def test_disabled_policy(self) -> None:
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.DISABLED)
        r = _make_resolver(policy=policy)
        result = await r.resolve_dm_user(_msg())
        assert result is None

    @pytest.mark.asyncio
    async def test_open_policy_resolves(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value="uid-1")
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.OPEN)
        r = _make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(_msg())
        assert result == "uid-1"

    @pytest.mark.asyncio
    async def test_open_policy_lid_fallback(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.bind = AsyncMock()
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.OPEN)
        policy.get_default_user_id = AsyncMock(return_value="default-uid")

        ch_mock = MagicMock()
        ch_mock._lid_to_pn = {}

        r = _make_resolver(
            pairing=pairing,
            policy=policy,
            get_channel=MagicMock(return_value=ch_mock),
        )
        result = await r.resolve_dm_user(_msg(sender_id="123@lid"))
        assert result == "default-uid"

    @pytest.mark.asyncio
    async def test_open_policy_default_fallback(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.OPEN)
        policy.get_default_user_id = AsyncMock(return_value="default-uid")
        r = _make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(_msg())
        assert result == "default-uid"

    @pytest.mark.asyncio
    async def test_open_policy_no_default(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.OPEN)
        policy.get_default_user_id = AsyncMock(return_value=None)
        r = _make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(_msg())
        assert result is None

    @pytest.mark.asyncio
    async def test_pairing_mode_resolves(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value="uid-1")
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.PAIRING)
        r = _make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(_msg())
        assert result == "uid-1"

    @pytest.mark.asyncio
    async def test_pairing_mode_blocked(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=PairingStatus.BLOCKED)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.PAIRING)
        r = _make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(_msg())
        assert result is None

    @pytest.mark.asyncio
    async def test_pairing_mode_pending(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=PairingStatus.PENDING)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.PAIRING)
        r = _make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(_msg())
        assert result is None
        r._fx.send_pending_reply.assert_called_once()

    @pytest.mark.asyncio
    async def test_pairing_mode_new_sender(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=None)
        pairing.bind = AsyncMock()
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.PAIRING)
        policy.get_default_user_id = AsyncMock(return_value="default")
        r = _make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(_msg())
        assert result is None
        pairing.bind.assert_called_once()
        r._fx.send_pairing_request_reply.assert_called_once()

    @pytest.mark.asyncio
    async def test_allowlist_mode_resolves(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value="uid-1")
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.ALLOWLIST)
        r = _make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(_msg())
        assert result == "uid-1"

    @pytest.mark.asyncio
    async def test_allowlist_mode_blocked(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=PairingStatus.BLOCKED)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.ALLOWLIST)
        r = _make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(_msg())
        assert result is None

    @pytest.mark.asyncio
    async def test_allowlist_mode_unpaired(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=None)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.ALLOWLIST)
        r = _make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(_msg())
        assert result is None

    @pytest.mark.asyncio
    async def test_no_policy_defaults_to_allowlist(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=None)
        r = _make_resolver(pairing=pairing, policy=None)
        result = await r.resolve_dm_user(_msg())
        assert result is None


class TestResolveGroupUser:
    @pytest.mark.asyncio
    async def test_pre_resolved_group_user_bypasses_policy_checks(self) -> None:
        policy = MagicMock()
        r = _make_resolver(policy=policy)

        result = await r.resolve_group_user(
            _msg(
                is_group=True,
                chat_id="grp-1",
                user_id="resolved-uid",
                metadata={"trusted_inbound": "control_plane"},
            )
        )

        assert result is not None
        assert result[0] == "resolved-uid"
        assert result[1].user_id == "resolved-uid"
        policy.get_group_policy.assert_not_called()

    @pytest.mark.asyncio
    async def test_disabled_policy(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.DISABLED)
        r = _make_resolver(policy=policy)
        result = await r.resolve_group_user(_msg(is_group=True, chat_id="grp-1"))
        assert result is None

    @pytest.mark.asyncio
    async def test_group_not_enabled(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-other"})
        policy.get_guest_mode = AsyncMock(return_value=False)
        r = _make_resolver(policy=policy)
        result = await r.resolve_group_user(_msg(is_group=True, chat_id="grp-1"))
        assert result is None

    @pytest.mark.asyncio
    async def test_guest_mention_in_non_enabled_group(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-other"})
        policy.get_guest_mode = AsyncMock(return_value=True)
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.MENTION_ONLY, []))
        policy.get_default_user_id = AsyncMock(return_value="default-uid")
        r = _make_resolver(policy=policy)
        result = await r.resolve_group_user(
            _msg(
                is_group=True,
                chat_id="grp-guest",
                mentioned=True,
                thread_id="t1",
                metadata={METADATA_EXPLICIT_MENTION_KEY: "1"},
            ),
        )
        assert result is not None
        assert result[0] == "default-uid"
        assert result[1].metadata.get("guest_turn") == "1"
        assert not r._tracker.is_active("test:grp-guest:t1")

    @pytest.mark.asyncio
    async def test_guest_requires_explicit_mention(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value=set())
        policy.get_guest_mode = AsyncMock(return_value=True)
        r = _make_resolver(policy=policy)
        result = await r.resolve_group_user(_msg(is_group=True, chat_id="grp-guest", mentioned=False))
        assert result is None

    @pytest.mark.asyncio
    async def test_guest_rejects_reply_only_without_explicit_mention(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value=set())
        policy.get_guest_mode = AsyncMock(return_value=True)
        r = _make_resolver(policy=policy)
        result = await r.resolve_group_user(
            _msg(is_group=True, chat_id="grp-guest", mentioned=True, content="follow up"),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_mentioned_triggers(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.MENTION_ONLY, []))
        policy.get_default_user_id = AsyncMock(return_value="default-uid")
        r = _make_resolver(policy=policy)
        result = await r.resolve_group_user(_msg(is_group=True, chat_id="grp-1", mentioned=True))
        assert result is not None
        assert result[0] == "default-uid"

    @pytest.mark.asyncio
    async def test_not_mentioned_buffers(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.MENTION_ONLY, []))
        r = _make_resolver(policy=policy)
        result = await r.resolve_group_user(_msg(is_group=True, chat_id="grp-1", mentioned=False))
        assert result is None

    @pytest.mark.asyncio
    async def test_all_trigger_mode(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.ALL, []))
        policy.get_default_user_id = AsyncMock(return_value="uid")
        r = _make_resolver(policy=policy)
        result = await r.resolve_group_user(_msg(is_group=True, chat_id="grp-1"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_prefix_trigger_mode(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.PREFIX, ["/bot"]))
        policy.get_default_user_id = AsyncMock(return_value="uid")
        r = _make_resolver(policy=policy)
        result = await r.resolve_group_user(_msg(content="/bot hello", is_group=True, chat_id="grp-1"))
        assert result is not None
        assert result[1].content == "hello"

    @pytest.mark.asyncio
    async def test_prefix_no_match(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.PREFIX, ["/bot"]))
        r = _make_resolver(policy=policy)
        result = await r.resolve_group_user(_msg(content="hello", is_group=True, chat_id="grp-1"))
        assert result is None

    @pytest.mark.asyncio
    async def test_no_default_user_returns_none(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.ALL, []))
        policy.get_default_user_id = AsyncMock(return_value=None)
        r = _make_resolver(policy=policy)
        result = await r.resolve_group_user(_msg(is_group=True, chat_id="grp-1"))
        assert result is None

    @pytest.mark.asyncio
    async def test_no_policy_defaults_disabled(self) -> None:
        r = _make_resolver(policy=None)
        result = await r.resolve_group_user(_msg(is_group=True, chat_id="grp-1"))
        assert result is None


class TestLidFallback:
    @pytest.mark.asyncio
    async def test_lid_resolved_via_cache(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(side_effect=[None, "uid-from-pn"])
        pairing.bind = AsyncMock()
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.OPEN)
        policy.get_default_user_id = AsyncMock(return_value=None)

        ch_mock = MagicMock()
        ch_mock._lid_to_pn = {"123@lid": "+1234567890"}

        r = _make_resolver(
            pairing=pairing,
            policy=policy,
            get_channel=MagicMock(return_value=ch_mock),
        )
        result = await r.resolve_dm_user(_msg(sender_id="123@lid"))
        assert result == "uid-from-pn"
        pairing.bind.assert_called_once()

    @pytest.mark.asyncio
    async def test_lid_cache_miss_no_default(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=None)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.ALLOWLIST)

        ch_mock = MagicMock()
        ch_mock._lid_to_pn = {"other@lid": "+999"}

        r = _make_resolver(
            pairing=pairing,
            policy=policy,
            get_channel=MagicMock(return_value=ch_mock),
        )
        result = await r.resolve_dm_user(_msg(sender_id="123@lid"))
        assert result is None


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

        r = _make_resolver(policy=policy)

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
        r._fx.send_mute_reply.assert_called_once_with(msg4)

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

        r = _make_resolver(policy=policy)

        msg = InboundMessage(channel="test", sender_id="u1", chat_id="chat-123", content="hello", is_group=True, mentioned=False)
        res = await r.resolve_group_user(msg)
        assert res is not None
        assert res[0] == "user1"
