"""A ``stop()`` the gateway cuts off has already released the channel's long-lived connection.

``stop_channel`` abandons a ``stop()`` that outlives its cap, so every step it had not reached never runs. A provider
therefore releases its own task or connection and leaves the status at ``STOPPED`` before the best-effort network
cleanup (drafts, streaming cards); otherwise the abandoned channel keeps listening and a restart runs two side by side.
"""

from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from unittest.mock import AsyncMock, MagicMock

import pytest

from app.channels.core import channel_stop
from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.providers.dingtalk.channel import DingTalkChannel
from app.channels.providers.feishu.channel import FeishuChannel
from app.channels.providers.telegram.api import TelegramClient
from app.channels.types import ChannelStatus
from tests.channels.providers.telegram.telegram_channel_factories import make_channel

_GUARD_SECONDS = 5.0
_SETTLE_SECONDS = 0.05
_STOP_CAP_SECONDS = 0.25
_CHANNEL = "channel"


async def _hang(*_args: object, **_kwargs: object) -> None:
    await asyncio.Event().wait()


async def _settle() -> None:
    await asyncio.sleep(_SETTLE_SECONDS)


class _Connections:
    """The long-lived connections a fake network currently holds open."""

    def __init__(self) -> None:
        self.live = 0

    async def hold(self, *_args: object, **_kwargs: object) -> None:
        self.live += 1
        try:
            await asyncio.Event().wait()
        finally:
            self.live -= 1


class _FakeTransport:
    """Stands in for a websocket transport: open until ``stop()``."""

    def __init__(self, connections: _Connections) -> None:
        self._connections = connections
        connections.live += 1

    async def stop(self) -> None:
        self._connections.live -= 1


@dataclass
class _Provider:
    channel: BaseChannel
    connections: _Connections
    release: Callable[[], Awaitable[None]]


async def _cancel(task: asyncio.Task[None] | None) -> None:
    if task is not None and not task.done():
        task.cancel()
        await asyncio.gather(task, return_exceptions=True)


async def _telegram(monkeypatch: pytest.MonkeyPatch) -> _Provider:
    """A polling bot with a draft open whose clearing never completes."""
    connections = _Connections()
    channel = make_channel()
    client = MagicMock(spec=TelegramClient)
    client.get_me = AsyncMock(return_value={"username": "bot", "id": 1})
    for name in ("set_my_commands", "delete_my_commands", "delete_webhook", "close"):
        setattr(client, name, AsyncMock())
    client.get_updates = connections.hold
    client.send_message_draft = _hang
    monkeypatch.setattr(channel, "_client", client)
    await channel.start()
    await _settle()
    channel._active_drafts["1:draft:1"] = 7
    return _Provider(channel, connections, lambda: _cancel(channel._poll_task))


async def _dingtalk(monkeypatch: pytest.MonkeyPatch) -> _Provider:
    """A stream-mode bot with a streaming card open whose finalizing never completes."""
    connections = _Connections()
    channel = DingTalkChannel(app_key="key", app_secret="secret")
    monkeypatch.setattr(channel._api, "refresh_token", AsyncMock())
    monkeypatch.setattr(channel._api, "close", AsyncMock())
    monkeypatch.setattr(channel._api, "streaming_update", _hang)
    monkeypatch.setattr(channel, "_stream_once", connections.hold)
    await channel.start()
    await _settle()
    channel._streaming_cards["card"] = "card"
    return _Provider(channel, connections, lambda: _cancel(channel._stream_task))


async def _feishu(monkeypatch: pytest.MonkeyPatch) -> _Provider:
    """A websocket bot with a streaming card open whose finalizing never completes."""
    connections = _Connections()
    channel = FeishuChannel(app_id="cli_test", app_secret="secret")
    monkeypatch.setattr(channel, "_ws_transport", _FakeTransport(connections))
    monkeypatch.setattr(channel._client, "streaming_card_update", _hang)
    monkeypatch.setattr(channel._client, "close", AsyncMock())
    channel._status = ChannelStatus.RUNNING
    channel._streaming_card_ids["message"] = "card"

    async def release() -> None:
        return None

    return _Provider(channel, connections, release)


_Builder = Callable[[pytest.MonkeyPatch], Awaitable[_Provider]]
_STOPPABLE = [
    pytest.param(_telegram, id="telegram"),
    pytest.param(_dingtalk, id="dingtalk"),
    pytest.param(_feishu, id="feishu"),
]
_RESTARTABLE = [pytest.param(_telegram, id="telegram"), pytest.param(_dingtalk, id="dingtalk")]


@pytest.fixture(autouse=True)
def short_cap(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(channel_stop, "_STOP_TIMEOUT", _STOP_CAP_SECONDS)


@pytest.mark.asyncio
@pytest.mark.parametrize("build", _STOPPABLE)
async def test_a_stop_cut_off_during_its_cleanup_has_already_released_the_connection(
    build: _Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = await build(monkeypatch)
    try:
        await asyncio.wait_for(channel_stop.stop_channel(_CHANNEL, provider.channel), _GUARD_SECONDS)

        assert provider.channel.status == ChannelStatus.STOPPED
        assert provider.connections.live == 0
    finally:
        await provider.release()


@pytest.mark.asyncio
@pytest.mark.parametrize("build", _RESTARTABLE)
async def test_a_restart_after_a_cut_off_stop_leaves_exactly_one_connection(
    build: _Builder, monkeypatch: pytest.MonkeyPatch
) -> None:
    provider = await build(monkeypatch)
    gateway = ChannelGateway()
    try:
        await asyncio.wait_for(gateway._restart_channel(_CHANNEL, provider.channel), _GUARD_SECONDS)
        await gateway._channel_tasks[_CHANNEL]
        await _settle()

        assert provider.connections.live == 1
    finally:
        await provider.release()
