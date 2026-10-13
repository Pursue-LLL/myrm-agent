"""Tests for the privacy settings read from the persisted personal settings."""

from __future__ import annotations

import pytest

from app.core.security.privacy_settings import (
    mask_pii_when_enabled,
    privacy_agent_params,
    privacy_enabled,
)

_PHONE_TEXT = "我的手机 13812345678，身份证 110101199003074530"


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

    def test_enabled_settings_carry_actions_and_deep_scan(self) -> None:
        params = privacy_agent_params(
            {"privacyEnabled": True, "privacyS2Action": "pseudonymize", "privacyS3Action": "block", "privacyDeepScan": True}
        )

        assert params == {
            "privacy_enabled": True,
            "privacy_s2_action": "pseudonymize",
            "privacy_s3_action": "block",
            "privacy_deep_scan": True,
        }

    def test_missing_or_foreign_actions_fall_back_to_the_ui_defaults(self) -> None:
        params = privacy_agent_params({"privacyEnabled": True, "privacyS2Action": "nonsense"})

        assert params["privacy_s2_action"] == "warn"
        assert params["privacy_s3_action"] == "redact"
        assert params["privacy_deep_scan"] is False


class TestMaskPiiWhenEnabled:
    def test_text_passes_through_while_protection_is_off(self) -> None:
        assert mask_pii_when_enabled(_PHONE_TEXT, {"privacyEnabled": False}) == _PHONE_TEXT
        assert mask_pii_when_enabled(_PHONE_TEXT, None) == _PHONE_TEXT

    def test_pii_and_credentials_are_masked_when_protection_is_on(self) -> None:
        masked = mask_pii_when_enabled(f"{_PHONE_TEXT}，password: 123456", {"privacyEnabled": True})

        assert "13812345678" not in masked
        assert "110101199003074530" not in masked
        assert "123456" not in masked
        assert "我的手机" in masked, "surrounding words stay readable; only the sensitive spans are replaced"
