"""The /voice slash command moves the bot without a message, so it asks the access policy about the caller first.

A message from a user reaches the agent only through the router's admission; a slash command is handled by the host
itself and would otherwise skip it. The caller must be one the policy admits for that chat (the owner always is), and a
channel nobody wired to a policy admits no one. Joining and leaving act on the owner's voice session rather than on the
caller's own conversation, as a system command does, so they also need the owner; reading the status needs only the
admission. Discord gives the command three seconds to be acknowledged and the policy reads its stores, so the command is
acknowledged before the policy is asked and every answer follows up.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.core.bus import MessageBus
from app.channels.protocols.pairing import GroupPolicy, PairingRole, PairingStatus
from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.voice.manager import _GuildVoiceState
from app.channels.routing.router import AgentRouter
from app.channels.types import InboundMessage
from tests.channels.providers.discord.gateway_testkit import start_channel

_GUILD = 7
_ACTIONS = ["join", "leave", "status"]
_REFUSAL = "You are not allowed to use this command. Ask the bot owner to give you access."
_OWNER_ONLY = "Only the bot owner can make the bot join or leave a voice channel."
_OWNER, _MEMBER, _STRANGER = 1, 2, 3


@dataclass
class _Rig:
    channel: DiscordChannel
    command: Callable[..., Awaitable[None]]
    voice_client: MagicMock


@pytest.fixture
async def rig(monkeypatch: pytest.MonkeyPatch) -> _Rig:
    commands: dict[str, Callable[..., Awaitable[None]]] = {}
    channel = await start_channel(monkeypatch, commands)
    assert channel._voice_manager is not None
    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.disconnect = AsyncMock()
    channel._voice_manager._guilds[_GUILD] = _GuildVoiceState(voice_client=voice_client, receiver=MagicMock())
    channel.join_voice = AsyncMock(return_value=True)  # type: ignore[method-assign]
    return _Rig(channel, commands["voice"], voice_client)


def _interaction(*, user_id: int = 123) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = user_id
    interaction.user.display_name = "Member"
    interaction.guild.id = _GUILD
    interaction.guild_id = _GUILD
    interaction.channel_id = 456
    interaction.response.send_message = AsyncMock()
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


async def _run(rig: _Rig, action: str, interaction: MagicMock) -> None:
    target = MagicMock(spec=discord.VoiceChannel) if action == "join" else None
    await rig.command(interaction, action, target)


def _replies(interaction: MagicMock) -> list[str]:
    assert interaction.response.send_message.await_count == 0
    return [call.args[0] for call in interaction.followup.send.await_args_list]


@pytest.mark.parametrize("action", _ACTIONS)
async def test_a_caller_the_policy_does_not_admit_is_refused_and_nothing_happens(rig: _Rig, action: str) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=False))
    rig.channel.set_owner_gate(AsyncMock(return_value=True))
    interaction = _interaction()

    await _run(rig, action, interaction)

    rig.voice_client.disconnect.assert_not_awaited()
    rig.channel.join_voice.assert_not_awaited()  # type: ignore[attr-defined]
    assert _replies(interaction) == [_REFUSAL]
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True


async def test_a_channel_nobody_wired_to_a_policy_refuses_every_caller(rig: _Rig) -> None:
    interaction = _interaction()

    await _run(rig, "leave", interaction)

    rig.voice_client.disconnect.assert_not_awaited()
    assert _replies(interaction) == [_REFUSAL]


async def test_the_owner_leaves_the_voice_channel(rig: _Rig) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))
    rig.channel.set_owner_gate(AsyncMock(return_value=True))

    await _run(rig, "leave", _interaction())

    rig.voice_client.disconnect.assert_awaited_once_with(force=True)


async def test_the_owner_joins_a_voice_channel(rig: _Rig) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))
    rig.channel.set_owner_gate(AsyncMock(return_value=True))

    await _run(rig, "join", _interaction())

    rig.channel.join_voice.assert_awaited_once()  # type: ignore[attr-defined]


async def test_an_admitted_caller_reads_the_voice_status(rig: _Rig) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))
    interaction = _interaction()

    await _run(rig, "status", interaction)

    assert _replies(interaction) == ["Voice status: **Connected**"]


@pytest.mark.parametrize("action", ["join", "leave"])
async def test_an_admitted_caller_who_is_not_the_owner_cannot_move_the_bot(rig: _Rig, action: str) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))
    rig.channel.set_owner_gate(AsyncMock(return_value=False))
    interaction = _interaction()

    await _run(rig, action, interaction)

    rig.voice_client.disconnect.assert_not_awaited()
    rig.channel.join_voice.assert_not_awaited()  # type: ignore[attr-defined]
    assert _replies(interaction) == [_OWNER_ONLY]
    assert interaction.followup.send.await_args.kwargs["ephemeral"] is True


async def test_an_admitted_caller_who_is_not_the_owner_reads_the_voice_status(rig: _Rig) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))
    owner_gate = AsyncMock(return_value=False)
    rig.channel.set_owner_gate(owner_gate)
    interaction = _interaction()

    await _run(rig, "status", interaction)

    assert _replies(interaction) == ["Voice status: **Connected**"]
    owner_gate.assert_not_awaited()


@pytest.mark.parametrize("action", ["join", "leave"])
async def test_a_channel_nobody_wired_to_an_owner_check_refuses_join_and_leave_to_everyone(rig: _Rig, action: str) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))
    interaction = _interaction()

    await _run(rig, action, interaction)

    rig.voice_client.disconnect.assert_not_awaited()
    rig.channel.join_voice.assert_not_awaited()  # type: ignore[attr-defined]
    assert _replies(interaction) == [_OWNER_ONLY]


async def test_an_action_not_known_to_be_read_only_needs_the_owner(rig: _Rig) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))
    rig.channel.set_owner_gate(AsyncMock(return_value=False))
    interaction = _interaction()

    await rig.command(interaction, "move", None)

    assert _replies(interaction) == [_OWNER_ONLY]


async def test_a_caller_the_policy_does_not_admit_is_not_asked_whether_they_are_the_owner(rig: _Rig) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=False))
    owner_gate = AsyncMock(return_value=True)
    rig.channel.set_owner_gate(owner_gate)

    await _run(rig, "leave", _interaction())

    owner_gate.assert_not_awaited()


async def test_the_owner_is_judged_by_the_sender_id_in_the_chat_the_command_came_from(rig: _Rig) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))
    owner_gate = AsyncMock(return_value=True)
    rig.channel.set_owner_gate(owner_gate)

    await _run(rig, "leave", _interaction(user_id=123))

    owner_gate.assert_awaited_once()
    assert owner_gate.await_args is not None
    msg: InboundMessage = owner_gate.await_args.args[0]
    assert (msg.channel, msg.sender_id, msg.chat_id, msg.is_group, msg.user_id) == (rig.channel.name, "123", "456", True, None)


@pytest.mark.parametrize("action", _ACTIONS)
async def test_the_command_is_acknowledged_before_the_policy_is_asked(rig: _Rig, action: str) -> None:
    interaction = _interaction()
    acknowledged_when_asked: list[int] = []

    async def gate(_msg: InboundMessage) -> bool:
        acknowledged_when_asked.append(interaction.response.defer.await_count)
        return True

    rig.channel.set_sender_gate(gate)

    await _run(rig, action, interaction)

    assert acknowledged_when_asked == [1]
    interaction.response.defer.assert_awaited_once_with(ephemeral=True)


async def test_the_policy_judges_the_caller_in_the_chat_the_command_came_from(rig: _Rig) -> None:
    gate = AsyncMock(return_value=True)
    rig.channel.set_sender_gate(gate)

    await _run(rig, "status", _interaction(user_id=123))

    gate.assert_awaited_once()
    assert gate.await_args is not None
    msg: InboundMessage = gate.await_args.args[0]
    assert (msg.channel, msg.sender_id, msg.chat_id, msg.is_group) == (rig.channel.name, "123", "456", True)


async def test_the_caller_is_named_only_by_the_sender_id_so_the_policy_decides_who_they_are(rig: _Rig) -> None:
    gate = AsyncMock(return_value=True)
    rig.channel.set_sender_gate(gate)

    await _run(rig, "status", _interaction(user_id=123))

    assert gate.await_args is not None
    assert gate.await_args.args[0].user_id is None


async def test_a_refused_caller_is_logged_with_the_chat_the_command_came_from(
    rig: _Rig, caplog: pytest.LogCaptureFixture
) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=False))

    with caplog.at_level(logging.WARNING, logger="app.channels.providers.discord.voice_control"):
        await _run(rig, "leave", _interaction(user_id=123))

    assert [(r.levelno, "123" in r.getMessage(), "456" in r.getMessage()) for r in caplog.records] == [
        (logging.WARNING, True, True)
    ]


async def test_a_refused_non_owner_is_logged_with_the_chat_the_command_came_from(
    rig: _Rig, caplog: pytest.LogCaptureFixture
) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))
    rig.channel.set_owner_gate(AsyncMock(return_value=False))

    with caplog.at_level(logging.WARNING, logger="app.channels.providers.discord.voice_control"):
        await _run(rig, "leave", _interaction(user_id=123))

    assert [(r.levelno, "123" in r.getMessage(), "456" in r.getMessage()) for r in caplog.records] == [
        (logging.WARNING, True, True)
    ]


def _put_on_a_router_with_the_real_policy(rig: _Rig) -> None:
    """The channel on a bus whose router judges callers by the real policy.

    The chat the command comes from is enabled for every sender; ``_OWNER`` has an ADMIN pairing, ``_MEMBER`` a MEMBER
    pairing and ``_STRANGER`` none.
    """
    policy = MagicMock()
    policy.get_group_policy = AsyncMock(return_value=GroupPolicy.OPEN)
    policy.get_enabled_groups = AsyncMock(return_value={"456"})
    policy.get_guest_mode = AsyncMock(return_value=False)
    pairings = {
        str(_OWNER): (PairingStatus.ACTIVE, PairingRole.ADMIN),
        str(_MEMBER): (PairingStatus.ACTIVE, PairingRole.MEMBER),
    }
    pairing = MagicMock()
    pairing.get_pairing_detail = AsyncMock(side_effect=lambda _channel, sender_id: pairings.get(sender_id))
    bus = MessageBus()
    AgentRouter(bus=bus, pairing_store=pairing, agent_executor=MagicMock(), policy_provider=policy)
    bus.register_channel(rig.channel)


def _took_effect(rig: _Rig, action: str, interaction: MagicMock) -> bool:
    if action == "join":
        return bool(rig.channel.join_voice.await_count == 1)  # type: ignore[attr-defined]
    if action == "leave":
        return bool(rig.voice_client.disconnect.await_count == 1)
    return _replies(interaction) == ["Voice status: **Connected**"]


@pytest.mark.parametrize(
    ("caller", "action", "allowed"),
    [
        (_OWNER, "join", True),
        (_OWNER, "leave", True),
        (_OWNER, "status", True),
        (_MEMBER, "join", False),
        (_MEMBER, "leave", False),
        (_MEMBER, "status", True),
        (_STRANGER, "join", False),
        (_STRANGER, "leave", False),
        (_STRANGER, "status", True),
    ],
    ids=[
        "owner-join",
        "owner-leave",
        "owner-status",
        "paired-member-join",
        "paired-member-leave",
        "paired-member-status",
        "unpaired-member-of-an-enabled-chat-join",
        "unpaired-member-of-an-enabled-chat-leave",
        "unpaired-member-of-an-enabled-chat-status",
    ],
)
async def test_the_real_policy_lets_only_the_owner_join_or_leave_and_any_admitted_caller_read_the_status(
    rig: _Rig, caller: int, action: str, allowed: bool
) -> None:
    _put_on_a_router_with_the_real_policy(rig)
    interaction = _interaction(user_id=caller)

    await _run(rig, action, interaction)

    assert _took_effect(rig, action, interaction) is allowed
    if not allowed:
        assert _replies(interaction) == [_OWNER_ONLY]
