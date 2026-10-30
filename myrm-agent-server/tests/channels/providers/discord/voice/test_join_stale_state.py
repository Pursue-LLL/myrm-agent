"""VoiceManager.join over a guild state whose VoiceClient is not connected.

Two situations look alike from the state: discord.py is still bringing the session back up (its VoiceClient stays
registered on the guild), or discord.py has dropped it (the guild holds no such VoiceClient any more) without an event
that removes the state. A join must keep the first and release the second. Releasing a session that is reconnecting
orphans a live connection that no command can reach; keeping a dropped one lets its listen loop keep running until its
voice timeout leaves the guild by id and takes the new session down with it.
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


def _channel(*, registered: MagicMock | None = None) -> MagicMock:
    """A voice channel of the guild; ``registered`` is the VoiceClient discord.py currently holds on that guild."""
    channel = MagicMock()
    channel.guild.id = _GUILD
    channel.guild.voice_client = registered
    return channel


async def _unconnected_session(
    manager: VoiceManager, *, silent_for: float = 0.0
) -> tuple[_GuildVoiceState, MagicMock, MagicMock]:
    """A registered state whose VoiceClient is not connected and whose listen loop is running, with its two mocks."""
    voice_client, receiver = _voice_client(connected=False), _receiver()
    state = _GuildVoiceState(voice_client=voice_client, receiver=receiver, text_channel_id=1)
    state.last_speech_at = time.monotonic() - silent_for
    manager._guilds[_GUILD] = state
    state.listen_task = asyncio.create_task(manager._listen_loop(_GUILD))
    await asyncio.sleep(0.05)
    return state, receiver, voice_client


async def _join_again(manager: VoiceManager) -> MagicMock:
    new_client = _voice_client(connected=True)
    channel = _channel()
    channel.connect = AsyncMock(return_value=new_client)
    with patch.object(voice_manager, "VoiceReceiver", return_value=_receiver()):
        assert await manager.join(channel, text_channel_id=2)
    return new_client


async def test_joining_again_releases_a_session_discord_py_has_dropped() -> None:
    manager = VoiceManager(MagicMock(), voice_timeout=0)
    dropped, receiver, voice_client = await _unconnected_session(manager)

    await _join_again(manager)

    assert dropped.listen_task is not None
    assert dropped.listen_task.done()
    receiver.stop.assert_called_once()
    voice_client.disconnect.assert_not_awaited()
    assert manager._guilds[_GUILD] is not dropped
    await manager.leave_all()


async def test_the_dropped_sessions_timeout_does_not_end_the_new_session() -> None:
    manager = VoiceManager(MagicMock(), voice_timeout=1)
    await _unconnected_session(manager, silent_for=0.8)

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
    await _unconnected_session(manager)
    channel = _channel()
    channel.connect = AsyncMock(side_effect=TimeoutError("no voice server"))

    assert await manager.join(channel) is False

    assert _GUILD not in manager._guilds


async def test_joining_over_a_session_discord_py_is_reconnecting_keeps_it() -> None:
    manager = VoiceManager(MagicMock(), voice_timeout=0)
    reconnecting, receiver, voice_client = await _unconnected_session(manager)
    channel = _channel(registered=voice_client)
    channel.connect = AsyncMock()

    assert await manager.join(channel) is False

    assert manager._guilds[_GUILD] is reconnecting
    assert reconnecting.listen_task is not None
    assert not reconnecting.listen_task.done()
    receiver.stop.assert_not_called()
    voice_client.disconnect.assert_not_awaited()
    channel.connect.assert_not_awaited()
    await manager.leave_all()


async def test_the_declined_join_succeeds_once_discord_py_drops_the_session() -> None:
    manager = VoiceManager(MagicMock(), voice_timeout=0)
    session, receiver, voice_client = await _unconnected_session(manager)
    channel = _channel(registered=voice_client)
    channel.connect = AsyncMock(return_value=_voice_client(connected=True))

    assert await manager.join(channel) is False
    channel.guild.voice_client = None
    with patch.object(voice_manager, "VoiceReceiver", return_value=_receiver()):
        assert await manager.join(channel) is True

    assert session.listen_task is not None
    assert session.listen_task.done()
    receiver.stop.assert_called_once()
    assert manager._guilds[_GUILD] is not session
    await manager.leave_all()
