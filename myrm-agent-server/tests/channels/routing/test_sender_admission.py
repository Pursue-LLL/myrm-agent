"""Sender admission and sender trust: the read-only verdicts that guard event-triggered cron jobs.

Both run before PolicyResolver. Admission must agree with what PolicyResolver decides for the same sender (the owner
is always admitted on top of that); trust must agree with the fence the chat turn gets on the identity PolicyResolver
assigns. Neither may change any state.
"""

from __future__ import annotations

import uuid
from collections.abc import AsyncIterator, Iterator
from dataclasses import dataclass, replace
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.pairing import DmPolicy, GroupPolicy, GroupTriggerMode, PairingRole, PairingStatus
from app.channels.routing.context_buffer import GroupContextBuffer
from app.channels.routing.identity_scope import is_untrusted_sender
from app.channels.routing.message_effects import MessageEffects
from app.channels.routing.policy_resolver import PolicyResolver
from app.channels.types import METADATA_EXPLICIT_MENTION_KEY, METADATA_GUEST_TURN_KEY, InboundMessage, ReactionLevel
from app.core.channel_bridge.pairing_store import SqlPairingStore

Pairing = tuple[PairingStatus, PairingRole] | None

_OWNER: Pairing = (PairingStatus.ACTIVE, PairingRole.ADMIN)
_MEMBER: Pairing = (PairingStatus.ACTIVE, PairingRole.MEMBER)
_PENDING: Pairing = (PairingStatus.PENDING, PairingRole.MEMBER)
_BLOCKED: Pairing = (PairingStatus.BLOCKED, PairingRole.MEMBER)

_CHAT = "grp-1"


@dataclass(frozen=True)
class _Policy:
    """In-memory ChannelPolicyProvider exposing the knobs the admission gates read."""

    dm: DmPolicy = DmPolicy.ALLOWLIST
    group: GroupPolicy = GroupPolicy.OPEN
    enabled_groups: frozenset[str] = frozenset()
    guest_mode: bool = False
    default_user_id: str = "sandbox"  # what PairingStore.resolve returns for an ACTIVE admin pairing

    async def get_dm_policy(self, channel: str) -> DmPolicy:
        return self.dm

    async def get_group_policy(self, channel: str) -> GroupPolicy:
        return self.group

    async def get_group_trigger(self, channel: str) -> tuple[GroupTriggerMode, list[str]]:
        return GroupTriggerMode.MENTION_ONLY, []

    async def get_reaction_level(self, channel: str) -> ReactionLevel:
        return ReactionLevel.SIMPLE

    async def get_enabled_groups(self) -> set[str]:
        return set(self.enabled_groups)

    async def get_guest_mode(self, channel: str) -> bool:
        return self.guest_mode

    async def get_free_response_chats(self, channel: str) -> set[str]:
        return set()

    async def get_default_user_id(self) -> str | None:
        return self.default_user_id


@dataclass(frozen=True)
class _DmCase:
    id: str
    dm: DmPolicy
    pairing: Pairing
    admitted: bool
    runs_turn: bool  # the chat path resolves an identity for this sender


@dataclass(frozen=True)
class _GroupCase:
    id: str
    group: GroupPolicy
    chat_enabled: bool
    guest_mode: bool
    explicit_mention: bool
    pairing: Pairing
    admitted: bool
    runs_turn: bool

    @property
    def policy(self) -> _Policy:
        enabled = frozenset({_CHAT}) if self.chat_enabled else frozenset()
        return _Policy(group=self.group, enabled_groups=enabled, guest_mode=self.guest_mode)


@dataclass(frozen=True)
class _LidCase:
    id: str
    phone_pairing: Pairing
    mapped: bool  # the adapter knows which phone number the LID belongs to
    admitted: bool


DM_CASES = [
    _DmCase("allowlist-owner", DmPolicy.ALLOWLIST, _OWNER, True, True),
    _DmCase("allowlist-member", DmPolicy.ALLOWLIST, _MEMBER, True, True),
    _DmCase("allowlist-stranger", DmPolicy.ALLOWLIST, None, False, False),
    _DmCase("allowlist-blocked", DmPolicy.ALLOWLIST, _BLOCKED, False, False),
    _DmCase("allowlist-pending", DmPolicy.ALLOWLIST, _PENDING, False, False),
    _DmCase("pairing-member", DmPolicy.PAIRING, _MEMBER, True, True),
    _DmCase("pairing-stranger", DmPolicy.PAIRING, None, False, False),
    _DmCase("pairing-pending", DmPolicy.PAIRING, _PENDING, False, False),
    _DmCase("open-stranger", DmPolicy.OPEN, None, True, True),
    _DmCase("disabled-member", DmPolicy.DISABLED, _MEMBER, False, False),
    _DmCase("disabled-owner", DmPolicy.DISABLED, _OWNER, True, False),
]

