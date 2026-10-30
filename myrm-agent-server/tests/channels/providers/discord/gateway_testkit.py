"""A DiscordChannel on a stand-in gateway client: the host's ``on_ready`` runs without a network."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")
import discord

from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.config import DiscordChannelConfig


class FakeClient:
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


async def ready(channel: DiscordChannel) -> None:
    """Deliver the gateway's READY to the host."""
    assert isinstance(channel._client, FakeClient)
    await channel._client.handlers["on_ready"]()


async def start_channel(
    monkeypatch: pytest.MonkeyPatch,
    commands: dict[str, Callable[..., Awaitable[None]]] | None = None,
) -> DiscordChannel:
    """A started, ready voice-enabled channel; the slash commands it registers land in ``commands``."""
    tree = MagicMock()
    tree.sync = AsyncMock()
    if commands is not None:
        tree.command = lambda *, name, description: lambda handler: commands.setdefault(name, handler)
    monkeypatch.setattr(discord, "Client", FakeClient)
    monkeypatch.setattr(discord.app_commands, "CommandTree", lambda client: tree)
    monkeypatch.setattr(DiscordChannel, "_ensure_opus_loaded", staticmethod(lambda: None))
    channel = DiscordChannel(DiscordChannelConfig(bot_token="test_token", enable_gateway=True, voice_enabled=True))
    await channel.start()
    await ready(channel)
    return channel
