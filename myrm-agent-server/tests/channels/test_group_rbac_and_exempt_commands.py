"""Unit tests for Group Ingress RBAC, Confused Deputy Mitigation, and Exempt Diagnostic Commands.

Covers:
1. Exempt read-only diagnostic commands (/status, /quota, /help) bypassing daily quota.
2. Group ingress sender identity resolution:
   - Unpaired sender in enabled group gets guest UID and METADATA_GUEST_TURN_KEY=1.
   - Paired member gets paired_member UID with daily quota check.
   - Paired member exceeded quota blocked on normal message but allowed on diagnostic commands.
   - Paired admin gets sandbox UID with owner privileges.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.pairing import DmPolicy, PairingRole, PairingStatus
from app.channels.routing.policy_resolver import PolicyResolver
from app.channels.types import METADATA_GUEST_TURN_KEY, InboundMessage


class TestGroupRbacAndExemptCommands:
    """Test suite for group sender-scoped RBAC and quota bypass for diagnostic commands."""

    @pytest.mark.asyncio
    async def test_exempt_diagnostic_commands_bypass_dm_quota(self) -> None:
        mock_pairing = MagicMock()
        mock_pairing.resolve = AsyncMock(return_value="paired_member_telegram_u1")
        mock_pairing.get_pairing_detail = AsyncMock(
            return_value=(PairingStatus.ACTIVE, PairingRole.MEMBER, 5)
        )
        mock_pairing.touch_display_name = AsyncMock()

        mock_policy = MagicMock()
        mock_policy.get_dm_policy = AsyncMock(return_value=DmPolicy.OPEN)
        mock_fx = MagicMock()

        resolver = PolicyResolver(
            pairing=mock_pairing,
            policy=mock_policy,
            context_buffer=MagicMock(),
            fx=mock_fx,
            get_channel=lambda ch: None,
        )

        msg = InboundMessage(
            channel="telegram",
            sender_id="u1",
            content="/status my quota check",
        )

        with patch(
            "app.database.repositories.channel_message_repo.ChannelMessageRepository.get_daily_trigger_count",
            new_callable=AsyncMock,
            return_value=10,
        ):
            resolved = await resolver.resolve_dm_user(msg)
            assert resolved == "paired_member_telegram_u1"
            mock_fx.send_quota_exceeded_reply.assert_not_called()

    @pytest.mark.asyncio
    async def test_group_ingress_sender_scoped_rbac_and_confused_deputy(self) -> None:
        mock_pairing = MagicMock()
        mock_pairing.resolve = AsyncMock(
            side_effect=lambda ch, sender: {
                "admin_user": "sandbox",
                "member_user": "paired_member_slack_member_user",
            }.get(sender, None)
        )
        mock_pairing.get_pairing_detail = AsyncMock(
            return_value=(PairingStatus.ACTIVE, PairingRole.MEMBER, 10)
        )

        mock_policy = MagicMock()
        from app.channels.protocols.pairing import GroupPolicy
        mock_policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
        mock_policy.get_default_user_id = AsyncMock(return_value="sandbox")
        mock_policy.get_enabled_groups = AsyncMock(return_value={"group_123"})
        mock_policy.get_free_response_chats = AsyncMock(return_value=set())
        mock_fx = MagicMock()
        mock_fx.send_quota_exceeded_reply = AsyncMock()
        mock_cb = MagicMock()
        mock_cb.drain_async = AsyncMock(return_value=[])

        resolver = PolicyResolver(
            pairing=mock_pairing,
            policy=mock_policy,
            context_buffer=mock_cb,
            fx=mock_fx,
            get_channel=lambda ch: None,
        )

        # 1. Unpaired sender in enabled group -> Guest turn, stripped of bash/sandbox privileges
        guest_msg = InboundMessage(
            channel="slack",
            chat_id="group_123",
            sender_id="unknown_guest",
            content="@bot hello",
            mentioned=True,
        )
        res = await resolver.resolve_group_user(guest_msg)
        assert res is not None
        uid, out_msg = res
        assert uid == "guest_slack_unknown_guest"
        assert (out_msg.metadata or {}).get(METADATA_GUEST_TURN_KEY) == "1"

        # 2. Member sender in enabled group -> paired_member scoped
        member_msg = InboundMessage(
            channel="slack",
            chat_id="group_123",
            sender_id="member_user",
            content="@bot help me",
            mentioned=True,
        )
        with patch(
            "app.database.repositories.channel_message_repo.ChannelMessageRepository.get_daily_trigger_count",
            new_callable=AsyncMock,
            return_value=2,
        ):
            res_member = await resolver.resolve_group_user(member_msg)
            assert res_member is not None
            mem_uid, _ = res_member
            assert mem_uid == "paired_member_slack_member_user"

        # 3. Member exceeded quota in group with non-exempt message -> Blocked
        exceeded_member_msg = InboundMessage(
            channel="slack",
            chat_id="group_123",
            sender_id="member_user",
            content="@bot do expensive task",
            mentioned=True,
        )
        with patch(
            "app.database.repositories.channel_message_repo.ChannelMessageRepository.get_daily_trigger_count",
            new_callable=AsyncMock,
            return_value=10,
        ):
            res_exceeded = await resolver.resolve_group_user(exceeded_member_msg)
            assert res_exceeded is None
            mock_fx.send_quota_exceeded_reply.assert_called_once_with(exceeded_member_msg, 10)

        # 4. Member exceeded quota in group with /quota -> Allowed
        quota_check_msg = InboundMessage(
            channel="slack",
            chat_id="group_123",
            sender_id="member_user",
            content="@bot /quota",
            mentioned=True,
        )
        with patch(
            "app.database.repositories.channel_message_repo.ChannelMessageRepository.get_daily_trigger_count",
            new_callable=AsyncMock,
            return_value=10,
        ):
            res_quota = await resolver.resolve_group_user(quota_check_msg)
            assert res_quota is not None
            q_uid, _ = res_quota
            assert q_uid == "paired_member_slack_member_user"

        # 5. Admin sender in enabled group -> Sandbox owner privileges
        admin_msg = InboundMessage(
            channel="slack",
            chat_id="group_123",
            sender_id="admin_user",
            content="@bot restart service",
            mentioned=True,
        )
        res_admin = await resolver.resolve_group_user(admin_msg)
        assert res_admin is not None
        adm_uid, _ = res_admin
        assert adm_uid == "sandbox"