GROUP_CASES = [
    _GroupCase("enabled-stranger", GroupPolicy.OPEN, True, False, False, None, True, True),
    _GroupCase("enabled-member", GroupPolicy.OPEN, True, False, False, _MEMBER, True, True),
    _GroupCase("enabled-owner", GroupPolicy.OPEN, True, False, False, _OWNER, True, True),
    _GroupCase("enabled-allowlist-policy", GroupPolicy.ALLOWLIST, True, False, False, None, True, True),
    _GroupCase("not-enabled-stranger", GroupPolicy.OPEN, False, False, False, None, False, False),
    _GroupCase("not-enabled-blocked", GroupPolicy.OPEN, False, False, False, _BLOCKED, False, False),
    _GroupCase("guest-mention", GroupPolicy.OPEN, False, True, True, None, True, True),
    _GroupCase("guest-mode-without-mention", GroupPolicy.OPEN, False, True, False, None, False, False),
    _GroupCase("mention-without-guest-mode", GroupPolicy.OPEN, False, False, True, None, False, False),
    _GroupCase("disabled-policy-enabled-chat", GroupPolicy.DISABLED, True, False, False, None, False, False),
    _GroupCase("not-enabled-owner", GroupPolicy.OPEN, False, False, False, _OWNER, True, False),
    _GroupCase("disabled-policy-owner", GroupPolicy.DISABLED, False, False, False, _OWNER, True, False),
]

LID_CASES = [
    _LidCase("mapped-member", _MEMBER, True, True),
    _LidCase("mapped-owner", _OWNER, True, True),
    _LidCase("mapped-pending", _PENDING, True, False),
    _LidCase("mapped-blocked", _BLOCKED, True, False),
    _LidCase("unmapped", _MEMBER, False, False),
]


class _Roster:
    """The senders and pairing rows one test creates, removed on teardown so tests never see each other's rows."""

    def __init__(self) -> None:
        self.store = SqlPairingStore()
        self.channel = f"adm{uuid.uuid4().hex[:8]}"
        self._senders: list[str] = []

    def sender(self, suffix: str = "") -> str:
        sender_id = f"s{uuid.uuid4().hex[:8]}{suffix}"
        self._senders.append(sender_id)
        return sender_id

    async def paired_sender(self, pairing: Pairing) -> str:
        sender_id = self.sender()
        if pairing is not None:
            await self.store.bind(self.channel, sender_id, status=pairing[0], role=pairing[1])
        return sender_id

    async def detail(self, sender_id: str) -> tuple[PairingStatus, PairingRole, int | None] | None:
        return await self.store.get_pairing_detail(self.channel, sender_id)

    async def cleanup(self) -> None:
        for sender_id in self._senders:
            await self.store.unbind(self.channel, sender_id)

    def dm(self, sender_id: str, *, user_id: str | None = None, trusted: bool = False) -> InboundMessage:
        return InboundMessage(
            channel=self.channel,
            sender_id=sender_id,
            chat_id=sender_id,
            content="server down",
            user_id=user_id,
            metadata=_metadata(trusted=trusted),
        )

    def group(
        self,
        sender_id: str,
        *,
        mentioned: bool = False,
        explicit_mention: bool = False,
        user_id: str | None = None,
        trusted: bool = False,
    ) -> InboundMessage:
        return InboundMessage(
            channel=self.channel,
            sender_id=sender_id,
            chat_id=_CHAT,
            content="server down",
            user_id=user_id,
            is_group=True,
            mentioned=mentioned,
            metadata=_metadata(explicit_mention=explicit_mention, trusted=trusted),
        )


def _metadata(*, explicit_mention: bool = False, trusted: bool = False) -> dict[str, object]:
    metadata: dict[str, object] = {}
    if explicit_mention:
        metadata[METADATA_EXPLICIT_MENTION_KEY] = "1"
    if trusted:
        metadata["trusted_inbound"] = "control_plane"
    return metadata


