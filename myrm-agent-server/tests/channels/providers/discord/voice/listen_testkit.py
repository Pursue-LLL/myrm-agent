"""Drives one pass of a VoiceManager's listen loop over given utterances, with the STT entry point stubbed."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.manager import VoiceManager, _GuildVoiceState

STALE_SPEECH_AT = 5.0


async def listen_once(
    manager: VoiceManager,
    utterances: list[tuple[int, bytes]],
    *,
    guild_id: int,
    text_channel_id: int,
) -> tuple[AsyncMock, _GuildVoiceState]:
    """Run the listen loop until ``utterances`` are consumed; return the STT entry point's mock and the session.

    The session starts with ``last_speech_at`` at ``STALE_SPEECH_AT``, so a test can tell whether an utterance was
    taken as speech; the voice timeout is off, or that old timestamp would end the session. The caller sets the poll
    interval to zero to keep the pass instant.
    """
    manager._voice_timeout = 0
    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    receiver = MagicMock()
    receiver.running = True
    pending = [list(utterances)]

    def check_silence() -> list[tuple[int, bytes]]:
        if pending:
            return pending.pop()
        receiver.running = False
        return []

    receiver.check_silence = check_silence
    state = _GuildVoiceState(voice_client=voice_client, receiver=receiver, text_channel_id=text_channel_id)
    state.last_speech_at = STALE_SPEECH_AT
    manager._guilds[guild_id] = state
    with patch.object(manager._input, "process", new_callable=AsyncMock) as process:
        await manager._listen_loop(guild_id)
    return process, state
