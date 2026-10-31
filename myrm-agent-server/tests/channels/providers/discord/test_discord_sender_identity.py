"""What the Discord adapter emits is judged by the router's resolvers, so a sender the policy does not admit gets no turn.

``user_id`` is the identity the resolvers assign; they take one a message carries only from a control-plane forward.
The adapter names its author only through ``sender_id`` and leaves the rest to the router. These tests wire a real
adapter to a real bus, router and resolvers (the stores behind them are in memory) and follow what each entry point of
the adapter produces: a DM, a voice transcript, a spoken utterance, a /voice command.
"""

from __future__ import annotations

import itertools
from collections.abc import AsyncIterator, Awaitable, Callable
from dataclasses import dataclass, field
from datetime import UTC, datetime
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.core.bus import MessageBus
from app.channels.protocols.pairing import DmPolicy, GroupPolicy, PairingRole, PairingStatus
from app.channels.providers.discord.channel import DiscordChannel
from app.channels.routing.channel_data_plane import ChannelDataPlaneService
from app.channels.routing.identity_scope import is_untrusted_sender
from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage
from tests.channels.providers.discord.gateway_testkit import start_channel
from tests.channels.providers.discord.voice.listen_testkit import listen_once

_GUILD = 7
_ENABLED_TEXT_CHANNEL = 456
_STRANGER = 123
_MEMBER = 55
_OWNER = 1
_CHANNEL = "discord"  # the channel name pairing rows are keyed by
_OWNER_IDENTITY = "sandbox"  # what SqlPairingStore.resolve returns for an ACTIVE admin pairing
_MEMBER_IDENTITY = f"paired_member_{_CHANNEL}_{_MEMBER}"  # ... and for any other ACTIVE pairing
_ids = itertools.count(1000)


@dataclass
class _Rig:
    channel: DiscordChannel
    router: AgentRouter
    commands: dict[str, Callable[..., Awaitable[None]]]
    emitted: list[InboundMessage] = field(default_factory=list)
    pairings: dict[tuple[str, str], PairingRole] = field(default_factory=dict)

    def pair(self, author_id: int, role: PairingRole) -> None:
        self.pairings[(_CHANNEL, str(author_id))] = role


@pytest.fixture
async def rig(monkeypatch: pytest.MonkeyPatch) -> _Rig:
    monkeypatch.setattr(ChannelDataPlaneService, "record_inbound", AsyncMock())
    monkeypatch.setattr("app.channels.providers.discord.voice.manager._LISTEN_POLL_INTERVAL", 0)
    commands: dict[str, Callable[..., Awaitable[None]]] = {}
    channel = await start_channel(monkeypatch, commands)
    bus = MessageBus()
    bus.register_channel(channel)
    pairings: dict[tuple[str, str], PairingRole] = {}

    policy = MagicMock()
    policy.get_dm_policy = AsyncMock(return_value=DmPolicy.ALLOWLIST)
    policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
    policy.get_enabled_groups = AsyncMock(return_value={str(_ENABLED_TEXT_CHANNEL)})
    policy.get_guest_mode = AsyncMock(return_value=False)
    policy.get_default_user_id = AsyncMock(return_value=_OWNER_IDENTITY)

    async def resolve(channel: str, sender_id: str) -> str | None:
        role = pairings.get((channel, sender_id))
        if role is None:
            return None
        return _OWNER_IDENTITY if role == PairingRole.ADMIN else f"paired_member_{channel}_{sender_id}"

    async def detail(channel: str, sender_id: str) -> tuple[PairingStatus, PairingRole, None] | None:
        role = pairings.get((channel, sender_id))
        return None if role is None else (PairingStatus.ACTIVE, role, None)

    async def status(channel: str, sender_id: str) -> PairingStatus | None:
        return PairingStatus.ACTIVE if (channel, sender_id) in pairings else None

    pairing = MagicMock()
    pairing.resolve = AsyncMock(side_effect=resolve)
    pairing.get_pairing_detail = AsyncMock(side_effect=detail)
    pairing.get_status = AsyncMock(side_effect=status)
    pairing.touch_display_name = AsyncMock()
    router = AgentRouter(bus=bus, pairing_store=pairing, agent_executor=MagicMock(), policy_provider=policy)

    result = _Rig(channel, router, commands, pairings=pairings)

    async def capture(msg: InboundMessage) -> None:
        result.emitted.append(msg)

    channel.set_inbound_handler(capture)
    return result


async def _dm_from(rig: _Rig, author_id: int) -> InboundMessage:
    message = MagicMock()
    message.author.bot = False
    message.author.id = author_id
    message.author.display_name = "Someone"
    message.guild = None
    message.channel.id = 789
    message.id = next(_ids)
    message.content = "hello"
    message.attachments = []
    message.reference = None
    message.mentions = []
    await rig.channel._on_message(message)
    return rig.emitted[-1]


async def _click_from(rig: _Rig, author_id: int) -> InboundMessage:
    interaction = MagicMock()
    interaction.type = discord.InteractionType.component
    interaction.response.defer = AsyncMock()
    interaction.data = {"custom_id": "act:approval:approve:1"}
    interaction.user.id = author_id
    interaction.user.display_name = "Someone"
    interaction.channel_id = 789
    interaction.guild_id = None
    interaction.id = next(_ids)
    await rig.channel._on_interaction(interaction)
    return rig.emitted[-1]