def _resolver(roster: _Roster, policy: _Policy | None, lid_map: dict[str, str] | None = None) -> PolicyResolver:
    fx = MagicMock(spec=MessageEffects)
    for name in ("send_pending_reply", "send_pairing_request_reply", "send_quota_exceeded_reply", "send_mute_reply"):
        setattr(fx, name, AsyncMock())
    channel = MagicMock()
    channel._lid_to_pn = lid_map or {}
    return PolicyResolver(
        pairing=roster.store,
        policy=policy,
        context_buffer=GroupContextBuffer(),
        fx=fx,
        get_channel=lambda _name: channel,
    )


@pytest.fixture
async def roster() -> AsyncIterator[_Roster]:
    roster = _Roster()
    yield roster
    await roster.cleanup()


@pytest.fixture(autouse=True)
def _no_ledger_writes() -> Iterator[None]:
    """The resolvers record every inbound message; the comparison runs do not need the ledger."""
    with patch("app.channels.routing.channel_data_plane.ChannelDataPlaneService.record_inbound", new=AsyncMock()):
        yield


class TestDirectMessages:
    @pytest.mark.parametrize("case", DM_CASES, ids=lambda case: case.id)
    async def test_verdict_and_no_state_change(self, roster: _Roster, case: _DmCase) -> None:
        sender_id = await roster.paired_sender(case.pairing)
        before = await roster.detail(sender_id)

        assert await _resolver(roster, _Policy(dm=case.dm)).is_sender_admitted(roster.dm(sender_id)) is case.admitted
        assert await roster.detail(sender_id) == before, "the verdict must not create or change a pairing"

    @pytest.mark.parametrize("case", DM_CASES, ids=lambda case: case.id)
    async def test_agrees_with_the_chat_path(self, roster: _Roster, case: _DmCase) -> None:
        sender_id = await roster.paired_sender(case.pairing)
        resolver = _resolver(roster, _Policy(dm=case.dm))

        assert (await resolver.resolve_dm_user(roster.dm(sender_id)) is not None) is case.runs_turn


class TestGroupMessages:
    @pytest.mark.parametrize("case", GROUP_CASES, ids=lambda case: case.id)
    async def test_verdict_is_per_chat_and_changes_no_state(self, roster: _Roster, case: _GroupCase) -> None:
        sender_id = await roster.paired_sender(case.pairing)
        before = await roster.detail(sender_id)
        resolver = _resolver(roster, case.policy)

        # A message that does not address the bot is admitted like one that does: admission is per chat.
        for mentioned in (False, True):
            msg = roster.group(sender_id, mentioned=mentioned, explicit_mention=case.explicit_mention)
            assert await resolver.is_sender_admitted(msg) is case.admitted
        assert await roster.detail(sender_id) == before

    @pytest.mark.parametrize("case", GROUP_CASES, ids=lambda case: case.id)
    async def test_agrees_with_the_chat_path(self, roster: _Roster, case: _GroupCase) -> None:
        sender_id = await roster.paired_sender(case.pairing)
        msg = roster.group(sender_id, mentioned=True, explicit_mention=case.explicit_mention)

        assert (await _resolver(roster, case.policy).resolve_group_user(msg) is not None) is case.runs_turn


class TestWhatsAppLid:
    @pytest.mark.parametrize("case", LID_CASES, ids=lambda case: case.id)
    async def test_lid_follows_its_phone_number_without_being_bound(self, roster: _Roster, case: _LidCase) -> None:
        phone = await roster.paired_sender(case.phone_pairing)
        lid = roster.sender("@lid")
        resolver = _resolver(roster, _Policy(), lid_map={lid: phone} if case.mapped else {})

        assert await resolver.is_sender_admitted(roster.dm(lid)) is case.admitted
        assert await roster.detail(lid) is None, "the verdict must not bind the LID"
        # The chat path agrees, and it is the one that binds.
        assert (await resolver.resolve_dm_user(roster.dm(lid)) is not None) is case.admitted


class TestTrustedAndPreResolved:
    async def test_control_plane_forward_is_admitted_whatever_the_policy(self, roster: _Roster) -> None:
        resolver = _resolver(roster, _Policy(dm=DmPolicy.DISABLED, group=GroupPolicy.DISABLED))
        sender_id = roster.sender()

        assert await resolver.is_sender_admitted(roster.dm(sender_id, user_id="platform-user", trusted=True)) is True
        assert await resolver.is_sender_admitted(roster.group(sender_id, user_id="platform-user", trusted=True)) is True

    async def test_pre_resolved_user_admits_a_dm_but_not_a_group(self, roster: _Roster) -> None:
        resolver = _resolver(roster, _Policy())
        stranger = roster.sender()

        assert await resolver.is_sender_admitted(roster.dm(stranger, user_id="u-1")) is True
        assert await resolver.is_sender_admitted(roster.group(stranger, user_id="u-1")) is False

    async def test_without_a_policy_provider_dms_are_allowlisted_and_groups_closed(self, roster: _Roster) -> None:
        resolver = _resolver(roster, None)
        stranger, member = roster.sender(), await roster.paired_sender(_MEMBER)

        assert await resolver.is_sender_admitted(roster.dm(stranger)) is False
        assert await resolver.is_sender_admitted(roster.dm(member)) is True
        assert await resolver.is_sender_admitted(roster.group(member)) is False


