"""The /voice command answers in the language Discord reports for the caller, and says what really happened.

Every reply is a ``voice_*`` message of the channel catalog rendered for the interaction's locale; a language the catalog
has no file for is answered in English, like every other channel reply. A reply never claims more than happened: leaving
while the bot is in no voice channel says so instead of reporting a leave.
"""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.voice.manager import _GuildVoiceState
from tests.channels.providers.discord.gateway_testkit import start_channel

_GUILD = 7
_TEXT_CHANNEL = 456


@dataclass
class _Rig:
    channel: DiscordChannel
    command: Callable[..., Awaitable[None]]
    voice_client: MagicMock
    join_voice: AsyncMock


@pytest.fixture
async def rig(monkeypatch: pytest.MonkeyPatch) -> _Rig:
    """The owner of the bot, admitted, in a guild where the bot sits in a voice channel."""
    commands: dict[str, Callable[..., Awaitable[None]]] = {}
    channel = await start_channel(monkeypatch, commands)
    assert channel._voice_manager is not None
    channel.set_sender_gate(AsyncMock(return_value=True))
    channel.set_owner_gate(AsyncMock(return_value=True))
    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.disconnect = AsyncMock()
    channel._voice_manager._guilds[_GUILD] = _GuildVoiceState(voice_client=voice_client, receiver=MagicMock())
    join_voice = AsyncMock(return_value=True)
    monkeypatch.setattr(channel, "join_voice", join_voice)
    return _Rig(channel, commands["voice"], voice_client, join_voice)


def _interaction(locale: discord.Locale = discord.Locale.american_english, *, in_guild: bool = True) -> MagicMock:
    interaction = MagicMock()
    interaction.user.id = 123
    interaction.user.display_name = "Owner"
    interaction.guild = MagicMock() if in_guild else None
    interaction.guild_id = _GUILD if in_guild else None
    if in_guild:
        interaction.guild.id = _GUILD
    interaction.channel_id = _TEXT_CHANNEL
    interaction.locale = locale
    interaction.response.defer = AsyncMock()
    interaction.followup.send = AsyncMock()
    return interaction


def _voice_channel(name: str) -> MagicMock:
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.name = name
    return channel


async def _reply_to(rig: _Rig, action: str, interaction: MagicMock, target: MagicMock | None = None) -> str:
    """The single reply the command sent, which only its caller can see."""
    await rig.command(interaction, action, target)
    sent = interaction.followup.send.await_args_list
    assert len(sent) == 1
    assert sent[0].kwargs["ephemeral"] is True
    reply = sent[0].args[0]
    assert isinstance(reply, str)
    return reply


async def test_the_command_says_so_when_voice_is_not_enabled(rig: _Rig) -> None:
    rig.channel._voice_manager = None

    assert await _reply_to(rig, "status", _interaction()) == "Voice is not enabled."


async def test_the_command_says_so_when_it_is_used_outside_a_server(rig: _Rig) -> None:
    assert await _reply_to(rig, "status", _interaction(in_guild=False)) == "This command can only be used in a server."


async def test_a_join_without_a_voice_channel_asks_for_one(rig: _Rig) -> None:
    assert await _reply_to(rig, "join", _interaction()) == "Please specify a voice channel or join one first."
    rig.join_voice.assert_not_awaited()


async def test_a_join_names_the_channel_it_joined(rig: _Rig) -> None:
    target = _voice_channel("General")

    assert await _reply_to(rig, "join", _interaction(), target) == "Joined **General**"

    rig.join_voice.assert_awaited_once_with(target, text_channel_id=_TEXT_CHANNEL)


async def test_a_join_that_did_not_happen_says_so(rig: _Rig) -> None:
    rig.join_voice.return_value = False

    assert await _reply_to(rig, "join", _interaction(), _voice_channel("General")) == "Failed to join voice channel."


async def test_a_leave_leaves_the_voice_channel(rig: _Rig) -> None:
    assert await _reply_to(rig, "leave", _interaction()) == "Left voice channel."

    rig.voice_client.disconnect.assert_awaited_once_with(force=True)


async def test_a_session_that_is_reconnecting_is_still_left(rig: _Rig) -> None:
    rig.voice_client.is_connected.return_value = False

    assert await _reply_to(rig, "leave", _interaction()) == "Left voice channel."


async def test_a_leave_while_the_bot_is_in_no_voice_channel_says_so_and_leaves_nothing(
    rig: _Rig, monkeypatch: pytest.MonkeyPatch
) -> None:
    assert rig.channel._voice_manager is not None
    rig.channel._voice_manager._guilds.clear()
    leave_voice = AsyncMock()
    monkeypatch.setattr(rig.channel, "leave_voice", leave_voice)

    assert await _reply_to(rig, "leave", _interaction()) == "Not in a voice channel."

    leave_voice.assert_not_awaited()


async def test_the_status_of_a_session_that_is_not_connected_says_so(rig: _Rig) -> None:
    rig.voice_client.is_connected.return_value = False

    assert await _reply_to(rig, "status", _interaction()) == "Voice status: **Not connected**"


@pytest.mark.parametrize(
    ("locale", "reply"),
    [
        (discord.Locale.american_english, "Left voice channel."),
        (discord.Locale.british_english, "Left voice channel."),
        (discord.Locale.chinese, "已离开语音频道。"),
        (discord.Locale.taiwan_chinese, "已離開語音頻道。"),
        (discord.Locale.japanese, "音声チャンネルから退出しました。"),
        (discord.Locale.korean, "Left voice channel."),
    ],
    ids=["en-US", "en-GB", "zh-CN", "zh-TW", "ja", "ko-has-no-catalog"],
)
async def test_a_reply_is_worded_in_the_callers_discord_language(rig: _Rig, locale: discord.Locale, reply: str) -> None:
    assert await _reply_to(rig, "leave", _interaction(locale)) == reply


async def test_a_reply_that_names_the_channel_keeps_the_name_in_every_language(rig: _Rig) -> None:
    reply = await _reply_to(rig, "join", _interaction(discord.Locale.japanese), _voice_channel("General"))

    assert reply == "**General** に参加しました"


async def test_a_refusal_is_worded_in_the_callers_discord_language(rig: _Rig) -> None:
    rig.channel.set_sender_gate(AsyncMock(return_value=False))

    reply = await _reply_to(rig, "status", _interaction(discord.Locale.chinese))

    assert reply == "你没有权限使用此命令，请联系机器人所有者授权。"
    rig.voice_client.disconnect.assert_not_awaited()


async def test_the_owner_only_refusal_is_worded_in_the_callers_discord_language(rig: _Rig) -> None:
    rig.channel.set_owner_gate(AsyncMock(return_value=False))

    reply = await _reply_to(rig, "join", _interaction(discord.Locale.japanese), _voice_channel("General"))

    assert reply == "ボットを音声チャンネルに参加・退出させられるのは、ボットの所有者だけです。"
    rig.join_voice.assert_not_awaited()