async def _transcript_from(rig: _Rig, author_id: int) -> InboundMessage:
    await rig.channel._on_voice_input(_ENABLED_TEXT_CHANNEL, author_id, "hello", "Someone")
    return rig.emitted[-1]


async def _turn_identity(rig: _Rig, msg: InboundMessage) -> str | None:
    """The identity the router's resolver gives a DM-shaped message, as the router does before a turn starts."""
    return await rig.router._resolver.resolve_dm_user(msg)


@pytest.mark.parametrize("emit", [_dm_from, _click_from, _transcript_from])
async def test_a_stranger_gets_no_turn_from_a_dm_a_button_click_or_a_voice_transcript(
    rig: _Rig, emit: Callable[..., Awaitable[InboundMessage]]
) -> None:
    assert await _turn_identity(rig, await emit(rig, _STRANGER)) is None


@pytest.mark.parametrize("emit", [_dm_from, _transcript_from])
async def test_a_paired_member_runs_fenced_as_that_member(rig: _Rig, emit: Callable[..., Awaitable[InboundMessage]]) -> None:
    rig.pair(_MEMBER, PairingRole.MEMBER)
    msg = await emit(rig, _MEMBER)

    identity = await _turn_identity(rig, msg)

    assert identity == _MEMBER_IDENTITY
    assert is_untrusted_sender(identity, msg)


@pytest.mark.parametrize("emit", [_dm_from, _transcript_from])
async def test_the_owner_runs_as_the_owner(rig: _Rig, emit: Callable[..., Awaitable[InboundMessage]]) -> None:
    rig.pair(_OWNER, PairingRole.ADMIN)
    msg = await emit(rig, _OWNER)

    identity = await _turn_identity(rig, msg)

    assert identity == _OWNER_IDENTITY
    assert not is_untrusted_sender(identity, msg)


async def _transcribed(rig: _Rig, author_id: int) -> bool:
    """Whether the voice channel's listen loop sends this speaker's utterance to speech-to-text."""
    manager = rig.channel._voice_manager
    assert manager is not None
    process, _ = await listen_once(
        manager, [(author_id, b"\x00" * 192100)], guild_id=_GUILD, text_channel_id=_ENABLED_TEXT_CHANNEL
    )
    return process.await_count == 1


async def test_a_speaker_who_is_not_paired_is_not_transcribed_even_in_an_enabled_channel(rig: _Rig) -> None:
    assert await _transcribed(rig, _STRANGER) is False


async def test_a_paired_member_and_the_owner_are_transcribed(rig: _Rig) -> None:
    rig.pair(_MEMBER, PairingRole.MEMBER)
    rig.pair(_OWNER, PairingRole.ADMIN)

    assert (await _transcribed(rig, _MEMBER), await _transcribed(rig, _OWNER)) == (True, True)


def _interaction(*, user_id: int, in_guild: bool = True, channel_id: int = _ENABLED_TEXT_CHANNEL) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.user.display_name = "Someone"
    interaction.guild.id = _GUILD if in_guild else None
    interaction.guild_id = _GUILD if in_guild else None
    interaction.channel_id = channel_id
    interaction.locale = discord.Locale.american_english
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def _voice_command_reply(rig: _Rig, interaction: MagicMock) -> str:
    await rig.commands["voice"](interaction, "status", None)
    sent = interaction.response.send_message.await_args_list + interaction.followup.send.await_args_list
    assert len(sent) == 1
    reply = sent[0].args[0]
    assert isinstance(reply, str)
    return reply


async def test_a_member_of_an_enabled_channel_may_use_the_voice_command_without_a_pairing(rig: _Rig) -> None:
    reply = await _voice_command_reply(rig, _interaction(user_id=_STRANGER))

    assert reply.startswith("Voice status")


async def test_a_stranger_is_refused_the_voice_command_in_a_channel_the_policy_does_not_enable(rig: _Rig) -> None:
    reply = await _voice_command_reply(rig, _interaction(user_id=_STRANGER, channel_id=999))

    assert reply.startswith("You are not allowed")


async def test_the_owner_may_use_the_voice_command_in_a_channel_the_policy_does_not_enable(rig: _Rig) -> None:
    rig.pair(_OWNER, PairingRole.ADMIN)

    reply = await _voice_command_reply(rig, _interaction(user_id=_OWNER, channel_id=999))

    assert reply.startswith("Voice status")


async def test_a_stranger_is_refused_the_voice_command_in_a_dm(rig: _Rig) -> None:
    reply = await _voice_command_reply(rig, _interaction(user_id=_STRANGER, in_guild=False))

    assert reply.startswith("You are not allowed")


async def test_the_history_fetched_for_a_backfill_names_its_authors_only_by_sender_id(rig: _Rig) -> None:
    raw = MagicMock()
    raw.author.bot = False
    raw.author.id = _STRANGER
    raw.author.display_name = "Someone"
    raw.content = "earlier"
    raw.attachments = []
    raw.reference = None
    raw.guild = None
    raw.id = next(_ids)
    raw.created_at = datetime.now(UTC)

    async def history(limit: int) -> AsyncIterator[MagicMock]:
        yield raw

    chat = MagicMock()
    chat.history = history
    rig.channel._resolve_channel = AsyncMock(return_value=chat)  # type: ignore[method-assign]

    fetched = await rig.channel.fetch_history("789")

    assert [(m.sender_id, m.user_id) for m in fetched] == [(str(_STRANGER), None)]
