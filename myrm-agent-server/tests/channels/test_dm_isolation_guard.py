"""Tests for the DM identity guards: learning eligibility, the guest identity of strangers and the allowlist turn-away.

[INPUT]
- pytest
- app.channels.protocols.pairing::DmPolicy, PairingStatus
- app.channels.routing.channel_data_plane::ChannelDataPlaneService, is_learning_eligible
- app.channels.routing.policy_resolver::PolicyResolver
- app.channels.types::InboundMessage, METADATA_GUEST_TURN_KEY

[OUTPUT]
- Test cases validating the learning-eligibility filter and the ledger stamp by sender trust, the guest identity an
  open DM policy assigns to a stranger, and an allowlist policy turning unpaired senders away.

[POS]
Unit tests in tests/channels/test_dm_isolation_guard.py.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.pairing import DmPolicy, PairingStatus
from app.channels.routing.channel_data_plane import ChannelDataPlaneService, is_learning_eligible
from app.channels.routing.policy_resolver import PolicyResolver
from app.channels.types import METADATA_GUEST_TURN_KEY, InboundMessage


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
@pytest.mark.parametrize(
    ("user_id", "metadata", "is_authenticated", "eligible"),
    [
        ("owner_1", {}, True, True),
        ("owner_1", {}, False, False),
        ("guest_telegram_attacker_123", {}, True, False),
        ("paired_member_slack_u1", {}, True, False),
        ("owner_1", {METADATA_GUEST_TURN_KEY: "1"}, True, False),
    ],
)
async def test_record_inbound_stamps_learning_eligibility_by_sender_trust(
    user_id: str,
    metadata: dict[str, object],
    is_authenticated: bool,
    eligible: bool,
) -> None:
    """Only an authenticated, trusted sender's message is stamped as a learning candidate."""
    msg = InboundMessage(
        channel="telegram",
        sender_id="sender_1",
        sender_name="Alice",
        chat_id="chat_1",
        user_id=user_id,
        content="这是一段有价值的用户业务需求与背景说明",
        metadata=metadata,
    )

    with patch("app.channels.routing.channel_data_plane.get_session") as mock_get_session:
        mock_get_session.return_value.__aenter__.return_value = AsyncMock()
        entry = await ChannelDataPlaneService.record_inbound(msg, is_trigger=True, is_authenticated=is_authenticated)

    assert entry is not None
    assert entry.learning_eligible is eligible


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
