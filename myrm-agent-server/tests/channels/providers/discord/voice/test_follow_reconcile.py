"""The follow reconciliation is the heal path for missed gateway events, so one failed pass must not end it.

A pass that fails (the REST poll hits a network error, a join raises) is logged with the guild and the error and the
next pass runs as if nothing happened; one guild's failure never skips the guilds after it; a cancel that lands inside
a pass still ends the task; and a task that has ended can be started again.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, MagicMock

import aiohttp
import pytest

pytest.importorskip("discord")
import discord

from app.channels.providers.discord.voice import follow
from app.channels.providers.discord.voice.follow import VoiceFollowManager

_FOLLOWED_USER = "100"

_RestRequest = Callable[[discord.http.Route], Awaitable[dict[str, str]]]


@pytest.fixture(autouse=True)
def _fast_passes(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(follow, "_RECONCILE_INTERVAL", 0.005)
    monkeypatch.setattr(follow, "_RECONCILE_JITTER", 0.0)


def _guild(guild_id: int) -> tuple[MagicMock, MagicMock]:
    """A guild whose followed user sits in the voice channel returned with it."""
    channel = MagicMock(spec=discord.VoiceChannel)
    channel.id = 1000 + guild_id
    guild = MagicMock()
    guild.id = guild_id
    guild.get_channel.return_value = channel
    return guild, channel


def _manager(guilds: list[MagicMock], request: _RestRequest) -> tuple[VoiceFollowManager, AsyncMock]:
    client = MagicMock()
    client.guilds = guilds
    client.http.request = request
    voice_ops = MagicMock()
    voice_ops.join = AsyncMock(return_value=True)
    voice_ops.leave = AsyncMock()
    return VoiceFollowManager(client, voice_ops, follow_user_ids={_FOLLOWED_USER}), voice_ops.join


async def _channel_of_guild(route: discord.http.Route) -> dict[str, str]:
    assert isinstance(route.guild_id, int)
    return {"channel_id": str(1000 + route.guild_id)}


async def _until(condition: Callable[[], bool]) -> None:
    async with asyncio.timeout(2.0):
        while not condition():
            await asyncio.sleep(0.005)


async def test_a_network_error_in_one_pass_does_not_end_the_loop() -> None:
    guild, channel = _guild(1)
    polls = 0

    async def request(route: discord.http.Route) -> dict[str, str]:
        nonlocal polls
        polls += 1
        if polls == 1:
            raise aiohttp.ClientConnectionError("network blip")
        return await _channel_of_guild(route)

    manager, join = _manager([guild], request)
    await manager.start_reconciliation()
    try:
        await _until(lambda: join.await_count > 0)
        assert polls > 1
        assert manager._reconcile_task is not None
        assert not manager._reconcile_task.done()
        join.assert_awaited_with(channel)
    finally:
        await manager.stop_reconciliation()


async def test_a_guild_that_fails_does_not_skip_the_guilds_after_it() -> None:
    first, first_channel = _guild(1)
    second, second_channel = _guild(2)
    manager, join = _manager([first, second], _channel_of_guild)

    async def join_unless_first(channel: discord.VoiceChannel) -> bool:
        if channel is first_channel:
            raise ConnectionResetError("join failed")
        return True

    join.side_effect = join_unless_first

    await manager._reconcile_once()

    assert [call.args[0] for call in join.await_args_list] == [first_channel, second_channel]


async def test_a_reconcile_task_that_has_ended_is_started_again() -> None:
    guild, _ = _guild(1)
    manager, _ = _manager([guild], _channel_of_guild)
    await manager.start_reconciliation()
    ended = manager._reconcile_task
    assert ended is not None
    ended.cancel()
    await asyncio.gather(ended, return_exceptions=True)
    assert ended.done()

    await manager.start_reconciliation()
    try:
        assert manager._reconcile_task is not ended
        assert manager._reconcile_task is not None
        assert not manager._reconcile_task.done()
    finally:
        await manager.stop_reconciliation()


async def test_a_failed_pass_is_logged_with_the_guild_and_the_error(caplog: pytest.LogCaptureFixture) -> None:
    guild, _ = _guild(7)

    async def request(route: discord.http.Route) -> dict[str, str]:
        raise aiohttp.ClientConnectionError("network blip")

    manager, _ = _manager([guild], request)

    with caplog.at_level(logging.WARNING, logger=follow.logger.name):
        await manager._reconcile_once()

    [record] = [r for r in caplog.records if r.levelno == logging.WARNING]
    message = record.getMessage()
    assert "guild 7" in message
    assert "ClientConnectionError" in message
    assert "network blip" in message
    assert record.exc_info is None


async def test_a_cancel_that_lands_inside_a_pass_ends_the_task() -> None:
    """Stopping the loop cancels it wherever it is; a pass that logs and swallows the cancel would never end."""
    guild, _ = _guild(1)
    manager, join = _manager([guild], _channel_of_guild)
    in_join = asyncio.Event()
    release_join = asyncio.Event()

    async def block_in_join(channel: discord.VoiceChannel) -> bool:
        in_join.set()
        await release_join.wait()
        return True

    join.side_effect = block_in_join
    await manager.start_reconciliation()
    task = manager._reconcile_task
    assert task is not None
    try:
        await _until(in_join.is_set)
        task.cancel()
        # Not wait_for: a swallowed cancel must fail this assertion, not hang the test.
        done, _ = await asyncio.wait({task}, timeout=1.0)
        assert task in done
    finally:
        manager._destroyed = True
        release_join.set()
        task.cancel()
        await asyncio.wait({task}, timeout=1.0)
