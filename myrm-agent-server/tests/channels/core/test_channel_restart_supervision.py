"""The health loop restarts a failing channel once per backoff window, and only while it is ERROR or DEGRADED."""

from __future__ import annotations

import asyncio
import types
from unittest.mock import AsyncMock, patch

import pytest

from app.channels.core import gateway_health
from app.channels.core.base import BaseChannel
from app.channels.core.gateway import ChannelGateway
from app.channels.types import ChannelStatus, OutboundMessage
from tests.channels.providers.telegram.telegram_channel_factories import make_channel

_HOUR_OF_CHECKS = int(3600 / gateway_health._HEALTH_CHECK_INTERVAL)


class _ToggleChannel(BaseChannel):
    name = "toggle"

    def __init__(self, status: ChannelStatus, healthy: bool = False) -> None:
        super().__init__()
        self._status = status
        self.healthy = healthy

    async def send(self, msg: OutboundMessage) -> str | None:
        return None

    async def health_check(self) -> bool:
        return self.healthy


class _SelfRecordingChannel(_ToggleChannel):
    """Records its own failed check in ``health``, as 13 providers do."""

    name = "self-recording"

    async def health_check(self) -> bool:
        if not self.healthy:
            self.health.record_failure("probe failed")
        return self.healthy


class _Clock:
    def __init__(self) -> None:
        self.now = 10_000.0

    def monotonic(self) -> float:
        return self.now


@pytest.fixture
def clock(monkeypatch: pytest.MonkeyPatch) -> _Clock:
    fake = _Clock()
    monkeypatch.setattr(gateway_health, "time", types.SimpleNamespace(monotonic=fake.monotonic))
    return fake


async def _restart_cycles(gateway: ChannelGateway, channel: BaseChannel, clock: _Clock, cycles: int) -> list[int]:
    """Run one health check per interval; return the 1-based checks at which the gateway restarted the channel."""
    restarted: list[int] = []
    with patch.object(gateway, "_restart_channel", new=AsyncMock()) as restart:
        for cycle in range(1, cycles + 1):
            clock.now += gateway_health._HEALTH_CHECK_INTERVAL
            awaited = restart.await_count
            await gateway._check_channel_health(channel.name, channel)
            if restart.await_count > awaited:
                restarted.append(cycle)
    return restarted


@pytest.mark.asyncio
async def test_a_channel_that_stays_in_error_is_restarted_for_as_long_as_it_stays_down(clock: _Clock) -> None:
    gateway = ChannelGateway()
    channel = _ToggleChannel(ChannelStatus.ERROR)

    restarted = await _restart_cycles(gateway, channel, clock, _HOUR_OF_CHECKS)

    assert restarted[:1] == [gateway_health._DEGRADED_THRESHOLD]
    assert len(restarted) >= 10
    assert restarted[-1:] and restarted[-1] >= _HOUR_OF_CHECKS - 10


@pytest.mark.asyncio
async def test_a_running_channel_that_stops_answering_degrades_and_is_restarted(clock: _Clock) -> None:
    gateway = ChannelGateway()
    channel = _ToggleChannel(ChannelStatus.RUNNING)

    restarted = await _restart_cycles(gateway, channel, clock, gateway_health._DEGRADED_THRESHOLD)

    assert channel.status == ChannelStatus.DEGRADED
    assert restarted == [gateway_health._DEGRADED_THRESHOLD]


@pytest.mark.asyncio
async def test_checks_inside_one_backoff_window_restart_the_channel_once() -> None:
    gateway = ChannelGateway()
    channel = _ToggleChannel(ChannelStatus.ERROR)

    with patch.object(gateway, "_restart_channel", new=AsyncMock()) as restart:
        for _ in range(gateway_health._DEGRADED_THRESHOLD + 5):
            await gateway._check_channel_health(channel.name, channel)

    assert restart.await_count == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("status", [ChannelStatus.IDLE, ChannelStatus.STOPPED, ChannelStatus.DISABLED])
