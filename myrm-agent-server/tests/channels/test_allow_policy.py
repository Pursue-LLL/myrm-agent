"""Tests for AllowPolicy access control."""

from __future__ import annotations

from app.channels.core.allow_policy import (
    OPEN_POLICY,
    SELECTIVE_POLICY,
    STRICT_POLICY,
    AllowPolicy,
    ChatPolicy,
    ChatPolicyOverride,
    FilterReason,
)
from app.channels.types import InboundMessage


def _msg(
    sender_id: str = "user1",
    is_group: bool = False,
    is_bot: bool = False,
    mentioned: bool = False,
    chat_id: str = "c1",
) -> InboundMessage:
    return InboundMessage(
        channel="test",
        sender_id=sender_id,
        content="hi",
        chat_id=chat_id,
        is_group=is_group,
        is_bot=is_bot,
        mentioned=mentioned,
    )


def _allowed(policy: AllowPolicy, msg: InboundMessage) -> bool:
    return policy.evaluate(msg) is None


class TestDenylist:
    def test_denylisted_sender_blocked(self) -> None:
        policy = AllowPolicy(denylist=frozenset({"bad"}))
        reason = policy.evaluate(_msg(sender_id="bad"))
        assert reason == FilterReason.DENYLISTED

    def test_non_denylisted_sender_allowed(self) -> None:
        policy = AllowPolicy(denylist=frozenset({"bad"}))
        assert _allowed(policy, _msg(sender_id="good"))

    def test_denylist_takes_priority_over_allowlist(self) -> None:
        policy = AllowPolicy(
            allowlist=frozenset({"user1"}),
            denylist=frozenset({"user1"}),
        )
        assert policy.evaluate(_msg(sender_id="user1")) == FilterReason.DENYLISTED

    def test_denylisted_bot_still_blocked(self) -> None:
        policy = AllowPolicy(
            denylist=frozenset({"bot1"}),
            bot_policy=ChatPolicy.ALLOW,
        )
        assert policy.evaluate(_msg(sender_id="bot1", is_bot=True)) == FilterReason.DENYLISTED

    def test_denylisted_overrides_chat_override(self) -> None:
        """Denylist takes priority even when chat override would allow."""
        policy = AllowPolicy(
            denylist=frozenset({"bad"}),
            chat_overrides={"c1": ChatPolicyOverride(bot_policy=ChatPolicy.ALLOW)},
        )
        assert policy.evaluate(_msg(sender_id="bad", is_bot=True)) == FilterReason.DENYLISTED

    def test_empty_denylist_blocks_nobody(self) -> None:
        policy = AllowPolicy(denylist=frozenset())
        assert _allowed(policy, _msg(sender_id="anyone"))

    def test_multiple_denylisted_senders(self) -> None:
        policy = AllowPolicy(denylist=frozenset({"a", "b", "c"}))
        assert policy.evaluate(_msg(sender_id="a")) == FilterReason.DENYLISTED
        assert policy.evaluate(_msg(sender_id="b")) == FilterReason.DENYLISTED
        assert policy.evaluate(_msg(sender_id="c")) == FilterReason.DENYLISTED
        assert _allowed(policy, _msg(sender_id="d"))


