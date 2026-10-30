"""The /voice slash command moves the bot without a message, so it asks the access policy about the caller first.

A message from a user reaches the agent only through the router's admission; a slash command is handled by the host
itself and would otherwise skip it. The caller must be one the policy admits for that chat (the owner always is), and a
channel nobody wired to a policy admits no one.
"""

from __future__ import annotations

import logging
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.voice.manager import _GuildVoiceState
from app.channels.types import InboundMessage
from tests.channels.providers.discord.gateway_testkit import start_channel

_GUILD = 7
_ACTIONS = ["join", "leave", "status"]


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
    sent = interaction.response.send_message.await_args_list + interaction.followup.send.await_args_list
    return [call.args[0] for call in sent]


@pytest.mark.parametrize("action", _ACTIONS)
async def test_a_caller_the_policy_does_not_admit_is_refused_and_nothing_happens(rig: _Rig, action: str) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=False))
    interaction = _interaction()

    await _run(rig, action, interaction)

    rig.voice_client.disconnect.assert_not_awaited()
    rig.channel.join_voice.assert_not_awaited()  # type: ignore[attr-defined]
    assert _replies(interaction) == ["You are not allowed to use this command."]
    assert interaction.response.send_message.await_args.kwargs["ephemeral"] is True


async def test_a_channel_nobody_wired_to_a_policy_refuses_every_caller(rig: _Rig) -> None:
    interaction = _interaction()

    await _run(rig, "leave", interaction)

    rig.voice_client.disconnect.assert_not_awaited()
    assert _replies(interaction) == ["You are not allowed to use this command."]


async def test_an_admitted_caller_leaves_the_voice_channel(rig: _Rig) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))

    await _run(rig, "leave", _interaction())

    rig.voice_client.disconnect.assert_awaited_once_with(force=True)


async def test_an_admitted_caller_joins_a_voice_channel(rig: _Rig) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))

    await _run(rig, "join", _interaction())

    rig.channel.join_voice.assert_awaited_once()  # type: ignore[attr-defined]


async def test_an_admitted_caller_reads_the_voice_status(rig: _Rig) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=True))
    interaction = _interaction()

    await _run(rig, "status", interaction)

    assert _replies(interaction) == ["Voice status: **Connected**"]


async def test_the_policy_judges_the_caller_in_the_chat_the_command_came_from(rig: _Rig) -> None:
    gate = AsyncMock(return_value=True)
    rig.channel.set_sender_gate(gate)

    await _run(rig, "status", _interaction(user_id=123))

    gate.assert_awaited_once()
    assert gate.await_args is not None
    msg: InboundMessage = gate.await_args.args[0]
    assert (msg.channel, msg.sender_id, msg.user_id, msg.chat_id, msg.is_group) == (rig.channel.name, "123", "123", "456", True)


async def test_a_refused_caller_is_logged(rig: _Rig, caplog: pytest.LogCaptureFixture) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=False))

    with caplog.at_level(logging.WARNING, logger="app.channels.providers.discord.voice_control"):
        await _run(rig, "leave", _interaction(user_id=123))

    assert [(r.levelno, "123" in r.getMessage()) for r in caplog.records] == [(logging.WARNING, True)]
