"""The receiver against discord.py's own connection and voice websocket classes instead of stand-ins.

The receiver reads a handful of attributes off ``VoiceClient._connection`` and hooks the voice websocket's message
callback. A ``MagicMock`` has every attribute, so a discord.py release that renames one leaves the other receiver tests
green while the receiver stops working; with the real classes here, that rename fails this file.
"""

from __future__ import annotations

import asyncio
from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest

pytest.importorskip("discord")
from discord.gateway import DiscordVoiceWebSocket
from discord.voice_state import VoiceConnectionState

from app.channels.providers.discord.voice.receiver import VoiceReceiver

_KEY = bytes(range(32))
_SSRC = 7
_USER = 42


@pytest.fixture
def connection() -> Iterator[VoiceConnectionState]:
    """A real connection state whose session has no key yet; its socket reader thread is stopped afterwards."""
    state = VoiceConnectionState(MagicMock())
    yield state
    state._socket_reader.stop()


def _receiver_on(connection: VoiceConnectionState) -> VoiceReceiver:
    voice_client = MagicMock()
    voice_client._connection = connection
    return VoiceReceiver(voice_client)


def test_a_connection_whose_session_has_no_key_yet_has_no_credentials(connection: VoiceConnectionState) -> None:
    assert _receiver_on(connection)._credentials() is None


def test_the_credentials_are_read_off_the_connections_own_attributes(connection: VoiceConnectionState) -> None:
    connection.secret_key = list(_KEY)

    credentials = _receiver_on(connection)._credentials()

    assert credentials is not None
    assert credentials.secret_key == _KEY
    assert (credentials.mode, credentials.bot_ssrc) == (connection.mode, connection.ssrc)
    assert credentials.dave_session is connection.dave_session


@pytest.mark.parametrize("method", ["add_socket_listener", "remove_socket_listener"])
def test_the_connection_offers_the_socket_listener_calls_the_receiver_makes(method: str) -> None:
    assert callable(getattr(VoiceConnectionState, method))


async def test_the_voice_websocket_passes_its_messages_to_the_speaking_hook(connection: VoiceConnectionState) -> None:
    receiver = _receiver_on(connection)
    websocket = DiscordVoiceWebSocket(MagicMock(), asyncio.get_running_loop())
    websocket._connection = connection
    connection.ws = websocket

    receiver._install_speaking_hook(connection)
    await websocket.received_message({"op": 5, "d": {"ssrc": _SSRC, "user_id": _USER}})

    assert receiver._ssrc_to_user == {_SSRC: _USER}