class TestAllowlist:
    def test_empty_allowlist_allows_all(self) -> None:
        policy = AllowPolicy(allowlist=frozenset())
        assert _allowed(policy, _msg(sender_id="anyone"))

    def test_allowlisted_sender_passes(self) -> None:
        policy = AllowPolicy(allowlist=frozenset({"vip"}))
        assert _allowed(policy, _msg(sender_id="vip"))

    def test_unlisted_sender_blocked(self) -> None:
        policy = AllowPolicy(allowlist=frozenset({"vip"}))
        assert policy.evaluate(_msg(sender_id="random")) == FilterReason.NOT_ALLOWLISTED

    def test_allowlist_only_applies_to_humans(self) -> None:
        """Bots bypass allowlist entirely — bot_policy governs them."""
        policy = AllowPolicy(
            allowlist=frozenset({"human_only"}),
            bot_policy=ChatPolicy.ALLOW,
        )
        assert _allowed(policy, _msg(sender_id="bot_x", is_bot=True))
        assert policy.evaluate(_msg(sender_id="bot_x", is_bot=False)) == FilterReason.NOT_ALLOWLISTED

    def test_allowlist_with_group_message(self) -> None:
        policy = AllowPolicy(
            allowlist=frozenset({"vip"}),
            group_policy=ChatPolicy.ALLOW,
        )
        assert _allowed(policy, _msg(sender_id="vip", is_group=True))
        assert policy.evaluate(_msg(sender_id="outsider", is_group=True)) == FilterReason.NOT_ALLOWLISTED


class TestChatPolicy:
    def test_dm_allow(self) -> None:
        policy = AllowPolicy(dm_policy=ChatPolicy.ALLOW)
        assert _allowed(policy, _msg(is_group=False))

    def test_dm_deny(self) -> None:
        policy = AllowPolicy(dm_policy=ChatPolicy.DENY)
        assert policy.evaluate(_msg(is_group=False)) == FilterReason.CHAT_DENIED

    def test_dm_mention_only_without_mention(self) -> None:
        policy = AllowPolicy(dm_policy=ChatPolicy.MENTION_ONLY)
        assert policy.evaluate(_msg(is_group=False, mentioned=False)) == FilterReason.CHAT_NOT_MENTIONED

    def test_dm_mention_only_with_mention(self) -> None:
        policy = AllowPolicy(dm_policy=ChatPolicy.MENTION_ONLY)
        assert _allowed(policy, _msg(is_group=False, mentioned=True))

    def test_group_default_mention_only(self) -> None:
        policy = AllowPolicy()
        assert policy.evaluate(_msg(is_group=True, mentioned=False)) == FilterReason.CHAT_NOT_MENTIONED
        assert _allowed(policy, _msg(is_group=True, mentioned=True))

    def test_group_allow(self) -> None:
        policy = AllowPolicy(group_policy=ChatPolicy.ALLOW)
        assert _allowed(policy, _msg(is_group=True, mentioned=False))

    def test_group_deny(self) -> None:
        policy = AllowPolicy(group_policy=ChatPolicy.DENY)
        assert policy.evaluate(_msg(is_group=True, mentioned=True)) == FilterReason.CHAT_DENIED


