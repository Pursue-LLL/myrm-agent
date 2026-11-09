"""PolicyResolver tests — group policy: enablement, guest mode, mention and trigger modes."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.protocols.pairing import (
    GroupPolicy,
    GroupTriggerMode,
)
from app.channels.types import METADATA_EXPLICIT_MENTION_KEY
from tests.channels.policy_resolver_testkit import make_message, make_resolver


class TestResolveGroupUser:
    @pytest.mark.asyncio
    async def test_pre_resolved_group_user_bypasses_policy_checks(self) -> None:
        policy = MagicMock()
        r = make_resolver(policy=policy)

        result = await r.resolve_group_user(
            make_message(
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
        r = make_resolver(policy=policy)
        result = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1"))
        assert result is None

    @pytest.mark.asyncio
    async def test_group_not_enabled(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-other"})
        policy.get_guest_mode = AsyncMock(return_value=False)
        r = make_resolver(policy=policy)
        result = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1"))
        assert result is None

    @pytest.mark.asyncio
    async def test_guest_mention_in_non_enabled_group(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-other"})
        policy.get_guest_mode = AsyncMock(return_value=True)
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.MENTION_ONLY, []))
        policy.get_default_user_id = AsyncMock(return_value="default-uid")
        r = make_resolver(policy=policy)
        result = await r.resolve_group_user(
            make_message(
                is_group=True,
                chat_id="grp-guest",
                mentioned=True,
                thread_id="t1",
                metadata={METADATA_EXPLICIT_MENTION_KEY: "1"},
            ),
        )
        assert result is not None
        assert result[0] == "guest_test_u1"
        assert result[1].metadata.get("guest_turn") == "1"
        assert r._tracker.is_active("test:grp-guest:t1")

    @pytest.mark.asyncio
    async def test_guest_requires_explicit_mention(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value=set())
        policy.get_guest_mode = AsyncMock(return_value=True)
        r = make_resolver(policy=policy)
        result = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-guest", mentioned=False))
        assert result is None

    @pytest.mark.asyncio
    async def test_guest_rejects_reply_only_without_explicit_mention(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value=set())
        policy.get_guest_mode = AsyncMock(return_value=True)
        r = make_resolver(policy=policy)
        result = await r.resolve_group_user(
            make_message(is_group=True, chat_id="grp-guest", mentioned=True, content="follow up"),
        )
        assert result is None

    @pytest.mark.asyncio
    async def test_mentioned_triggers(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.MENTION_ONLY, []))
        policy.get_default_user_id = AsyncMock(return_value="default-uid")
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value="default-uid")
        r = make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1", mentioned=True))
        assert result is not None
        assert result[0] == "default-uid"

    @pytest.mark.asyncio
    async def test_unpaired_sender_in_enabled_group_is_guest(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.MENTION_ONLY, []))
        policy.get_default_user_id = AsyncMock(return_value="default-uid")
        r = make_resolver(policy=policy)
        result = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1", mentioned=True))
        assert result is not None
        assert result[0] == "guest_test_u1"
        assert result[1].metadata.get("guest_turn") == "1"

    @pytest.mark.asyncio
    async def test_not_mentioned_buffers(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.MENTION_ONLY, []))
        r = make_resolver(policy=policy)
        result = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1", mentioned=False))
        assert result is None

    @pytest.mark.asyncio
    async def test_all_trigger_mode(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.ALL, []))
        policy.get_default_user_id = AsyncMock(return_value="uid")
        r = make_resolver(policy=policy)
        result = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1"))
        assert result is not None

    @pytest.mark.asyncio
    async def test_prefix_trigger_mode(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.PREFIX, ["/bot"]))
        policy.get_default_user_id = AsyncMock(return_value="uid")
        r = make_resolver(policy=policy)
        result = await r.resolve_group_user(make_message(content="/bot hello", is_group=True, chat_id="grp-1"))
        assert result is not None
        assert result[1].content == "hello"

    @pytest.mark.asyncio
    async def test_prefix_no_match(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.PREFIX, ["/bot"]))
        r = make_resolver(policy=policy)
        result = await r.resolve_group_user(make_message(content="hello", is_group=True, chat_id="grp-1"))
        assert result is None

    @pytest.mark.asyncio
    async def test_no_default_user_returns_none(self) -> None:
        policy = MagicMock()
        policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        policy.get_enabled_groups = AsyncMock(return_value={"grp-1"})
        policy.get_group_trigger = AsyncMock(return_value=(GroupTriggerMode.ALL, []))
        policy.get_default_user_id = AsyncMock(return_value=None)
        r = make_resolver(policy=policy)
        result = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1"))
        assert result is None

    @pytest.mark.asyncio
    async def test_no_policy_defaults_disabled(self) -> None:
        r = make_resolver(policy=None)
        result = await r.resolve_group_user(make_message(is_group=True, chat_id="grp-1"))
        assert result is None
