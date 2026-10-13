"""Tests for the privacy settings read from the persisted personal settings."""

from __future__ import annotations

import pytest
from myrm_agent_harness.agent.security.types import PIIAction

from app.core.security.privacy_settings import (
    PrivacyAgentParams,
    privacy_agent_params,
    privacy_enabled,
    privacy_policy_from_settings,
    resolve_privacy_params,
)

_RULES = {
    "privacyCustomKeywordsS2": ["Project Falcon"],
    "privacyCustomKeywordsS3": ["vault-7"],
    "privacyCustomPatternsS2": [r"EMP-\d{6}"],
    "privacyCustomPatternsS3": [r"SEC-\d{4}"],
    "privacySensitiveToolsS2": ["browser"],
    "privacySensitiveToolsS3": ["bash"],
}


class TestPrivacyEnabled:
    @pytest.mark.parametrize("settings", [None, {}, {"privacyEnabled": False}, {"privacyEnabled": "true"}, {"privacyEnabled": 1}])
    def test_only_an_explicit_true_turns_protection_on(self, settings: dict[str, object] | None) -> None:
        assert privacy_enabled(settings) is False

    def test_true_turns_protection_on(self) -> None:
        assert privacy_enabled({"privacyEnabled": True}) is True


class TestPrivacyAgentParams:
    def test_nothing_is_supplied_while_protection_is_off(self) -> None:
        assert privacy_agent_params({"privacyEnabled": False, "privacyS3Action": "block"}) == {}
        assert privacy_agent_params(None) == {}

    def test_enabled_settings_carry_actions_deep_scan_and_custom_rules(self) -> None:
        params = privacy_agent_params(
            {
                "privacyEnabled": True,
                "privacyS2Action": "pseudonymize",
                "privacyS3Action": "block",
                "privacyDeepScan": True,
                **_RULES,
            }
        )

        assert params == {
            "privacy_enabled": True,
            "privacy_s2_action": "pseudonymize",
            "privacy_s3_action": "block",
            "privacy_deep_scan": True,
            "privacy_custom_keywords_s2": ["Project Falcon"],
            "privacy_custom_keywords_s3": ["vault-7"],
            "privacy_custom_patterns_s2": [r"EMP-\d{6}"],
            "privacy_custom_patterns_s3": [r"SEC-\d{4}"],
            "privacy_sensitive_tools_s2": ["browser"],
            "privacy_sensitive_tools_s3": ["bash"],
        }

    def test_missing_or_foreign_actions_fall_back_to_the_ui_defaults(self) -> None:
        params = privacy_agent_params({"privacyEnabled": True, "privacyS2Action": "nonsense"})

        assert params["privacy_s2_action"] == "warn"
        assert params["privacy_s3_action"] == "redact"
        assert params["privacy_deep_scan"] is False
        assert params["privacy_custom_keywords_s2"] == []

    def test_malformed_rule_lists_are_dropped_instead_of_crashing_a_run(self) -> None:
        params = privacy_agent_params(
            {"privacyEnabled": True, "privacyCustomKeywordsS2": "not a list", "privacyCustomPatternsS3": ["ok", 7, "", None]}
        )

        assert params["privacy_custom_keywords_s2"] == []
        assert params["privacy_custom_patterns_s3"] == ["ok"]


class TestPrivacyPolicyFromSettings:
    def test_no_policy_while_protection_is_off(self) -> None:
        assert privacy_policy_from_settings(None) is None
        assert privacy_policy_from_settings({"privacyEnabled": False, **_RULES}) is None

    def test_policy_carries_actions_and_every_custom_rule(self) -> None:
        policy = privacy_policy_from_settings(
            {"privacyEnabled": True, "privacyS2Action": "redact", "privacyS3Action": "block", **_RULES}
        )

        assert policy is not None and policy.enabled is True
        assert (policy.s2_action, policy.s3_action) == (PIIAction.REDACT, PIIAction.BLOCK)
        assert policy.custom_keywords_s2 == ("Project Falcon",)
        assert policy.custom_patterns_s3 == (r"SEC-\d{4}",)
        assert policy.sensitive_tools_s3 == ("bash",)


class TestResolvePrivacyParams:
    _persisted_on = {"privacyEnabled": True, "privacyS2Action": "warn", "privacyS3Action": "redact", **_RULES}

    def test_a_request_that_says_nothing_gets_the_persisted_protection(self) -> None:
        assert resolve_privacy_params(self._persisted_on, {}) == privacy_agent_params(self._persisted_on)

    def test_a_request_that_says_nothing_with_protection_off_gets_no_protection(self) -> None:
        assert resolve_privacy_params({"privacyEnabled": False}, {}) == {"privacy_deep_scan": False}
        assert resolve_privacy_params(None, {}) == {"privacy_deep_scan": False}

    def test_what_the_request_carries_wins_and_the_rest_comes_from_the_settings(self) -> None:
        requested: PrivacyAgentParams = {
            "privacy_enabled": True,
            "privacy_s2_action": "redact",
            "privacy_s3_action": "block",
            "privacy_custom_keywords_s2": ["Only This"],
        }

        params = resolve_privacy_params(self._persisted_on, requested)

        assert params["privacy_s2_action"] == "redact"
        assert params["privacy_s3_action"] == "block"
        assert params["privacy_custom_keywords_s2"] == ["Only This"]
        assert params["privacy_custom_keywords_s3"] == ["vault-7"]

    def test_a_request_can_enable_protection_the_settings_leave_off(self) -> None:
        params = resolve_privacy_params(None, {"privacy_enabled": True, "privacy_s2_action": "redact"})

        assert params["privacy_enabled"] is True
        assert params["privacy_s2_action"] == "redact"
        assert params["privacy_s3_action"] == "redact"

    def test_an_explicit_off_wins_over_the_settings(self) -> None:
        assert resolve_privacy_params(self._persisted_on, {"privacy_enabled": False}) == {"privacy_deep_scan": False}

    def test_the_deep_scan_choice_survives_protection_being_off(self) -> None:
        assert resolve_privacy_params({"privacyDeepScan": True}, {}) == {"privacy_deep_scan": True}
        assert resolve_privacy_params({"privacyDeepScan": True}, {"privacy_deep_scan": False}) == {"privacy_deep_scan": False}

    def test_an_explicit_deep_scan_choice_wins_and_an_unspoken_one_follows_the_settings(self) -> None:
        settings = {"privacyEnabled": True, "privacyDeepScan": True}

        assert resolve_privacy_params(settings, {"privacy_deep_scan": False})["privacy_deep_scan"] is False
        assert resolve_privacy_params(settings, {})["privacy_deep_scan"] is True
