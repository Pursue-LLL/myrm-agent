"""PolicyResolver tests — DM policy modes, pairing states, and LID fallback."""

from __future__ import annotations

from typing import cast
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.protocols.pairing import (
    DmPolicy,
    PairingRole,
    PairingStatus,
)
from app.channels.routing.policy_resolver import PolicyResolver
from tests.channels.policy_resolver_testkit import make_message, make_resolver


class TestResolveDmUser:
    @pytest.mark.asyncio
    async def test_takes_the_identity_of_a_control_plane_forward(self) -> None:
        policy = MagicMock()
        r = make_resolver(policy=policy)

        result = await r.resolve_dm_user(make_message(user_id="existing-uid", metadata={"trusted_inbound": "control_plane"}))

        assert result == "existing-uid"
        policy.get_dm_policy.assert_not_called()

    @pytest.mark.asyncio
    async def test_ignores_an_identity_carried_without_the_control_plane_mark(self) -> None:
        """Only the DM policy and the sender's pairing say who a sender is; no policy provider means ALLOWLIST."""
        r = make_resolver()

        assert await r.resolve_dm_user(make_message(user_id="existing-uid")) is None

    @pytest.mark.asyncio
    async def test_disabled_policy(self) -> None:
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.DISABLED)
        r = make_resolver(policy=policy)
        result = await r.resolve_dm_user(make_message())
        assert result is None

    @pytest.mark.asyncio
    async def test_open_policy_resolves(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value="uid-1")
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.OPEN)
        r = make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(make_message())
        assert result == "uid-1"

    @pytest.mark.asyncio
    async def test_open_policy_unmapped_lid_becomes_guest(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.bind = AsyncMock()
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.OPEN)
        policy.get_default_user_id = AsyncMock(return_value="default-uid")

        ch_mock = MagicMock()
        ch_mock._lid_to_pn = {}

        r = make_resolver(
            pairing=pairing,
            policy=policy,
            get_channel=MagicMock(return_value=ch_mock),
        )
        result = await r.resolve_dm_user(make_message(sender_id="123@lid"))
        assert result == "guest_test_123@lid"
        pairing.bind.assert_not_called()

    @pytest.mark.asyncio
    async def test_open_policy_unpaired_sender_becomes_guest(self) -> None:
        """An open DM policy admits any account, never as the default (owner) user."""
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.OPEN)
        policy.get_default_user_id = AsyncMock(return_value="default-uid")
        r = make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(make_message())
        assert result == "guest_test_u1"
        policy.get_default_user_id.assert_not_called()

    @pytest.mark.asyncio
    async def test_pairing_mode_resolves(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value="uid-1")
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.PAIRING)
        r = make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(make_message())
        assert result == "uid-1"

    @pytest.mark.asyncio
    async def test_pairing_mode_blocked(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=PairingStatus.BLOCKED)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.PAIRING)
        r = make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(make_message())
        assert result is None

    @pytest.mark.asyncio
    async def test_pairing_mode_pending(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=PairingStatus.PENDING)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.PAIRING)
        r = make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(make_message())
        assert result is None
        cast(AsyncMock, r._fx.send_pending_reply).assert_called_once()

    @pytest.mark.asyncio
    async def test_pairing_mode_new_sender(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=None)
        pairing.bind = AsyncMock()
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.PAIRING)
        policy.get_default_user_id = AsyncMock(return_value="default")
        r = make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(make_message())
        assert result is None
        pairing.bind.assert_called_once()
        cast(AsyncMock, r._fx.send_pairing_request_reply).assert_called_once()

    @pytest.mark.asyncio
    async def test_allowlist_mode_resolves(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value="uid-1")
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.ALLOWLIST)
        r = make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(make_message())
        assert result == "uid-1"

    @pytest.mark.asyncio
    async def test_allowlist_mode_blocked(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=PairingStatus.BLOCKED)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.ALLOWLIST)
        r = make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(make_message())
        assert result is None

    @pytest.mark.asyncio
    async def test_allowlist_mode_unpaired(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=None)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.ALLOWLIST)
        r = make_resolver(pairing=pairing, policy=policy)
        result = await r.resolve_dm_user(make_message())
        assert result is None

    @pytest.mark.asyncio
    async def test_no_policy_defaults_to_allowlist(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=None)
        r = make_resolver(pairing=pairing, policy=None)
        result = await r.resolve_dm_user(make_message())
        assert result is None


class TestLidFallback:
    @staticmethod
    def _lid_resolver(pairing: MagicMock) -> PolicyResolver:
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.OPEN)
        ch_mock = MagicMock()
        ch_mock._lid_to_pn = {"123@lid": "+1234567890"}
        return make_resolver(pairing=pairing, policy=policy, get_channel=MagicMock(return_value=ch_mock))

    @pytest.mark.asyncio
    async def test_lid_resolved_via_cache(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(side_effect=[None, "uid-from-pn"])
        pairing.get_pairing_detail = AsyncMock(return_value=(PairingStatus.ACTIVE, PairingRole.ADMIN, None))
        pairing.bind = AsyncMock()

        result = await self._lid_resolver(pairing).resolve_dm_user(make_message(sender_id="123@lid"))

        assert result == "uid-from-pn"
        pairing.bind.assert_awaited_once()
        args, kwargs = pairing.bind.await_args
        assert args == ("test", "123@lid", "uid-from-pn")
        assert kwargs["role"] == PairingRole.ADMIN

    @pytest.mark.asyncio
    async def test_lid_inherits_status_role_and_quota_of_its_phone_number(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(side_effect=[None, "paired_member_test_+1234567890"])
        pairing.get_pairing_detail = AsyncMock(return_value=(PairingStatus.ACTIVE, PairingRole.MEMBER, 7))
        pairing.bind = AsyncMock()

        await self._lid_resolver(pairing).resolve_dm_user(make_message(sender_id="123@lid"))

        kwargs = pairing.bind.await_args.kwargs
        assert (kwargs["status"], kwargs["role"], kwargs["daily_quota"]) == (PairingStatus.ACTIVE, PairingRole.MEMBER, 7)

    @pytest.mark.asyncio
    async def test_lid_of_unpaired_phone_number_is_not_bound(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_pairing_detail = AsyncMock(return_value=None)
        pairing.bind = AsyncMock()

        result = await self._lid_resolver(pairing).resolve_dm_user(make_message(sender_id="123@lid"))

        assert result == "guest_test_123@lid"
        pairing.bind.assert_not_called()

    @pytest.mark.asyncio
    async def test_lid_cache_miss_no_default(self) -> None:
        pairing = MagicMock()
        pairing.resolve = AsyncMock(return_value=None)
        pairing.get_status = AsyncMock(return_value=None)
        policy = MagicMock()
        policy.get_dm_policy = AsyncMock(return_value=DmPolicy.ALLOWLIST)

        ch_mock = MagicMock()
        ch_mock._lid_to_pn = {"other@lid": "+999"}

        r = make_resolver(
            pairing=pairing,
            policy=policy,
            get_channel=MagicMock(return_value=ch_mock),
        )
        result = await r.resolve_dm_user(make_message(sender_id="123@lid"))
        assert result is None
