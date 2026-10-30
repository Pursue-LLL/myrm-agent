"""The voice manager lives as long as the gateway client.

discord.py can send READY more than once on one client (after a session it cannot resume, it identifies again), and the
host's ``on_ready`` runs each time. A second READY must keep the manager that holds the live voice sessions, or nothing
(``/voice leave``, the stop) can reach them. A new client, built by a restart, gets a new manager: the previous one may
belong to a stop that was cancelled after its follow loop had been shut down.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.config import DiscordChannelConfig
from app.channels.providers.discord.voice.manager import _GuildVoiceState
from app.channels.types import ChannelStatus


class _FakeClient:
    """Stands in for ``discord.Client``: records the event handlers and ends its gateway session at once."""

    def __init__(self, **_: object) -> None:
        self.user = SimpleNamespace(id=99)
        self.voice_clients: list[object] = []
        self.handlers: dict[str, Callable[..., Awaitable[None]]] = {}

    def event(self, handler: Callable[..., Awaitable[None]]) -> Callable[..., Awaitable[None]]:
        self.handlers[handler.__name__] = handler
        return handler

    async def start(self, token: str) -> None:
        return None

    def is_closed(self) -> bool:
        return False

    async def close(self) -> None:
        return None


async def _ready(channel: DiscordChannel) -> None:
    assert isinstance(channel._client, _FakeClient)
    await channel._client.handlers["on_ready"]()


@pytest.fixture
async def channel(monkeypatch: pytest.MonkeyPatch) -> DiscordChannel:
    monkeypatch.setattr(discord, "Client", _FakeClient)
    tree = MagicMock()
    tree.sync = AsyncMock()
    monkeypatch.setattr(discord.app_commands, "CommandTree", lambda client: tree)
    monkeypatch.setattr(DiscordChannel, "_ensure_opus_loaded", staticmethod(lambda: None))
    channel = DiscordChannel(DiscordChannelConfig(bot_token="test_token", enable_gateway=True, voice_enabled=True))
    await channel.start()
    await _ready(channel)
    return channel


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

    await _ready(channel)

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
    await _ready(channel)

    assert channel._voice_manager is not first
