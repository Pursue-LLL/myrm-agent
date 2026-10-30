"""The voice manager lives as long as the gateway client.

discord.py can send READY more than once on one client (after a session it cannot resume, it identifies again), and the
host's ``on_ready`` runs each time. A second READY must keep the manager that holds the live voice sessions, or nothing
(``/voice leave``, the stop) can reach them. A new client, built by a restart, gets a new manager: the previous one may
belong to a stop that was cancelled after its follow loop had been shut down.
"""

from __future__ import annotations

import asyncio
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.voice.manager import _GuildVoiceState
from app.channels.types import ChannelStatus
from tests.channels.providers.discord.gateway_testkit import ready, start_channel


@pytest.fixture
async def channel(monkeypatch: pytest.MonkeyPatch) -> DiscordChannel:
    return await start_channel(monkeypatch)


def _join_guild(channel: DiscordChannel) -> MagicMock:
    assert channel._voice_manager is not None
    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.disconnect = AsyncMock()
    channel._voice_manager._guilds[7] = _GuildVoiceState(voice_client=voice_client, receiver=MagicMock())
    return voice_client


async def test_a_second_ready_keeps_the_manager_and_its_sessions(channel: DiscordChannel) -> None:
    first = channel._voice_manager
    voice_client = _join_guild(channel)

    await ready(channel)

    assert channel._voice_manager is first
    assert first is not None
    assert first.is_connected(7)

    await channel.stop()
    voice_client.disconnect.assert_awaited_once_with(force=True)


async def test_a_restart_after_a_cancelled_stop_builds_a_new_manager(
    channel: DiscordChannel, monkeypatch: pytest.MonkeyPatch
) -> None:
    first = channel._voice_manager
    assert first is not None
    monkeypatch.setattr(first, "leave_all", lambda: asyncio.sleep(3600))
    channel._status = ChannelStatus.DEGRADED

    stopping = asyncio.create_task(channel.stop())
    await asyncio.sleep(0.05)
    stopping.cancel()
    await asyncio.gather(stopping, return_exceptions=True)
    assert channel._voice_manager is first

    await channel.start()
    await ready(channel)

    assert channel._voice_manager is not first
