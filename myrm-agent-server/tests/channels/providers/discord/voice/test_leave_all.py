"""VoiceManager.leave_all: the guilds leave concurrently, and one guild that stalls or fails does not stop the others."""

from __future__ import annotations

import asyncio
import logging
from unittest.mock import AsyncMock, MagicMock

import pytest

pytest.importorskip("discord")

from app.channels.providers.discord.voice.manager import VoiceManager, _GuildVoiceState


def _join(manager: VoiceManager, guild_id: int, disconnect: AsyncMock) -> MagicMock:
    voice_client = MagicMock()
    voice_client.is_connected.return_value = True
    voice_client.disconnect = disconnect
    manager._guilds[guild_id] = _GuildVoiceState(voice_client=voice_client, receiver=MagicMock())
    return voice_client


async def test_a_guild_that_waits_for_its_confirmation_does_not_hold_up_the_others() -> None:
    manager = VoiceManager(MagicMock(), voice_timeout=0)
    confirmed = asyncio.Event()

    async def wait_for_confirmation(*, force: bool) -> None:
        await confirmed.wait()

    _join(manager, 1, AsyncMock(side_effect=wait_for_confirmation))
    second = _join(manager, 2, AsyncMock())
    third = _join(manager, 3, AsyncMock())

    leave_all = asyncio.create_task(manager.leave_all())
    await asyncio.sleep(0.05)

    second.disconnect.assert_awaited_once_with(force=True)
    third.disconnect.assert_awaited_once_with(force=True)
    assert not leave_all.done()

    confirmed.set()
    await leave_all
    assert manager._guilds == {}


async def test_a_guild_that_fails_to_leave_does_not_stop_the_others(caplog: pytest.LogCaptureFixture) -> None:
    manager = VoiceManager(MagicMock(), voice_timeout=0)
    _join(manager, 1, AsyncMock(side_effect=RuntimeError("socket closed")))
    second = _join(manager, 2, AsyncMock())

    with caplog.at_level(logging.WARNING, logger="app.channels.providers.discord.voice.manager"):
        await manager.leave_all()

    second.disconnect.assert_awaited_once_with(force=True)
    assert manager._guilds == {}
    assert "guild 1" in caplog.text
    assert "socket closed" in caplog.text