class TestBotPolicy:
    def test_default_bot_policy_denies(self) -> None:
        policy = AllowPolicy()
        assert policy.evaluate(_msg(is_bot=True)) == FilterReason.BOT_DENIED

    def test_bot_policy_allow(self) -> None:
        policy = AllowPolicy(bot_policy=ChatPolicy.ALLOW)
        assert _allowed(policy, _msg(is_bot=True))

    def test_bot_policy_mention_only_without_mention(self) -> None:
        policy = AllowPolicy(bot_policy=ChatPolicy.MENTION_ONLY)
        assert policy.evaluate(_msg(is_bot=True, mentioned=False)) == FilterReason.BOT_NOT_MENTIONED

    def test_bot_policy_mention_only_with_mention(self) -> None:
        policy = AllowPolicy(bot_policy=ChatPolicy.MENTION_ONLY)
        assert _allowed(policy, _msg(is_bot=True, mentioned=True))

    def test_bot_bypasses_allowlist(self) -> None:
        """Admitted bots bypass the human allowlist."""
        policy = AllowPolicy(
            allowlist=frozenset({"human_only"}),
            bot_policy=ChatPolicy.ALLOW,
        )
        assert _allowed(policy, _msg(sender_id="bot_peer", is_bot=True))

    def test_human_still_checked_by_allowlist(self) -> None:
        """Humans are still checked against the allowlist."""
        policy = AllowPolicy(
            allowlist=frozenset({"human_only"}),
            bot_policy=ChatPolicy.ALLOW,
        )
        assert policy.evaluate(_msg(sender_id="random_human")) == FilterReason.NOT_ALLOWLISTED

    def test_bot_in_group_uses_bot_policy_not_group_policy(self) -> None:
        """Bot messages use bot_policy regardless of group context."""
        policy = AllowPolicy(
            group_policy=ChatPolicy.ALLOW,
            bot_policy=ChatPolicy.DENY,
        )
        assert policy.evaluate(_msg(is_bot=True, is_group=True)) == FilterReason.BOT_DENIED

    def test_bot_in_dm_uses_bot_policy_not_dm_policy(self) -> None:
        """Bot messages use bot_policy regardless of DM context."""
        policy = AllowPolicy(
            dm_policy=ChatPolicy.ALLOW,
            bot_policy=ChatPolicy.DENY,
        )
        assert policy.evaluate(_msg(is_bot=True, is_group=False)) == FilterReason.BOT_DENIED

    def test_bot_allowed_in_group_with_mention(self) -> None:
        """Bot with mention_only policy passes when mentioned in group."""
        policy = AllowPolicy(
            group_policy=ChatPolicy.DENY,
            bot_policy=ChatPolicy.MENTION_ONLY,
        )
        assert _allowed(policy, _msg(is_bot=True, is_group=True, mentioned=True))

    def test_non_bot_not_affected_by_bot_policy(self) -> None:
        """Human senders go through normal allowlist + chat policy path."""
        policy = AllowPolicy(
            bot_policy=ChatPolicy.ALLOW,
            group_policy=ChatPolicy.DENY,
        )
        assert policy.evaluate(_msg(is_bot=False, is_group=True)) == FilterReason.CHAT_DENIED


class TestChatOverrides:
    def test_override_group_policy(self) -> None:
        policy = AllowPolicy(
            group_policy=ChatPolicy.MENTION_ONLY,
            chat_overrides={"quiet_group": ChatPolicyOverride(group_policy=ChatPolicy.DENY)},
        )
        assert policy.evaluate(_msg(is_group=True, mentioned=True, chat_id="quiet_group")) == FilterReason.CHAT_DENIED
        assert _allowed(policy, _msg(is_group=True, mentioned=True, chat_id="other_group"))

    def test_override_bot_policy(self) -> None:
        policy = AllowPolicy(
            bot_policy=ChatPolicy.DENY,
            chat_overrides={"bot_friendly": ChatPolicyOverride(bot_policy=ChatPolicy.ALLOW)},
        )
        assert _allowed(policy, _msg(is_bot=True, chat_id="bot_friendly"))
        assert policy.evaluate(_msg(is_bot=True, chat_id="strict_chat")) == FilterReason.BOT_DENIED

    def test_override_inherits_when_none(self) -> None:
        """Override with None values inherits from global policy."""
        policy = AllowPolicy(
            group_policy=ChatPolicy.ALLOW,
            chat_overrides={"partial": ChatPolicyOverride(bot_policy=ChatPolicy.ALLOW)},
        )
        assert _allowed(policy, _msg(is_group=True, chat_id="partial"))

    def test_override_with_both_fields_set(self) -> None:
        """Override with both group_policy and bot_policy set."""
        policy = AllowPolicy(
            group_policy=ChatPolicy.ALLOW,
            bot_policy=ChatPolicy.DENY,
            chat_overrides={
                "custom": ChatPolicyOverride(
                    group_policy=ChatPolicy.DENY,
                    bot_policy=ChatPolicy.ALLOW,
                ),
            },
        )
        assert policy.evaluate(_msg(is_group=True, chat_id="custom")) == FilterReason.CHAT_DENIED
        assert _allowed(policy, _msg(is_bot=True, chat_id="custom"))

    def test_no_override_for_missing_chat_id(self) -> None:
        """Messages with chat_id=None fall back to global policy."""
        policy = AllowPolicy(
            group_policy=ChatPolicy.ALLOW,
            chat_overrides={"c1": ChatPolicyOverride(group_policy=ChatPolicy.DENY)},
        )
        msg = InboundMessage(
            channel="test", sender_id="user1", content="hi",
            chat_id=None, is_group=True,
        )
        assert _allowed(policy, msg)

    def test_override_mention_only_bot(self) -> None:
        """Bot override to MENTION_ONLY requires mention."""
        policy = AllowPolicy(
            bot_policy=ChatPolicy.ALLOW,
            chat_overrides={"strict_bot_chat": ChatPolicyOverride(bot_policy=ChatPolicy.MENTION_ONLY)},
        )
        assert policy.evaluate(
            _msg(is_bot=True, chat_id="strict_bot_chat", mentioned=False)
        ) == FilterReason.BOT_NOT_MENTIONED
        assert _allowed(policy, _msg(is_bot=True, chat_id="strict_bot_chat", mentioned=True))

    def test_override_does_not_affect_dm_policy(self) -> None:
        """group_policy override does not affect DM messages."""
        policy = AllowPolicy(
            dm_policy=ChatPolicy.ALLOW,
            chat_overrides={"c1": ChatPolicyOverride(group_policy=ChatPolicy.DENY)},
        )
        assert _allowed(policy, _msg(is_group=False, chat_id="c1"))


