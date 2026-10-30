"""A speaker is transcribed only when the access policy admits them; a refused speaker's audio never reaches STT.

The voice channel can hold people the bot owner never admitted, and every utterance sent to speech-to-text costs a
call and leaves the machine, so the policy is asked before the utterance is processed, not after its transcript is
known.
"""

from __future__ import annotations

import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.manager import VoiceManager, _GuildVoiceState
from tests.channels.providers.discord.voice.listen_testkit import STALE_SPEECH_AT, listen_once

_GUILD = 1
_TEXT_CHANNEL = 789
_PCM = b"\x00" * 192100


@pytest.fixture(autouse=True)
def _no_poll_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.channels.providers.discord.voice.manager._LISTEN_POLL_INTERVAL", 0)


async def _listen(
    manager: VoiceManager, utterances: list[tuple[int, bytes]], *, text_channel_id: int = _TEXT_CHANNEL
) -> tuple[AsyncMock, _GuildVoiceState]:
    return await listen_once(manager, utterances, guild_id=_GUILD, text_channel_id=text_channel_id)


def _manager(gate: AsyncMock | None, **kwargs: object) -> VoiceManager:
    return VoiceManager(MagicMock(), voice_timeout=0, speaker_gate=gate, **kwargs)  # type: ignore[arg-type]


async def test_an_admitted_speaker_is_transcribed_and_keeps_the_session_alive() -> None:
    gate = AsyncMock(return_value=True)

    process, state = await _listen(_manager(gate), [(42, _PCM)])

    process.assert_awaited_once_with(_GUILD, 42, _PCM, _TEXT_CHANNEL)
    assert state.last_speech_at != STALE_SPEECH_AT


async def test_a_refused_speaker_is_never_transcribed_and_does_not_keep_the_session_alive() -> None:
    gate = AsyncMock(return_value=False)

    process, state = await _listen(_manager(gate), [(42, _PCM)])

    process.assert_not_awaited()
    gate.assert_awaited_once_with(_TEXT_CHANNEL, 42)
    assert state.last_speech_at == STALE_SPEECH_AT


async def test_a_manager_nobody_wired_to_a_policy_transcribes_no_one() -> None:
    process, _ = await _listen(_manager(None), [(42, _PCM)])

    process.assert_not_awaited()


async def test_the_policy_is_asked_about_the_guild_when_the_session_has_no_text_channel() -> None:
    gate = AsyncMock(return_value=True)

    await _listen(_manager(gate), [(42, _PCM)], text_channel_id=0)

    gate.assert_awaited_once_with(_GUILD, 42)


async def test_a_speaker_outside_the_configured_list_is_dropped_before_the_policy_is_asked() -> None:
    gate = AsyncMock(return_value=True)

    process, _ = await _listen(_manager(gate, allowed_user_ids={"42"}), [(99, _PCM)])

    process.assert_not_awaited()
    gate.assert_not_awaited()


async def test_the_verdict_is_taken_for_every_utterance() -> None:
    gate = AsyncMock(side_effect=[True, False])

    process, _ = await _listen(_manager(gate), [(42, _PCM), (42, _PCM)])

    assert process.await_count == 1
    assert gate.await_count == 2


async def test_the_first_refusal_of_each_speaker_is_logged_once(caplog: pytest.LogCaptureFixture) -> None:
    gate = AsyncMock(return_value=False)

    with caplog.at_level(logging.WARNING, logger="app.channels.providers.discord.voice.manager"):
        await _listen(_manager(gate), [(42, _PCM), (42, _PCM), (43, _PCM)])

    warnings = [r.getMessage() for r in caplog.records if r.levelno == logging.WARNING]
    assert len(warnings) == 2
    assert "42" in warnings[0]
    assert "43" in warnings[1]