async def _chat_turn_is_fenced(resolver: PolicyResolver, msg: InboundMessage) -> bool:
    """The fence decision the executor makes for this sender, on the identity and message the resolvers hand over."""
    if msg.is_group:
        resolved = await resolver.resolve_group_user(msg)
        assert resolved is not None
        user_id, msg = resolved
    else:
        resolved_user = await resolver.resolve_dm_user(msg)
        assert resolved_user is not None
        user_id = resolved_user
    return is_untrusted_sender(user_id, msg)


class TestSenderTrust:
    @pytest.mark.parametrize("case", [case for case in DM_CASES if case.runs_turn], ids=lambda case: case.id)
    async def test_dm_verdict_matches_the_chat_fence(self, roster: _Roster, case: _DmCase) -> None:
        sender_id = await roster.paired_sender(case.pairing)
        resolver = _resolver(roster, _Policy(dm=case.dm))
        msg = roster.dm(sender_id)
        before = await roster.detail(sender_id)

        verdict = await resolver.is_untrusted_event_sender(msg)

        assert await roster.detail(sender_id) == before, "the verdict must not create or change a pairing"
        assert verdict is await _chat_turn_is_fenced(resolver, msg)

    @pytest.mark.parametrize("case", [case for case in GROUP_CASES if case.runs_turn], ids=lambda case: case.id)
    async def test_group_verdict_matches_the_chat_fence(self, roster: _Roster, case: _GroupCase) -> None:
        sender_id = await roster.paired_sender(case.pairing)
        resolver = _resolver(roster, case.policy)
        msg = roster.group(sender_id, mentioned=True, explicit_mention=case.explicit_mention)
        before = await roster.detail(sender_id)

        verdict = await resolver.is_untrusted_event_sender(msg)

        assert await roster.detail(sender_id) == before
        assert verdict is await _chat_turn_is_fenced(resolver, msg)

    @pytest.mark.parametrize(
        ("pairing", "untrusted"),
        [(_OWNER, False), (_MEMBER, True), (_PENDING, True), (_BLOCKED, True), (None, True)],
        ids=["owner", "member", "pending", "blocked", "stranger"],
    )
    async def test_only_an_active_admin_pairing_is_the_owner(self, roster: _Roster, pairing: Pairing, untrusted: bool) -> None:
        resolver = _resolver(roster, _Policy())
        sender_id = await roster.paired_sender(pairing)

        assert await resolver.is_untrusted_event_sender(roster.dm(sender_id)) is untrusted
        assert await resolver.is_untrusted_event_sender(roster.group(sender_id)) is untrusted

    @pytest.mark.parametrize(
        ("user_id", "guest_turn", "untrusted"),
        [
            ("sandbox", False, False),
            ("guest_chan_x", False, True),
            ("paired_member_chan_x", False, True),
            ("sandbox", True, True),
        ],
        ids=["owner", "guest", "member", "guest-turn-marker"],
    )
    async def test_control_plane_forward_is_judged_by_the_identity_it_carries(
        self, roster: _Roster, user_id: str, guest_turn: bool, untrusted: bool
    ) -> None:
        msg = roster.dm(roster.sender(), user_id=user_id, trusted=True)
        if guest_turn:
            msg = replace(msg, metadata={**msg.metadata, METADATA_GUEST_TURN_KEY: "1"})

        assert await _resolver(roster, _Policy()).is_untrusted_event_sender(msg) is untrusted

    async def test_a_pre_resolved_identity_does_not_make_a_stranger_the_owner(self, roster: _Roster) -> None:
        resolver = _resolver(roster, _Policy())
        stranger, owner = roster.sender(), await roster.paired_sender(_OWNER)

        assert await resolver.is_untrusted_event_sender(roster.dm(stranger, user_id="sandbox")) is True
        assert await resolver.is_untrusted_event_sender(roster.dm(owner, user_id="sandbox")) is False