class TestPresetPolicies:
    def test_open_policy_allows_dm(self) -> None:
        assert _allowed(OPEN_POLICY, _msg(is_group=False))

    def test_open_policy_allows_all_group_messages(self) -> None:
        assert _allowed(OPEN_POLICY, _msg(is_group=True, mentioned=False))
        assert _allowed(OPEN_POLICY, _msg(is_group=True, mentioned=True))

    def test_selective_policy_allows_dm(self) -> None:
        assert _allowed(SELECTIVE_POLICY, _msg(is_group=False))

    def test_selective_policy_group_requires_mention(self) -> None:
        assert not _allowed(SELECTIVE_POLICY, _msg(is_group=True, mentioned=False))
        assert _allowed(SELECTIVE_POLICY, _msg(is_group=True, mentioned=True))

    def test_strict_policy_dm_requires_mention(self) -> None:
        assert not _allowed(STRICT_POLICY, _msg(is_group=False, mentioned=False))
        assert _allowed(STRICT_POLICY, _msg(is_group=False, mentioned=True))

    def test_strict_policy_group_requires_mention(self) -> None:
        assert not _allowed(STRICT_POLICY, _msg(is_group=True, mentioned=False))
        assert _allowed(STRICT_POLICY, _msg(is_group=True, mentioned=True))


class TestFilterReason:
    def test_all_reasons_have_string_values(self) -> None:
        for reason in FilterReason:
            assert isinstance(reason.value, str)
            assert len(reason.value) > 0

    def test_all_reasons_are_unique(self) -> None:
        values = [r.value for r in FilterReason]
        assert len(values) == len(set(values))

    def test_expected_reason_count(self) -> None:
        assert len(FilterReason) == 6


class TestDefaultPolicyValues:
    """Verify AllowPolicy defaults are sane and match documentation."""

    def test_default_allowlist_empty(self) -> None:
        assert AllowPolicy().allowlist == frozenset()

    def test_default_denylist_empty(self) -> None:
        assert AllowPolicy().denylist == frozenset()

    def test_default_dm_policy_allow(self) -> None:
        assert AllowPolicy().dm_policy == ChatPolicy.ALLOW

    def test_default_group_policy_mention_only(self) -> None:
        assert AllowPolicy().group_policy == ChatPolicy.MENTION_ONLY

    def test_default_bot_policy_deny(self) -> None:
        assert AllowPolicy().bot_policy == ChatPolicy.DENY

    def test_default_chat_overrides_empty(self) -> None:
        assert AllowPolicy().chat_overrides == {}


