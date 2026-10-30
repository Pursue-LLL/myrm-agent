"""DiscordChannel.stop() leaves voice within a bound, whatever discord.py does while it waits for the gateway.

The voice connections are real ``VoiceConnectionState`` objects, so discord.py's own wait and cancellation code runs:
it waits for the gateway to confirm a leave, and swallows a cancellation while it does. Only the network is stubbed.
``Client.close()`` is a stand-in that, like discord.py's, disconnects every voice connection still attached to the client.
The stand-in waits are scaled down (``_CONFIRMATION_WAIT`` for discord.py's 30 s, ``_BUDGET`` for the 4 s leave bound).
"""

from __future__ import annotations

import asyncio
import logging
import time
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock, PropertyMock

import pytest

pytest.importorskip("discord")
from discord.voice_state import VoiceConnectionState

from app.channels.providers.discord import channel as discord_channel
from app.channels.providers.discord.channel import DiscordChannel
from app.channels.providers.discord.config import DiscordChannelConfig
from app.channels.providers.discord.voice.manager import VoiceManager, _GuildVoiceState
from app.channels.types import ChannelStatus

_CONFIRMATION_WAIT = 0.6
_BUDGET = 0.15
_RETURNS_BEFORE_ONE_WAIT = _CONFIRMATION_WAIT * 0.75
_GATEWAY_LOGGER = "app.channels.providers.discord.channel"


class _Voice:
    """One guild's voice connection: a real ``VoiceConnectionState`` over a stubbed network."""

    def __init__(self, attached: list[_Voice], events: list[str], *, confirms: bool, hangs_before_wait: bool) -> None:
        self.attached = attached
        self.events = events
        self.released = False
        attached.append(self)
        self.state = VoiceConnectionState(self)  # type: ignore[arg-type]
        self.state.timeout = _CONFIRMATION_WAIT
        reader = self.state._socket_reader
        stop_reader = reader.stop

        def release() -> None:
            self.released = True
            stop_reader()

        reader.stop = release  # type: ignore[method-assign]

        async def send_leave() -> None:
            if hangs_before_wait:
                await asyncio.sleep(1000)
            if confirms:
                self.state._disconnected.set()

        self.state._voice_disconnect = send_leave  # type: ignore[method-assign]

    def is_connected(self) -> bool:
        return True

    def stop(self) -> None:
        pass

    def cleanup(self) -> None:
        if self in self.attached:
            self.attached.remove(self)

    async def disconnect(self, *, force: bool) -> None:
        self.events.append("leave")
        await self.state.disconnect(force=force, wait=True)


async def _channel(
    monkeypatch: pytest.MonkeyPatch,
    attached: list[_Voice],
    events: list[str],
    *,
    guilds: int = 2,
    confirms: bool = False,
    first_hangs_before_wait: bool = False,
    budget: float = _BUDGET,
) -> DiscordChannel:
    monkeypatch.setattr(discord_channel, "_VOICE_LEAVE_TIMEOUT", budget)
    manager = VoiceManager(MagicMock(), voice_timeout=0)
    for guild_id in range(1, guilds + 1):
        voice = _Voice(attached, events, confirms=confirms, hangs_before_wait=first_hangs_before_wait and guild_id == 1)
        manager._guilds[guild_id] = _GuildVoiceState(voice_client=voice, receiver=MagicMock())  # type: ignore[arg-type]

    async def close() -> None:
        events.append("close")
        for voice in list(attached):
            await voice.disconnect(force=True)

    client = MagicMock()
    client.is_closed.return_value = False
    client.close = AsyncMock(side_effect=close)
    type(client).voice_clients = PropertyMock(side_effect=lambda: list(attached))

    channel = DiscordChannel(DiscordChannelConfig(bot_token="test_token", enable_gateway=True))
    channel._client = client
    channel._voice_manager = manager
    channel._gateway_task = asyncio.create_task(asyncio.sleep(3600))
    channel._status = ChannelStatus.RUNNING
    await asyncio.sleep(0)
    return channel


async def _stop(channel: DiscordChannel) -> float:
    started = time.monotonic()
    async with asyncio.timeout(3.0):
        await channel.stop()
    return time.monotonic() - started


async def _settle(everyone: list[_Voice]) -> list[bool]:
    """Let a leave abandoned at the deadline end by itself, report which connections released their socket, then
    stop the connections' reader threads."""
    await asyncio.sleep(_CONFIRMATION_WAIT + 0.4)
    released = [voice.released for voice in everyone]
    for voice in everyone:
        voice.state._socket_reader.stop()
    return released


async def test_stop_does_not_wait_for_a_confirmation_the_gateway_never_sends(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    attached: list[_Voice] = []
    channel = await _channel(monkeypatch, attached, [])
    everyone = list(attached)

    with caplog.at_level(logging.WARNING, logger=_GATEWAY_LOGGER):
        elapsed = await _stop(channel)

    assert elapsed < _RETURNS_BEFORE_ONE_WAIT
    assert channel.status == ChannelStatus.STOPPED
    channel._client.close.assert_awaited_once()
    assert channel._gateway_task.cancelled()
    assert attached == []
    assert "voice leave did not finish" in caplog.text
    assert await _settle(everyone) == [True, True]


async def test_stop_closes_the_client_when_a_guild_hangs_before_it_starts_waiting(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    attached: list[_Voice] = []
    channel = await _channel(monkeypatch, attached, [], guilds=3, first_hangs_before_wait=True)
    everyone = list(attached)

    elapsed = await _stop(channel)

    assert elapsed < _RETURNS_BEFORE_ONE_WAIT
    assert channel.status == ChannelStatus.STOPPED
    channel._client.close.assert_awaited_once()
    assert await _settle(everyone) == [True, True, True]


async def test_stop_leaves_voice_then_closes_the_client_without_a_warning_when_the_gateway_confirms(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    attached: list[_Voice] = []
    events: list[str] = []
    channel = await _channel(monkeypatch, attached, events, confirms=True, budget=5.0)
    everyone = list(attached)

    with caplog.at_level(logging.WARNING, logger=_GATEWAY_LOGGER):
        elapsed = await _stop(channel)

    assert elapsed < _RETURNS_BEFORE_ONE_WAIT
    assert events == ["leave", "leave", "close"]
    assert channel.status == ChannelStatus.STOPPED
    assert channel._gateway_task.cancelled()
    assert caplog.text == ""
    assert await _settle(everyone) == [True, True]


async def test_a_stop_cancelled_while_it_leaves_voice_cancels_the_leave(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(discord_channel, "_VOICE_LEAVE_TIMEOUT", 5.0)
    leaves: list[asyncio.Task[None]] = []

    async def leave_all() -> None:
        current = asyncio.current_task()
        assert current is not None
        leaves.append(current)
        await asyncio.Event().wait()

    channel = DiscordChannel(DiscordChannelConfig(bot_token="test_token", enable_gateway=True))
    channel._client = MagicMock()
    channel._client.close = AsyncMock()
    channel._voice_manager = SimpleNamespace(leave_all=leave_all)  # type: ignore[assignment]
    channel._status = ChannelStatus.RUNNING

    stopping = asyncio.create_task(channel.stop())
    await asyncio.sleep(0.05)
    stopping.cancel()
    with pytest.raises(asyncio.CancelledError):
        await stopping
    await asyncio.sleep(0)

    assert leaves[0].cancelled()
    channel._client.close.assert_not_awaited()
