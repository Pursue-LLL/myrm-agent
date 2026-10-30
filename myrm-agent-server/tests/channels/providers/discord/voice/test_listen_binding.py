"""A poll batch of utterances is admitted and processed against the text channel the batch started with.

The listen loop handles a batch one utterance at a time and each one awaits the policy and speech-to-text, which take
seconds. A ``/voice join`` from another text channel in that time rebinds the session; reading the binding again for the
next utterance would turn what a speaker said into a turn in a conversation that was never theirs, with its history,
skills and reply target. The rebind applies from the next batch on.
"""

from __future__ import annotations

from unittest.mock import MagicMock

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.manager import VoiceManager
from tests.channels.providers.discord.voice.listen_testkit import listen_once

_GUILD = 1
_TEXT_CHANNEL = 789
_REBOUND_CHANNEL = 456
_PCM = b"\x00" * 192100


@pytest.fixture(autouse=True)
def _no_poll_delay(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr("app.channels.providers.discord.voice.manager._LISTEN_POLL_INTERVAL", 0)


def _manager_that_rebinds_during_the_first_check() -> tuple[VoiceManager, list[int]]:
    """A manager whose policy answers yes and, on its first question, has a ``/voice join`` rebind the session."""
    asked: list[int] = []

    async def gate(chat_id: int, user_id: int) -> bool:
        asked.append(chat_id)
        if len(asked) == 1:
            manager._guilds[_GUILD].text_channel_id = _REBOUND_CHANNEL
        return True

    manager = VoiceManager(MagicMock(), voice_timeout=0, speaker_gate=gate)
    return manager, asked


async def test_every_utterance_of_a_batch_keeps_the_batchs_binding() -> None:
    manager, asked = _manager_that_rebinds_during_the_first_check()

    process, _ = await listen_once(manager, [(42, _PCM), (43, _PCM)], guild_id=_GUILD, text_channel_id=_TEXT_CHANNEL)

    assert asked == [_TEXT_CHANNEL, _TEXT_CHANNEL]
    assert [call.args[3] for call in process.await_args_list] == [_TEXT_CHANNEL, _TEXT_CHANNEL]


async def test_the_next_batch_takes_the_new_binding() -> None:
    manager, asked = _manager_that_rebinds_during_the_first_check()

    process, _ = await listen_once(
        manager,
        [(42, _PCM)],
        guild_id=_GUILD,
        text_channel_id=_TEXT_CHANNEL,
        later_batches=[[(42, _PCM)]],
    )

    assert asked == [_TEXT_CHANNEL, _REBOUND_CHANNEL]
    assert [call.args[3] for call in process.await_args_list] == [_TEXT_CHANNEL, _REBOUND_CHANNEL]
