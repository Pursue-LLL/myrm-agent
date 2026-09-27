"""Tests for server-level default TTSR stream rules."""

from __future__ import annotations

from myrm_agent_harness.agent.streaming.rules.coordinator import TtsrCoordinator

from app.services.rules.default_rules import get_default_stream_rules


def test_get_default_stream_rules() -> None:
    """Verify default rules suite contains core safety definitions."""
    rules = get_default_stream_rules()
    assert len(rules) >= 3

    rule_ids = {r.rule_id for r in rules}
    assert "ban_destructive_rm" in rule_ids
    assert "ban_private_key_leak" in rule_ids
    assert "ban_api_credential_leak" in rule_ids

    for rule in rules:
        assert rule.reminder
        assert rule.action == "abort_and_retry"
        assert rule.repeat_gap >= 5


def test_destructive_rm_rule_matching() -> None:
    """Test destructive rm pattern matches dangerous variations."""
    rules = get_default_stream_rules()
    coordinator = TtsrCoordinator(rules=rules)

    # Danger: rm -rf /
    match = coordinator.inspect_chunk("assistant", "rm -rf /var/log", current_turn=1)
    assert match is not None
    assert match.rule.rule_id == "ban_destructive_rm"
    assert coordinator.interrupt_requested is True

    coordinator2 = TtsrCoordinator(rules=rules)
    match_home = coordinator2.inspect_chunk("assistant", "rm -f ~", current_turn=1)
    assert match_home is not None
    assert match_home.rule.rule_id == "ban_destructive_rm"


def test_credential_leak_rule_matching() -> None:
    """Test private key and API key matching."""
    rules = get_default_stream_rules()
    coordinator = TtsrCoordinator(rules=rules)

    # Private key
    pk_sample = "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQEA0"
    match_pk = coordinator.inspect_chunk("assistant", pk_sample, current_turn=1)
    assert match_pk is not None
    assert match_pk.rule.rule_id == "ban_private_key_leak"

    coordinator.reset_turn()

    # OpenAI API Key
    key_sample = "sk-abcdefghijklmnopqrstuvwxyz1234567890"
    match_key = coordinator.inspect_chunk("tool_args", key_sample, current_turn=1)
    assert match_key is not None
    assert match_key.rule.rule_id == "ban_api_credential_leak"
