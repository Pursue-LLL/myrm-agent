"""Leaving a guild disconnects the VoiceClient while discord.py still holds it, not only while it is connected.

discord.py keeps a VoiceClient registered on its guild until ``disconnect`` runs ``cleanup()``, and it refuses every
later ``connect`` on that guild with ``Already connected to a voice channel``. A VoiceClient that is being brought back
up reports ``is_connected()`` False yet stays registered, so a leave that skips the disconnect for it leaves a
connection no command can reach. A VoiceClient discord.py has already dropped is the opposite case: its disconnect
waits for a confirmation that never comes, so it must not be asked to disconnect.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.manager import VoiceManager, _GuildVoiceState

_GUILD = 7


def _session(manager: VoiceManager, *, connected: bool, held: bool) -> tuple[MagicMock, MagicMock]:
    """A registered session; ``held`` says whether discord.py still has its VoiceClient registered on the guild."""
    voice_client = MagicMock()
    voice_client.is_connected.return_value = connected
    voice_client.disconnect = AsyncMock()
    voice_client.guild.voice_client = voice_client if held else None
    receiver = MagicMock()
    manager._guilds[_GUILD] = _GuildVoiceState(voice_client=voice_client, receiver=receiver, text_channel_id=1)
    return voice_client, receiver


@pytest.mark.parametrize(
    ("connected", "held", "disconnects"),
    [
        pytest.param(True, True, True, id="connected"),
        pytest.param(False, True, True, id="reconnecting"),
        pytest.param(True, False, True, id="connected-but-unregistered"),
        pytest.param(False, False, False, id="dropped-by-discord-py"),
    ],
)
async def test_leave_disconnects_what_discord_py_still_holds(connected: bool, held: bool, disconnects: bool) -> None:
    manager = VoiceManager(MagicMock(), voice_timeout=0)
    voice_client, receiver = _session(manager, connected=connected, held=held)

    await manager.leave(_GUILD)

    receiver.stop.assert_called_once()
    assert _GUILD not in manager._guilds
    if disconnects:
        voice_client.disconnect.assert_awaited_once_with(force=True)
    else:
        voice_client.disconnect.assert_not_awaited()
