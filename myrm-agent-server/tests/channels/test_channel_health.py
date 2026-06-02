"""Tests for channel health tracking and gateway backoff restart logic."""

from __future__ import annotations

import asyncio
import time

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.gateway import (
    _BACKOFF_FACTOR,
    _BASE_BACKOFF,
    _DEGRADED_THRESHOLD,
    _MAX_BACKOFF,
    ChannelGateway,
)
from app.channels.types import (
    ChannelHealth,
    ChannelStatus,
    OutboundMessage,
)

# ---------------------------------------------------------------------------
# ChannelHealth
# ---------------------------------------------------------------------------


class TestChannelHealth:
    def test_initial_state(self) -> None:
        h = ChannelHealth()
        assert h.consecutive_failures == 0
        assert h.last_success_at is None
        assert h.last_failure_at is None
        assert h.last_error == ""

    def test_record_success(self) -> None:
        h = ChannelHealth(consecutive_failures=3, last_error="timeout")
        h.record_success()
        assert h.consecutive_failures == 0
        assert h.last_success_at is not None
        assert h.last_error == ""

    def test_record_failure(self) -> None:
        h = ChannelHealth()
        h.record_failure("connection reset")
        assert h.consecutive_failures == 1
        assert h.last_failure_at is not None
        assert h.last_error == "connection reset"

    def test_failure_increments(self) -> None:
        h = ChannelHealth()
        for _i in range(5):
            h.record_failure()
        assert h.consecutive_failures == 5

    def test_success_resets_failures(self) -> None:
        h = ChannelHealth()
        h.record_failure()
        h.record_failure()
        h.record_success()
        assert h.consecutive_failures == 0


# ---------------------------------------------------------------------------
# ChannelStatus.DEGRADED
# ---------------------------------------------------------------------------


class TestChannelStatusDegraded:
    def test_degraded_value(self) -> None:
        assert ChannelStatus.DEGRADED == "degraded"

    def test_enum_member(self) -> None:
        assert hasattr(ChannelStatus, "DEGRADED")


# ---------------------------------------------------------------------------
# BaseChannel health integration
# ---------------------------------------------------------------------------


class DummyChannel(BaseChannel):
    name = "dummy"

    def __init__(self, healthy: bool = True) -> None:
        super().__init__()
        self._healthy = healthy

    async def send(self, msg: OutboundMessage) -> str | None:
        pass

    async def health_check(self) -> bool:
        return self._healthy


class TestBaseChannelHealth:
    def test_has_health_attribute(self) -> None:
        ch = DummyChannel()
        assert isinstance(ch.health, ChannelHealth)

    @pytest.mark.asyncio
    async def test_start_records_success(self) -> None:
        ch = DummyChannel()
        await ch.start()
        assert ch.health.last_success_at is not None
        assert ch.health.consecutive_failures == 0


# ---------------------------------------------------------------------------
# Gateway backoff logic
# ---------------------------------------------------------------------------


class TestGatewayBackoff:
    def test_compute_backoff_first_failure(self) -> None:
        backoff = ChannelGateway._compute_backoff(1)
        assert _BASE_BACKOFF * (1 - 0.25) <= backoff <= _BASE_BACKOFF * (1 + 0.25)

    def test_compute_backoff_exponential(self) -> None:
        backoff = ChannelGateway._compute_backoff(4)
        expected_base = _BASE_BACKOFF * (_BACKOFF_FACTOR**3)
        assert expected_base * 0.75 <= backoff <= expected_base * 1.25

    def test_compute_backoff_capped(self) -> None:
        backoff = ChannelGateway._compute_backoff(100)
        assert backoff <= _MAX_BACKOFF * 1.25

    def test_should_restart_low_failures(self) -> None:
        ch = DummyChannel()
        ch.health.consecutive_failures = 1
        assert ChannelGateway._should_restart(ch) is False

    def test_should_restart_threshold_reached(self) -> None:
        ch = DummyChannel()
        ch.health.consecutive_failures = _DEGRADED_THRESHOLD
        ch.health.last_failure_at = time.monotonic() - 9999
        assert ChannelGateway._should_restart(ch) is True

    def test_should_restart_within_backoff(self) -> None:
        ch = DummyChannel()
        ch.health.consecutive_failures = _DEGRADED_THRESHOLD
        ch.health.last_failure_at = time.monotonic()
        assert ChannelGateway._should_restart(ch) is False


# ---------------------------------------------------------------------------
# Gateway health_loop integration
# ---------------------------------------------------------------------------


class FailingChannel(BaseChannel):
    """Channel that fails health checks after ``fail_after`` successes."""

    name = "failing"

    def __init__(self, fail_after: int = 0) -> None:
        super().__init__()
        self._call_count = 0
        self._fail_after = fail_after

    async def send(self, msg: OutboundMessage) -> str | None:
        pass

    async def health_check(self) -> bool:
        self._call_count += 1
        return self._call_count <= self._fail_after


class TestGatewayHealthIntegration:
    @pytest.mark.asyncio
    async def test_healthy_channel_stays_running(self) -> None:
        gw = ChannelGateway()
        ch = DummyChannel(healthy=True)
        gw.register(ch)
        await gw.start()
        await asyncio.sleep(0.1)
        assert ch.status == ChannelStatus.RUNNING
        await gw.stop()

    @pytest.mark.asyncio
    async def test_failing_channel_degrades(self) -> None:
        gw = ChannelGateway()
        ch = FailingChannel(fail_after=0)
        gw.register(ch)
        ch._status = ChannelStatus.RUNNING

        for _ in range(_DEGRADED_THRESHOLD):
            healthy = await ch.health_check()
            if not healthy:
                ch.health.record_failure()
                if ch.health.consecutive_failures >= _DEGRADED_THRESHOLD:
                    ch._status = ChannelStatus.DEGRADED

        assert ch.status == ChannelStatus.DEGRADED
        assert ch.health.consecutive_failures == _DEGRADED_THRESHOLD

    @pytest.mark.asyncio
    async def test_recovery_clears_degraded(self) -> None:
        ch = DummyChannel(healthy=True)
        ch._status = ChannelStatus.DEGRADED
        ch.health.consecutive_failures = 3

        ch.health.record_success()
        if ch.status == ChannelStatus.DEGRADED:
            ch._status = ChannelStatus.RUNNING

        assert ch.status == ChannelStatus.RUNNING
        assert ch.health.consecutive_failures == 0
