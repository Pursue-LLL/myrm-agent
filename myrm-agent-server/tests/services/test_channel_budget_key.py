"""The channel budget key of a group is the session key of the group, however the policy key was typed.

A policy is looked up by the key of the live message, and its spend is recovered from the chats stored under the session
key. Both only match the canonical key, so a key typed with capitals, spaces or a punctuated chat id has to be brought
to it, and a key that no group can produce must not become a policy that never applies.
"""

from __future__ import annotations

import logging
from collections.abc import Callable

import pytest
from pydantic import ValidationError

from app.channels.types import SessionKey
from app.services.budget.channel_budget import ChannelBudgetPoliciesConfig, ChannelBudgetPolicy
from app.services.budget.channel_budget_key import (
    group_budget_key,
    normalize_channel_budget_key,
    parse_channel_budget_key,
)
from tests.support.channel_budget_fixtures import GROUP_IDS

_SPELLINGS: dict[str, Callable[[str, str], str]] = {
    "as delivered": lambda channel, peer: f"{channel}:group:{peer}",
    "channel in capitals": lambda channel, peer: f"{channel.upper()}:group:{peer}",
    "padded with spaces": lambda channel, peer: f"  {channel}:group:{peer} ",
    "lowercased by hand": lambda channel, peer: f"{channel}:group:{peer}".lower(),
}


@pytest.mark.parametrize(("channel", "peer"), GROUP_IDS)
class TestKeyOfAGroup:
    def test_it_is_the_session_key_of_the_group(self, channel: str, peer: str) -> None:
        assert group_budget_key(channel, peer) == SessionKey(channel, "group", peer).to_str()

    @pytest.mark.parametrize("spelling", _SPELLINGS)
    def test_every_spelling_of_the_key_is_brought_to_it(self, channel: str, peer: str, spelling: str) -> None:
        typed = _SPELLINGS[spelling](channel, peer)

        assert normalize_channel_budget_key(typed) == group_budget_key(channel, peer)
        assert parse_channel_budget_key(typed) == group_budget_key(channel, peer)

    def test_normalising_twice_changes_nothing(self, channel: str, peer: str) -> None:
        once = normalize_channel_budget_key(f"{channel}:group:{peer}")

        assert normalize_channel_budget_key(once) == once


class TestKeyThatNamesNoGroup:
    @pytest.mark.parametrize("raw", ["", "  ", "ch", "ch:ok", "  Slack:Group "])
    def test_it_is_only_trimmed_and_lowercased(self, raw: str) -> None:
        assert normalize_channel_budget_key(raw) == raw.strip().lower()

    @pytest.mark.parametrize("raw", ["", "foo", "slack:dm:u1", "slack:group:", ":group:c1", "slack:group:   ", "slack: group:c1"])
    def test_a_typed_one_is_rejected_in_english(self, raw: str) -> None:
        with pytest.raises(ValueError, match=r"<channel>:group:<chat id>"):
            parse_channel_budget_key(raw)


class TestPolicyKey:
    def test_it_is_canonical(self) -> None:
        assert ChannelBudgetPolicy(channel_key="  Slack:group:C024BE91L ").channel_key == "slack:group:c024be91l"

    def test_a_legacy_key_of_a_punctuated_id_reaches_the_key_of_live_messages(self) -> None:
        legacy = "matrix:group:!abcdef:matrix.org"

        assert ChannelBudgetPolicy(channel_key=legacy).channel_key == group_budget_key("matrix", "!AbCdEf:matrix.org")

    def test_a_key_that_is_not_text_is_still_a_validation_error(self) -> None:
        with pytest.raises(ValidationError):
            ChannelBudgetPolicy.model_validate({"channel_key": 123})


def _policies(*entries: tuple[str, float, bool]) -> ChannelBudgetPoliciesConfig:
    return ChannelBudgetPoliciesConfig.model_validate(
        {"policies": [{"channel_key": key, "daily_limit_usd": limit, "enabled": enabled} for key, limit, enabled in entries]}
    )


class TestPoliciesOfOneGroup:
    def test_the_stricter_one_is_kept_and_the_collision_is_logged(self, caplog: pytest.LogCaptureFixture) -> None:
        with caplog.at_level(logging.WARNING):
            config = _policies(("slack:group:C1", 5.0, True), ("Slack:group:c1 ", 1.0, True))

        assert [(p.channel_key, p.daily_limit_usd) for p in config.policies] == [("slack:group:c1", 1.0)]
        assert "collide on slack:group:c1" in caplog.text

    def test_an_enabled_policy_beats_a_disabled_one_with_a_lower_limit(self) -> None:
        config = _policies(("slack:group:c1", 1.0, False), ("Slack:group:C1", 5.0, True))

        assert [(p.daily_limit_usd, p.enabled) for p in config.policies] == [(5.0, True)]

    def test_the_first_one_wins_a_tie(self) -> None:
        config = ChannelBudgetPoliciesConfig.model_validate(
            {
                "policies": [
                    {"channel_key": "slack:group:c1", "daily_limit_usd": 2.0, "label": "first"},
                    {"channel_key": "SLACK:GROUP:C1", "daily_limit_usd": 2.0, "label": "second"},
                ]
            }
        )

        assert [p.label for p in config.policies] == ["first"]

    def test_policies_of_different_groups_are_all_kept_in_order(self) -> None:
        config = _policies(("slack:group:c2", 1.0, True), ("telegram:group:g-1", 2.0, True), ("slack:group:c1", 3.0, True))

        assert [p.channel_key for p in config.policies] == ["slack:group:c2", "telegram:group:g-1", "slack:group:c1"]
