"""Tests for coerce_pii_action — safe PII action string parsing.

Covers valid/missing/invalid persisted action values shared by the retry
memory extraction context and SecurityPolicyExtension.
"""

from unittest.mock import patch

import pytest

from myrm_agent_harness.agent.security.types import PIIAction

from app.core.security.pii_actions import coerce_pii_action


class TestCoercePiiAction:
    def test_valid_value_returns_enum(self) -> None:
        assert coerce_pii_action("warn", PIIAction.REDACT) is PIIAction.WARN
        assert coerce_pii_action("redact", PIIAction.REDACT) is PIIAction.REDACT
        assert coerce_pii_action("pseudonymize", PIIAction.REDACT) is PIIAction.PSEUDONYMIZE
        assert coerce_pii_action("block", PIIAction.REDACT) is PIIAction.BLOCK

    def test_missing_value_returns_default(self) -> None:
        assert coerce_pii_action(None, PIIAction.WARN) is PIIAction.WARN
        assert coerce_pii_action("", PIIAction.REDACT) is PIIAction.REDACT

    @pytest.mark.parametrize(
        "bad_value",
        ["alert", "ban", "pseudonymise", "123", "PSEUDONYMIZE"],
    )
    def test_invalid_value_falls_back_to_default(self, bad_value: str) -> None:
        with patch("app.core.security.pii_actions.logger") as mock_logger:
            result = coerce_pii_action(bad_value, PIIAction.REDACT)
        assert result is PIIAction.REDACT
        mock_logger.warning.assert_called_once()
