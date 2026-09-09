"""Unit and integration tests for Multi-Channel DM Isolation, Session Enclave, and Anti-Poisoning Guard.

[INPUT]
- pytest
- app.channels.routing.router_keys::routing_enclave_key, parse_enclave_key, routing_session_key
- app.channels.routing.policy_resolver::PolicyResolver
- app.channels.routing.channel_data_plane::is_learning_eligible, ChannelDataPlaneService
- app.channels.types::InboundMessage, DmPolicy

[OUTPUT]
- Test cases validating enclave keys, privilege escalation defense, and memory anti-poisoning fences.

[POS]
Unit tests in tests/channels/test_dm_isolation_and_enclave_guard.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.protocols.pairing import DmPolicy, PairingStatus
from app.channels.routing.channel_data_plane import is_learning_eligible
from app.channels.routing.policy_resolver import PolicyResolver
from app.channels.routing.router_keys import (
    parse_enclave_key,
    routing_enclave_key,
    routing_session_key,
)
from app.channels.types import InboundMessage


def test_routing_enclave_key_isolation() -> None:
    """Verify 4-tuple enclave keys provide strict isolation across tenants and profiles."""
    key_user_a = routing_enclave_key("telegram", "user_123", tenant_id="tenant_x", agent_profile_id="agent_coder")
    key_user_b = routing_enclave_key("telegram", "user_456", tenant_id="tenant_x", agent_profile_id="agent_coder")
    key_agent_b = routing_enclave_key("telegram", "user_123", tenant_id="tenant_x", agent_profile_id="agent_writer")

    assert key_user_a != key_user_b
    assert key_user_a != key_agent_b
    assert key_user_a == "tenant_x:telegram:user_123:agent_coder"

    # Verify parse_enclave_key round-trip
    parsed = parse_enclave_key(key_user_a)
    assert parsed["tenant_id"] == "tenant_x"
    assert parsed["channel"] == "telegram"
    assert parsed["peer_id"] == "user_123"
    assert parsed["agent_profile_id"] == "agent_coder"

    # Legacy 2-part key fallback
    legacy_parsed = parse_enclave_key("slack:peer_999")
    assert legacy_parsed["tenant_id"] == "default"
    assert legacy_parsed["channel"] == "slack"
    assert legacy_parsed["peer_id"] == "peer_999"
    assert legacy_parsed["agent_profile_id"] == "default"

    # Backward compatible session key
    assert routing_session_key("feishu", "user_1") == "feishu:user_1"


def test_is_learning_eligible_filtering() -> None:
    """Verify high-signal human context filter blocks noise and slash commands."""
    assert is_learning_eligible("这是一段有价值的用户业务需求与背景说明") is True
    assert is_learning_eligible("") is False
    assert is_learning_eligible("a") is False
    assert is_learning_eligible("/help") is False
    assert is_learning_eligible("!deploy prod") is False
    assert is_learning_eligible("#tag") is False
    assert is_learning_eligible("Sentry: Error encountered in prod", sender_name="alertmanager") is False
    assert is_learning_eligible("打卡提醒：今天请记得按时打卡", sender_name="提醒助手") is False


@pytest.mark.asyncio
async def test_policy_resolver_open_mode_privilege_escalation_defense() -> None:
    """Verify open DM policy assigns sandboxed guest identity instead of default_user_id."""
    pairing_store = AsyncMock()
    pairing_store.resolve.return_value = None  # Unknown/unpaired sender

    policy_provider = AsyncMock()
    policy_provider.get_dm_policy.return_value = DmPolicy.OPEN
    policy_provider.get_default_user_id.return_value = "sandbox_admin_user"

    resolver = PolicyResolver(
        pairing=pairing_store,
        policy=policy_provider,
        context_buffer=MagicMock(),
        fx=MagicMock(),
        get_channel=MagicMock(),
    )

    msg = InboundMessage(
        channel="telegram",
        sender_id="attacker_123",
        sender_name="Attacker",
        chat_id="chat_789",
        content="rm -rf /",
    )

    resolved_user = await resolver.resolve_dm_user(msg)

    # Must NOT be the privileged sandbox_admin_user!
    assert resolved_user is not None
    assert resolved_user != "sandbox_admin_user"
    assert resolved_user.startswith("guest_telegram_attacker_123")


@pytest.mark.asyncio
async def test_policy_resolver_allowlist_mode_blocks_unpaired() -> None:
    """Verify allowlist mode completely ignores unpaired senders."""
    pairing_store = AsyncMock()
    pairing_store.resolve.return_value = None
    pairing_store.get_status.return_value = PairingStatus.BLOCKED

    policy_provider = AsyncMock()
    policy_provider.get_dm_policy.return_value = DmPolicy.ALLOWLIST

    resolver = PolicyResolver(
        pairing=pairing_store,
        policy=policy_provider,
        context_buffer=MagicMock(),
        fx=MagicMock(),
        get_channel=MagicMock(),
    )

    msg = InboundMessage(
        channel="telegram",
        sender_id="stranger_456",
        sender_name="Stranger",
        chat_id="chat_456",
        content="hello",
    )

    resolved_user = await resolver.resolve_dm_user(msg)
    assert resolved_user is None
