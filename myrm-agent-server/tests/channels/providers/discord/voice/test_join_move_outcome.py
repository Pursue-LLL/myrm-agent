"""Joining a voice channel the bot is not in yet moves a live session, and the join is only as good as the move.

discord.py's ``VoiceClient.move_to`` documents a ``TimeoutError`` for a move that did not complete, but the connection
state it forwards to logs the timeout, rolls back and returns normally. So a move that did not happen looks exactly like
one that did, unless the manager looks at where the client is afterwards. A join that did not happen must not bind the
session to the new text channel (that drops the speech the receiver still holds for the old one) or be reported as done.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
from discord.voice_state import VoiceConnectionState

from app.channels.providers.discord.voice.manager import VoiceManager, _GuildVoiceState

_GUILD = 1
_TEXT_CHANNEL = 456
_OTHER_TEXT_CHANNEL = 789
_LOGGER = "app.channels.providers.discord.voice.channel_move"


def _voice_channel(channel_id: int) -> MagicMock:
    channel = MagicMock()
    channel.id = channel_id
    channel.guild.id = _GUILD
    return channel


@dataclass
class _Session:
    manager: VoiceManager
    state: _GuildVoiceState
    client: MagicMock
    receiver: MagicMock
    target: MagicMock


@pytest.fixture
def session() -> _Session:
    """A manager with one live session in voice channel 111, bound to text channel 456; the move goes to channel 222."""
    client = MagicMock()
    client.is_connected.return_value = True
    client.channel = _voice_channel(111)
    receiver = MagicMock()
    state = _GuildVoiceState(voice_client=client, receiver=receiver, text_channel_id=_TEXT_CHANNEL)
    manager = VoiceManager(MagicMock(), voice_timeout=0)
    manager._guilds[_GUILD] = state
    return _Session(manager, state, client, receiver, _voice_channel(222))


def _assert_the_session_is_untouched(session: _Session) -> None:
    assert session.manager._guilds[_GUILD] is session.state
    assert session.state.text_channel_id == _TEXT_CHANNEL
    session.receiver.discard_pending.assert_not_called()


async def test_a_move_that_completes_joins_the_new_channel_and_binds_its_text_channel(session: _Session) -> None:
    session.client.move_to = AsyncMock(side_effect=lambda channel: setattr(session.client, "channel", channel))

    assert await session.manager.join(session.target, text_channel_id=_OTHER_TEXT_CHANNEL) is True

    session.client.move_to.assert_awaited_once_with(session.target)
    assert session.state.text_channel_id == _OTHER_TEXT_CHANNEL
    session.receiver.discard_pending.assert_called_once_with()


async def test_a_move_that_returns_without_moving_is_not_a_join(session: _Session, caplog: pytest.LogCaptureFixture) -> None:
    session.client.move_to = AsyncMock()

    with caplog.at_level(logging.ERROR, logger=_LOGGER):
        assert await session.manager.join(session.target, text_channel_id=_OTHER_TEXT_CHANNEL) is False

    _assert_the_session_is_untouched(session)
    assert [(r.levelno, "222" in r.getMessage()) for r in caplog.records] == [(logging.ERROR, True)]


@pytest.mark.parametrize(
    "error",
    [TimeoutError("move timed out"), ConnectionResetError("gateway closed")],
    ids=lambda error: type(error).__name__,
)
async def test_a_move_that_raises_is_not_a_join(session: _Session, caplog: pytest.LogCaptureFixture, error: Exception) -> None:
    session.client.move_to = AsyncMock(side_effect=error)

    with caplog.at_level(logging.ERROR, logger=_LOGGER):
        assert await session.manager.join(session.target, text_channel_id=_OTHER_TEXT_CHANNEL) is False

    _assert_the_session_is_untouched(session)
    assert [(r.levelno, "222" in r.getMessage(), str(error) in r.getMessage()) for r in caplog.records] == [
        (logging.ERROR, True, True)
    ]


async def test_a_move_that_leaves_the_client_disconnected_is_not_a_join(session: _Session) -> None:
    async def move_then_drop(channel: MagicMock) -> None:
        session.client.channel = channel
        session.client.is_connected.return_value = False

    session.client.move_to = AsyncMock(side_effect=move_then_drop)

    assert await session.manager.join(session.target, text_channel_id=_OTHER_TEXT_CHANNEL) is False

    _assert_the_session_is_untouched(session)


async def test_a_cancelled_move_is_not_swallowed(session: _Session) -> None:
    session.client.move_to = AsyncMock(side_effect=asyncio.CancelledError)

    with pytest.raises(asyncio.CancelledError):
        await session.manager.join(session.target, text_channel_id=_OTHER_TEXT_CHANNEL)

    _assert_the_session_is_untouched(session)


async def test_joining_the_channel_the_bot_is_already_in_moves_nothing(session: _Session) -> None:
    session.client.move_to = AsyncMock()

    assert await session.manager.join(session.client.channel, text_channel_id=_OTHER_TEXT_CHANNEL) is True

    session.client.move_to.assert_not_awaited()
    assert session.state.text_channel_id == _OTHER_TEXT_CHANNEL


async def test_discord_py_returns_normally_from_a_move_that_timed_out() -> None:
    """The library behaviour the manager's check after the move rests on, against its own connection state."""
    voice_client = MagicMock()
    voice_client.channel = _voice_channel(111)
    voice_client.channel.guild.change_voice_state = AsyncMock()
    connection = VoiceConnectionState(voice_client)
    try:
        state_before = connection.state

        await connection.move_to(_voice_channel(222), 0.01)

        assert connection.state is state_before
        assert voice_client.channel.id == 111
    finally:
        connection._socket_reader.stop()