async def test_a_channel_that_is_not_meant_to_run_is_never_restarted(clock: _Clock, status: ChannelStatus) -> None:
    gateway = ChannelGateway()
    channel = _ToggleChannel(status)

    restarted = await _restart_cycles(gateway, channel, clock, _HOUR_OF_CHECKS)

    assert restarted == []
    assert channel.status == status


@pytest.mark.asyncio
async def test_a_recovered_channel_forgets_its_backoff_window(clock: _Clock) -> None:
    gateway = ChannelGateway()
    channel = _ToggleChannel(ChannelStatus.ERROR)
    await _restart_cycles(gateway, channel, clock, gateway_health._DEGRADED_THRESHOLD)
    assert channel.name in gateway._channel_restart_not_before

    channel.healthy = True
    await gateway._check_channel_health(channel.name, channel)

    assert channel.name not in gateway._channel_restart_not_before


@pytest.mark.asyncio
async def test_removing_a_channel_clears_its_backoff_window(clock: _Clock) -> None:
    gateway = ChannelGateway()
    channel = _ToggleChannel(ChannelStatus.ERROR)
    gateway.register(channel)
    await _restart_cycles(gateway, channel, clock, gateway_health._DEGRADED_THRESHOLD)
    assert channel.name in gateway._channel_restart_not_before

    await gateway.remove_channel(channel.name)

    assert channel.name not in gateway._channel_restart_not_before


@pytest.mark.asyncio
async def test_reloading_a_channel_clears_its_backoff_window(clock: _Clock) -> None:
    gateway = ChannelGateway()
    channel = _ToggleChannel(ChannelStatus.ERROR)
    gateway.register(channel)
    await _restart_cycles(gateway, channel, clock, gateway_health._DEGRADED_THRESHOLD)
    assert channel.name in gateway._channel_restart_not_before

    with patch.object(gateway, "_run_channel", new=AsyncMock()):
        assert await gateway.reload_channel(channel.name) is True
        await asyncio.sleep(0)

    assert channel.name not in gateway._channel_restart_not_before


@pytest.mark.asyncio
@pytest.mark.parametrize("channel_type", [_ToggleChannel, _SelfRecordingChannel])
async def test_one_failed_check_neither_degrades_nor_restarts_a_channel(
    clock: _Clock, channel_type: type[_ToggleChannel]
) -> None:
    gateway = ChannelGateway()
    channel = channel_type(ChannelStatus.RUNNING)

    restarted = await _restart_cycles(gateway, channel, clock, 1)

    assert restarted == []
    assert channel.status == ChannelStatus.RUNNING
    assert channel.health.consecutive_failures == 1


@pytest.mark.asyncio
@pytest.mark.parametrize("channel_type", [_ToggleChannel, _SelfRecordingChannel])
async def test_the_second_consecutive_failed_check_restarts_a_channel_whoever_counts_it(
    clock: _Clock, channel_type: type[_ToggleChannel]
) -> None:
    gateway = ChannelGateway()
    channel = channel_type(ChannelStatus.RUNNING)

    restarted = await _restart_cycles(gateway, channel, clock, gateway_health._DEGRADED_THRESHOLD)

    assert restarted == [gateway_health._DEGRADED_THRESHOLD]
    assert channel.health.consecutive_failures == gateway_health._DEGRADED_THRESHOLD


@pytest.mark.asyncio
async def test_a_real_telegram_channel_is_restarted_on_the_second_failed_getme_not_the_first(clock: _Clock) -> None:
    """``TelegramChannel.health_check`` records its own failure; the gateway must not record it a second time."""
    gateway = ChannelGateway()
    channel = make_channel()
    channel._status = ChannelStatus.RUNNING

    with patch.object(channel._client, "verify_token", new=AsyncMock(return_value=False)):
        restarted = await _restart_cycles(gateway, channel, clock, gateway_health._DEGRADED_THRESHOLD)

    assert restarted == [gateway_health._DEGRADED_THRESHOLD]
    assert channel.status == ChannelStatus.DEGRADED
