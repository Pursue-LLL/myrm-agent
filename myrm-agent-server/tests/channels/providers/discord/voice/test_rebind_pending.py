"""Binding a session to another text channel drops the speech the receiver has not yet delivered.

A poll of the listen loop delivers a finished utterance under the binding the session has at that poll. Speech still
buffered when ``/voice join`` moves the session to another text channel was said for the conversation it was captured
under; delivered after the move it would become a turn in a conversation that was never the speaker's, with its history,
skills and reply target. Speech that finished before the move is already in a poll batch and keeps its binding.
"""

from __future__ import annotations

import time
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.manager import VoiceManager, _GuildVoiceState
from app.channels.providers.discord.voice.receiver import (
    _BYTES_PER_SECOND,
    _MIN_SPEECH_DURATION,
    _SILENCE_THRESHOLD,
    VoiceReceiver,
)
from tests.channels.providers.discord.voice.receiver_testkit import make_mock_vc

_GUILD = 1
_SPEAKER = 42
_SSRC = 100
_VOICE_CHANNEL = 123
_TEXT_CHANNEL = 456
_OTHER_TEXT_CHANNEL = 789


def _hold_finished_speech(receiver: VoiceReceiver) -> None:
    """Buffer one utterance that the next silence check reports as finished."""
    receiver._buffers[_SSRC] = bytearray(b"\x00" * (int(_MIN_SPEECH_DURATION * _BYTES_PER_SECOND) + 100))
    receiver._last_packet_time[_SSRC] = time.monotonic() - _SILENCE_THRESHOLD - 0.1


def _session(text_channel_id: int) -> tuple[VoiceManager, VoiceReceiver, MagicMock]:
    """A manager with one joined guild whose receiver already knows the speaker, and the voice channel it sits in."""
    voice_channel = MagicMock()
    voice_channel.guild.id = _GUILD
    voice_channel.id = _VOICE_CHANNEL
    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.channel = voice_channel
    voice_client.move_to = AsyncMock(side_effect=lambda channel: setattr(voice_client, "channel", channel))
    receiver = VoiceReceiver(make_mock_vc())
    receiver._ssrc_to_user[_SSRC] = _SPEAKER

    manager = VoiceManager(MagicMock(), voice_timeout=0)
    manager._guilds[_GUILD] = _GuildVoiceState(voice_client=voice_client, receiver=receiver, text_channel_id=text_channel_id)
    return manager, receiver, voice_channel


def _finished_speakers(receiver: VoiceReceiver) -> list[int]:
    return [user_id for user_id, _ in receiver.check_silence()]


@pytest.mark.parametrize("bound_to", [_TEXT_CHANNEL, 0], ids=["another_text_channel", "no_binding_yet"])
async def test_binding_to_another_text_channel_drops_the_speech_not_yet_delivered(bound_to: int) -> None:
    manager, receiver, voice_channel = _session(bound_to)
    _hold_finished_speech(receiver)

    assert await manager.join(voice_channel, text_channel_id=_OTHER_TEXT_CHANNEL)

    assert _finished_speakers(receiver) == []
    assert manager._guilds[_GUILD].text_channel_id == _OTHER_TEXT_CHANNEL


async def test_moving_to_another_voice_channel_with_a_new_text_channel_drops_it_too() -> None:
    manager, receiver, _ = _session(_TEXT_CHANNEL)
    other_voice_channel = MagicMock()
    other_voice_channel.guild.id = _GUILD
    other_voice_channel.id = _VOICE_CHANNEL + 1
    _hold_finished_speech(receiver)

    assert await manager.join(other_voice_channel, text_channel_id=_OTHER_TEXT_CHANNEL)

    assert _finished_speakers(receiver) == []
    assert manager._guilds[_GUILD].text_channel_id == _OTHER_TEXT_CHANNEL


@pytest.mark.parametrize("text_channel_id", [_TEXT_CHANNEL, 0], ids=["same_text_channel", "no_text_channel"])
async def test_a_join_that_keeps_the_binding_keeps_the_speech(text_channel_id: int) -> None:
    manager, receiver, voice_channel = _session(_TEXT_CHANNEL)
    _hold_finished_speech(receiver)

    assert await manager.join(voice_channel, text_channel_id=text_channel_id)

    assert _finished_speakers(receiver) == [_SPEAKER]
    assert manager._guilds[_GUILD].text_channel_id == _TEXT_CHANNEL


async def test_speech_after_the_rebind_is_delivered() -> None:
    manager, receiver, voice_channel = _session(_TEXT_CHANNEL)
    _hold_finished_speech(receiver)
    await manager.join(voice_channel, text_channel_id=_OTHER_TEXT_CHANNEL)

    _hold_finished_speech(receiver)

    assert _finished_speakers(receiver) == [_SPEAKER]
