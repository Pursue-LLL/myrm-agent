"""VoiceManager.join over a guild state whose voice connection has already ended.

A connection can end on its own while the gateway is unreachable (discord.py then never gets the event that confirms the
leave), so nothing removes the guild's state. Joining again must release that state first: its listen loop would otherwise
keep running and, when its voice timeout elapsed, leave the guild by id and take the new session down with it.
"""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice import manager as voice_manager
from app.channels.providers.discord.voice.manager import VoiceManager, _GuildVoiceState

_GUILD = 7


@pytest.fixture(autouse=True)
def _fast_polling(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(voice_manager, "_LISTEN_POLL_INTERVAL", 0.01)


def _voice_client(*, connected: bool) -> MagicMock:
    voice_client = MagicMock()
    voice_client.is_connected.return_value = connected
    voice_client.disconnect = AsyncMock()
    return voice_client


def _receiver() -> MagicMock:
    receiver = MagicMock()
    receiver.running = True
    receiver.check_silence.return_value = []
    return receiver


async def _ended_session(manager: VoiceManager, *, silent_for: float = 0.0) -> tuple[_GuildVoiceState, MagicMock, MagicMock]:
    """A registered state whose connection has ended and whose listen loop is still running, with its two mocks."""
    voice_client, receiver = _voice_client(connected=False), _receiver()
    state = _GuildVoiceState(voice_client=voice_client, receiver=receiver, text_channel_id=1)
    state.last_speech_at = time.monotonic() - silent_for
    manager._guilds[_GUILD] = state
    state.listen_task = asyncio.create_task(manager._listen_loop(_GUILD))
    await asyncio.sleep(0.05)
    return state, receiver, voice_client


async def _join_again(manager: VoiceManager) -> MagicMock:
    new_client = _voice_client(connected=True)
    channel = MagicMock()
    channel.guild.id = _GUILD
    channel.connect = AsyncMock(return_value=new_client)
    with patch.object(voice_manager, "VoiceReceiver", return_value=_receiver()):
        assert await manager.join(channel, text_channel_id=2)
    return new_client


async def test_joining_again_releases_the_ended_session() -> None:
    manager = VoiceManager(MagicMock(), voice_timeout=0)
    ended, receiver, voice_client = await _ended_session(manager)

    await _join_again(manager)

    assert ended.listen_task is not None
    assert ended.listen_task.done()
    receiver.stop.assert_called_once()
    voice_client.disconnect.assert_not_awaited()
    assert manager._guilds[_GUILD] is not ended
    await manager.leave_all()


async def test_the_ended_sessions_timeout_does_not_end_the_new_session() -> None:
    manager = VoiceManager(MagicMock(), voice_timeout=1)
    await _ended_session(manager, silent_for=0.8)

    new_client = await _join_again(manager)
    new_session = manager._guilds[_GUILD]
    for _ in range(30):
        new_session.last_speech_at = time.monotonic()
        await asyncio.sleep(0.02)

    assert manager._guilds.get(_GUILD) is new_session
    new_client.disconnect.assert_not_awaited()
    await manager.leave_all()


async def test_a_failed_join_leaves_no_released_state_registered() -> None:
    manager = VoiceManager(MagicMock(), voice_timeout=0)
    await _ended_session(manager)
    channel = MagicMock()
    channel.guild.id = _GUILD
    channel.connect = AsyncMock(side_effect=TimeoutError("no voice server"))

    assert await manager.join(channel) is False

    assert _GUILD not in manager._guilds