class TestChatPolicyOverrideImmutability:
    """Verify ChatPolicyOverride frozen dataclass behavior."""

    def test_frozen_prevents_modification(self) -> None:
        override = ChatPolicyOverride(group_policy=ChatPolicy.ALLOW)
        try:
            override.group_policy = ChatPolicy.DENY  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass

    def test_default_none_values(self) -> None:
        override = ChatPolicyOverride()
        assert override.group_policy is None
        assert override.bot_policy is None


class TestAllowPolicyImmutability:
    """Verify AllowPolicy frozen dataclass behavior."""

    def test_frozen_prevents_modification(self) -> None:
        policy = AllowPolicy()
        try:
            policy.dm_policy = ChatPolicy.DENY  # type: ignore[misc]
            raise AssertionError("Should have raised FrozenInstanceError")
        except AttributeError:
            pass


class TestCombinationScenarios:
    """Complex multi-factor evaluation paths."""

    def test_denylist_plus_bot_plus_override(self) -> None:
        """Denylist wins even when override + bot_policy would allow."""
        policy = AllowPolicy(
            denylist=frozenset({"evil_bot"}),
            bot_policy=ChatPolicy.ALLOW,
            chat_overrides={"c1": ChatPolicyOverride(bot_policy=ChatPolicy.ALLOW)},
        )
        assert policy.evaluate(
            _msg(sender_id="evil_bot", is_bot=True, chat_id="c1")
        ) == FilterReason.DENYLISTED

    def test_allowlist_plus_group_deny(self) -> None:
        """Allowlisted human blocked by group DENY policy."""
        policy = AllowPolicy(
            allowlist=frozenset({"vip"}),
            group_policy=ChatPolicy.DENY,
        )
        assert policy.evaluate(
            _msg(sender_id="vip", is_group=True)
        ) == FilterReason.CHAT_DENIED

    def test_allowlist_plus_dm_allow(self) -> None:
        """Allowlisted human passes in DM with ALLOW policy."""
        policy = AllowPolicy(
            allowlist=frozenset({"vip"}),
            dm_policy=ChatPolicy.ALLOW,
        )
        assert _allowed(policy, _msg(sender_id="vip", is_group=False))

    def test_full_pipeline_human_dm_allowed(self) -> None:
        """Human DM: no denylist, no allowlist, dm_policy=ALLOW → pass."""
        policy = AllowPolicy()
        assert _allowed(policy, _msg(sender_id="user1", is_group=False))

    def test_full_pipeline_human_group_needs_mention(self) -> None:
        """Human group: no denylist, no allowlist, group_policy=MENTION_ONLY → needs mention."""
        policy = AllowPolicy()
        assert policy.evaluate(
            _msg(sender_id="user1", is_group=True, mentioned=False)
        ) == FilterReason.CHAT_NOT_MENTIONED
        assert _allowed(policy, _msg(sender_id="user1", is_group=True, mentioned=True))

    def test_full_pipeline_bot_default_denied(self) -> None:
        """Bot message with all defaults → denied."""
        policy = AllowPolicy()
        assert policy.evaluate(_msg(is_bot=True)) == FilterReason.BOT_DENIED

    def test_override_group_allow_with_global_mention_only(self) -> None:
        """Specific chat overrides group to ALLOW while global is MENTION_ONLY."""
        policy = AllowPolicy(
            group_policy=ChatPolicy.MENTION_ONLY,
            chat_overrides={"open_chat": ChatPolicyOverride(group_policy=ChatPolicy.ALLOW)},
        )
        assert _allowed(policy, _msg(is_group=True, chat_id="open_chat", mentioned=False))
        assert policy.evaluate(
            _msg(is_group=True, chat_id="other", mentioned=False)
        ) == FilterReason.CHAT_NOT_MENTIONED
