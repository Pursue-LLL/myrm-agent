"""``is_group_chatter`` and ``resolve_group_user`` reach the same verdict on whether a group message starts a turn.

The router settles chatter that arrives while the chat's turn runs with ``is_group_chatter`` and everything else
through ``resolve_group_user``. If the two drifted apart, a message nobody addressed would queue as if it were a
request, or one addressed to the bot would be dropped into the context of the next turn. Each case is judged on a
resolver of its own, because resolving a message mutes threads and counts bot triggers.
"""

from __future__ import annotations

import asyncio
import itertools
from collections.abc import Iterator
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.protocols.pairing import DmPolicy, GroupPolicy, GroupTriggerMode, PairingRole, PairingStatus
from app.channels.routing.context_buffer import GroupContextBuffer
from app.channels.routing.message_effects import MessageEffects
from app.channels.routing.policy_resolver import PolicyResolver
from app.channels.types import InboundMessage, ReactionLevel

_CHAT = "grp-1"
_THREAD = "t1"
_CHANNEL = "telegram"
_RECORD_INBOUND = "app.channels.routing.channel_data_plane.ChannelDataPlaneService.record_inbound"
_MUTE_THREAD = "app.channels.routing.follow_up.mute_tracked_thread"


class _Pairing:
    """Every sender resolves to the owner's default user, so an admitted trigger always starts a turn."""

    async def resolve(self, channel: str, sender_id: str) -> str | None:
        return "owner"

    async def touch_display_name(self, channel: str, sender_id: str, display_name: str) -> None:
        return None

    async def bind(
        self,
        channel: str,
        sender_id: str,
        user_id: str,
        *,
        status: PairingStatus = PairingStatus.ACTIVE,
        display_name: str | None = None,
        role: PairingRole = PairingRole.MEMBER,
        daily_quota: int | None = None,
    ) -> None:
        return None

    async def unbind(self, channel: str, sender_id: str) -> None:
        return None

    async def get_status(self, channel: str, sender_id: str) -> PairingStatus | None:
        return None

    async def get_pairing_detail(self, channel: str, sender_id: str) -> tuple[PairingStatus, PairingRole, int | None] | None:
        return None


@dataclass(frozen=True)
class _Case:
    group: GroupPolicy
    chat_enabled: bool
    trigger: GroupTriggerMode
    free_response: bool
    content: str
    mentioned: bool
    thread_active: bool
    is_bot: bool

    @property
    def id(self) -> str:
        parts = [
            self.group.value,
            "enabled" if self.chat_enabled else "not-enabled",
            "free-response" if self.free_response else self.trigger.value,
            {"hello": "plain", "/ask hello": "prefixed", "/mute": "mute-word"}[self.content],
            "mentioned" if self.mentioned else "unaddressed",
            "thread-active" if self.thread_active else "no-thread",
            "bot" if self.is_bot else "human",
        ]
        return "-".join(parts)

    @property
    def admitted(self) -> bool:
        """Whether the group gates of ``resolve_group_user`` let the chat through (guest mode is off)."""
        return self.group != GroupPolicy.DISABLED and self.chat_enabled

    @property
    def message(self) -> InboundMessage:
        return InboundMessage(
            channel=_CHANNEL,
            sender_id="alice",
            chat_id=_CHAT,
            is_group=True,
            is_bot=self.is_bot,
            mentioned=self.mentioned,
            content=self.content,
            thread_id=_THREAD,
            metadata={"locale": "en"},
        )


@dataclass(frozen=True)
class _Policy:
    case: _Case

    async def get_dm_policy(self, channel: str) -> DmPolicy:
        return DmPolicy.OPEN

    async def get_group_policy(self, channel: str) -> GroupPolicy:
        return self.case.group

    async def get_group_trigger(self, channel: str) -> tuple[GroupTriggerMode, list[str]]:
        return self.case.trigger, ["/ask "]

    async def get_reaction_level(self, channel: str) -> ReactionLevel:
        return ReactionLevel.SIMPLE

    async def get_enabled_groups(self) -> set[str]:
        return {_CHAT} if self.case.chat_enabled else set()

    async def get_free_response_chats(self, channel: str) -> set[str]:
        return {_CHAT} if self.case.free_response else set()

    async def get_guest_mode(self, channel: str) -> bool:
        return False

    async def get_default_user_id(self) -> str | None:
        return "owner"


def _cases() -> Iterator[_Case]:
    for group, enabled, (trigger, free_response), content, mentioned, thread_active, is_bot in itertools.product(
        (GroupPolicy.OPEN, GroupPolicy.DISABLED),
        (True, False),
        (
            (GroupTriggerMode.MENTION_ONLY, False),
            (GroupTriggerMode.PREFIX, False),
            (GroupTriggerMode.ALL, False),
            (GroupTriggerMode.MENTION_ONLY, True),
        ),
        ("hello", "/ask hello", "/mute"),
        (False, True),
        (False, True),
        (False, True),
    ):
        yield _Case(group, enabled, trigger, free_response, content, mentioned, thread_active, is_bot)


CASES = list(_cases())


def _resolver(case: _Case) -> PolicyResolver:
    fx = MagicMock(spec=MessageEffects)
    fx.send_mute_reply = AsyncMock()
    resolver = PolicyResolver(
        pairing=_Pairing(),
        policy=_Policy(case),
        context_buffer=GroupContextBuffer(),
        fx=fx,
        get_channel=lambda _name: MagicMock(),
    )
    if case.thread_active:
        resolver._tracker.activate(f"{_CHANNEL}:{_CHAT}:{_THREAD}")
    return resolver


@pytest.fixture
def ledger() -> Iterator[AsyncMock]:
    with patch(_RECORD_INBOUND, new=AsyncMock()) as record, patch(_MUTE_THREAD):
        yield record


async def _is_recorded_as_chatter(case: _Case, ledger: AsyncMock) -> bool:
    """Whether ``resolve_group_user`` took the path that keeps a message without starting a turn."""
    ledger.reset_mock()
    await _resolver(case).resolve_group_user(case.message)
    await asyncio.sleep(0)
    return [call.kwargs["is_trigger"] for call in ledger.call_args_list] == [False]


@pytest.mark.parametrize("case", CASES, ids=lambda case: case.id)
async def test_chatter_verdict_matches_the_turn_decision(case: _Case, ledger: AsyncMock) -> None:
    chatter = await _resolver(case).is_group_chatter(case.message)

    if not case.admitted:
        assert chatter is False, "a chat the group gates refuse keeps the normal path"
        return
    assert chatter is await _is_recorded_as_chatter(case, ledger)


async def test_asking_for_the_verdict_changes_nothing(ledger: AsyncMock) -> None:
    case = _Case(GroupPolicy.OPEN, True, GroupTriggerMode.MENTION_ONLY, False, "/mute", False, True, False)
    resolver = _resolver(case)

    assert await resolver.is_group_chatter(case.message) is False
    assert resolver._tracker.is_active(f"{_CHANNEL}:{_CHAT}:{_THREAD}"), "the mute word must not mute the thread"
    ledger.assert_not_called()


async def test_the_matrix_reaches_both_verdicts_in_an_admitted_chat() -> None:
    """A matrix that only ever answered one way would let the comparison above pass whatever the code did."""
    verdicts = {await _resolver(case).is_group_chatter(case.message) for case in CASES if case.admitted}

    assert verdicts == {True, False}
