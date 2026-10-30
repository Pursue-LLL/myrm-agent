"""A channel whose ``stop()`` never returns cannot hold up the gateway: the stop is abandoned after a cap and logged."""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.core import channel_stop
from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import ChannelStatus, OutboundMessage

_GUARD_SECONDS = 5.0


class _StopChannel(BaseChannel):
    name = "stopper"

    def __init__(self, stop_error: Exception | None = None, hangs: bool = True) -> None:
        super().__init__()
        self._stop_error = stop_error
        self._hangs = hangs
        self.stop_started = asyncio.Event()

    async def send(self, msg: OutboundMessage) -> str | None:
        return None

    async def stop(self) -> None:
        self.stop_started.set()
        if self._stop_error is not None:
            raise self._stop_error
        if self._hangs:
            await asyncio.Event().wait()


@pytest.fixture
def short_cap(monkeypatch: pytest.MonkeyPatch) -> float:
    monkeypatch.setattr(channel_stop, "_STOP_TIMEOUT", 0.05)
    return 0.05


@pytest.mark.asyncio
async def test_a_stop_that_never_returns_is_abandoned_after_the_cap_and_logged(
    short_cap: float, caplog: pytest.LogCaptureFixture
) -> None:
    channel = _StopChannel()

    with caplog.at_level(logging.WARNING, logger=channel_stop.logger.name):
        await asyncio.wait_for(channel_stop.stop_channel("stopper", channel), _GUARD_SECONDS)

    assert channel.stop_started.is_set()
    assert "Channel 'stopper' did not stop within" in caplog.text


@pytest.mark.asyncio
async def test_an_error_from_stop_is_logged_as_an_error_not_as_a_timeout(caplog: pytest.LogCaptureFixture) -> None:
    channel = _StopChannel(stop_error=RuntimeError("socket closed"))

    with caplog.at_level(logging.WARNING, logger=channel_stop.logger.name):
        await channel_stop.stop_channel("stopper", channel)

    assert "Channel 'stopper': error while stopping" in caplog.text
    assert "did not stop within" not in caplog.text


@pytest.mark.asyncio
async def test_a_timeout_error_raised_inside_stop_is_not_reported_as_the_cap(caplog: pytest.LogCaptureFixture) -> None:
    channel = _StopChannel(stop_error=TimeoutError("platform call timed out"))

    with caplog.at_level(logging.WARNING, logger=channel_stop.logger.name):
        await channel_stop.stop_channel("stopper", channel)

    assert "error while stopping" in caplog.text
    assert "did not stop within" not in caplog.text


@pytest.mark.asyncio
async def test_a_stop_that_finishes_logs_nothing(caplog: pytest.LogCaptureFixture) -> None:
    channel = _StopChannel(hangs=False)

    with caplog.at_level(logging.WARNING, logger=channel_stop.logger.name):
        await channel_stop.stop_channel("stopper", channel)

    assert channel.stop_started.is_set()
    assert caplog.text == ""


@pytest.mark.asyncio
async def test_cancelling_the_caller_is_not_swallowed() -> None:
    channel = _StopChannel()
    task = asyncio.create_task(channel_stop.stop_channel("stopper", channel))
    await asyncio.wait_for(channel.stop_started.wait(), _GUARD_SECONDS)

    task.cancel()

    with pytest.raises(asyncio.CancelledError):
        await asyncio.wait_for(task, _GUARD_SECONDS)


async def _restart(gateway: ChannelGateway, channel: BaseChannel) -> None:
    await gateway._restart_channel(channel.name, channel)
    assert channel.name in gateway._channel_tasks


async def _disable(gateway: ChannelGateway, channel: BaseChannel) -> None:
    assert await gateway.disable_channel(channel.name) is True
    assert channel.status == ChannelStatus.DISABLED


async def _remove(gateway: ChannelGateway, channel: BaseChannel) -> None:
    assert await gateway.remove_channel(channel.name) is True
    assert channel.name not in gateway.bus.channels


async def _reload(gateway: ChannelGateway, channel: BaseChannel) -> None:
    assert await gateway.reload_channel(channel.name) is True
    assert channel.name in gateway._channel_tasks


async def _shutdown(gateway: ChannelGateway, channel: BaseChannel) -> None:
    await gateway.stop()
    assert gateway._channel_tasks == {}


@pytest.mark.asyncio
@pytest.mark.parametrize("operation", [_restart, _disable, _remove, _reload, _shutdown])
async def test_a_channel_whose_stop_hangs_does_not_hold_up_the_gateway(
    short_cap: float,
    operation: Callable[[ChannelGateway, BaseChannel], Awaitable[None]],
    caplog: pytest.LogCaptureFixture,
) -> None:
    gateway = ChannelGateway()
    channel = _StopChannel()
    gateway.register(channel)

    with (
        patch.object(gateway, "_run_channel", new=AsyncMock()),
        caplog.at_level(logging.WARNING, logger=channel_stop.logger.name),
    ):
        await asyncio.wait_for(operation(gateway, channel), _GUARD_SECONDS)

    assert channel.stop_started.is_set()
    assert "Channel 'stopper' did not stop within" in caplog.text
