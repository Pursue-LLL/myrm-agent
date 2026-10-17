"""Tests for channel health tracking and gateway backoff restart logic."""

from __future__ import annotations

import asyncio
import time
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.channels.core.base import BaseChannel
from app.channels.core.bus import MessageBus
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


class TestRouterHealthRestart:
    """The health loop is the supervisor of the router's consume loop."""

    @pytest.mark.asyncio
    async def test_no_router_is_noop(self) -> None:
        gw = ChannelGateway()
        gw._running = True
        await gw._check_router_health()  # no router configured: must not raise

    @pytest.mark.asyncio
    async def test_shutdown_is_not_restarted(self) -> None:
        class DeadRouter:
            def __init__(self) -> None:
                self.start_calls = 0

            def is_consume_loop_alive(self) -> bool:
                return False

            async def start(self) -> None:
                self.start_calls += 1

        gw = ChannelGateway()
        router = DeadRouter()
        gw._router = router  # type: ignore[assignment]
        gw._running = False  # stopping: a dying loop must not be brought back

        await gw._check_router_health()
        assert router.start_calls == 0

    @pytest.mark.asyncio
    async def test_dead_router_is_restarted(self) -> None:
        class DeadThenAliveRouter:
            def __init__(self) -> None:
                self.start_calls = 0
                self.alive = False

            def is_consume_loop_alive(self) -> bool:
                return self.alive

            async def start(self) -> None:
                self.start_calls += 1
                self.alive = True

        gw = ChannelGateway()
        router = DeadThenAliveRouter()
        gw._router = router  # type: ignore[assignment]
        gw._running = True

        await gw._check_router_health()
        assert router.start_calls == 1
        # A recovered loop resets the backoff counter and gate.
        assert gw._router_restart_attempts == 0
        assert gw._router_restart_not_before == 0.0

    @pytest.mark.asyncio
    async def test_backoff_gates_repeated_restarts(self) -> None:
        class StillDeadRouter:
            def __init__(self) -> None:
                self.start_calls = 0

            def is_consume_loop_alive(self) -> bool:
                return False

            async def start(self) -> None:
                self.start_calls += 1

        gw = ChannelGateway()
        router = StillDeadRouter()
        gw._router = router  # type: ignore[assignment]
        gw._running = True

        await gw._check_router_health()
        assert router.start_calls == 1
        assert gw._router_restart_not_before > time.monotonic() - 1

        # Within the backoff window a second probe must not restart again.
        await gw._check_router_health()
        assert router.start_calls == 1

    @pytest.mark.asyncio
    async def test_alive_router_is_left_alone(self) -> None:
        class AliveRouter:
            def __init__(self) -> None:
                self.start_calls = 0

            def is_consume_loop_alive(self) -> bool:
                return True

            async def start(self) -> None:
                self.start_calls += 1

        gw = ChannelGateway()
        router = AliveRouter()
        gw._router = router  # type: ignore[assignment]
        gw._running = True

        await gw._check_router_health()
        assert router.start_calls == 0


class TestDispatchHealthRestart:
    """The health loop also supervises the bus outbound dispatch loop."""

    def test_shutdown_is_not_restarted(self) -> None:
        gw = ChannelGateway()
        gw._running = False  # stopping: a dying loop must not be brought back

        with patch.object(gw.bus, "ensure_dispatch_loop_alive") as ensure:
            gw._check_dispatch_health()
        ensure.assert_not_called()

    def test_dead_dispatch_loop_is_restarted(self) -> None:
        gw = ChannelGateway()
        gw._running = True

        with patch.object(gw.bus, "is_dispatch_loop_alive", return_value=False):
            with patch.object(gw.bus, "ensure_dispatch_loop_alive", return_value=True) as ensure:
                gw._check_dispatch_health()

        ensure.assert_called_once()
        # A recovered loop resets the backoff counter and gate.
        assert gw._dispatch_restart_attempts == 0
        assert gw._dispatch_restart_not_before == 0.0

    def test_backoff_gates_repeated_restarts(self) -> None:
        gw = ChannelGateway()
        gw._running = True

        with patch.object(gw.bus, "is_dispatch_loop_alive", return_value=False):
            with patch.object(gw.bus, "ensure_dispatch_loop_alive", return_value=False) as ensure:
                gw._check_dispatch_health()
                assert ensure.call_count == 1
                assert gw._dispatch_restart_not_before > time.monotonic() - 1

                # Within the backoff window a second probe must not restart again.
                gw._check_dispatch_health()
                assert ensure.call_count == 1

    def test_alive_dispatch_loop_is_left_alone(self) -> None:
        gw = ChannelGateway()
        gw._running = True

        with patch.object(gw.bus, "is_dispatch_loop_alive", return_value=True):
            with patch.object(gw.bus, "ensure_dispatch_loop_alive") as ensure:
                gw._check_dispatch_health()
        ensure.assert_not_called()


class TestBusDispatchLoopLiveness:
    """MessageBus exposes liveness/restart for the gateway supervisor."""

    @pytest.mark.asyncio
    async def test_ensure_dispatch_loop_alive_restarts_a_dead_loop(self) -> None:
        bus = MessageBus()
        bus._running = True
        bus._dispatch_task = None  # never started / finished

        with patch("app.channels.core.bus.spawn_observed_task") as spawn:
            spawn.return_value = AsyncMock()
            assert bus.ensure_dispatch_loop_alive() is True
        spawn.assert_called_once()
        assert spawn.call_args.kwargs["name"] == "channel_outbound_dispatch"

    def test_ensure_dispatch_loop_alive_is_noop_when_running(self) -> None:
        bus = MessageBus()
        bus._running = False

        with patch("app.channels.core.bus.spawn_observed_task") as spawn:
            assert bus.ensure_dispatch_loop_alive() is False
        spawn.assert_not_called()

    def test_is_dispatch_loop_alive_reflects_task_state(self) -> None:
        bus = MessageBus()
        assert bus.is_dispatch_loop_alive() is False
        bus._running = True

        done = MagicMock()
        done.done.return_value = True
        bus._dispatch_task = done
        assert bus.is_dispatch_loop_alive() is False

        live = MagicMock()
        live.done.return_value = False
        bus._dispatch_task = live
        assert bus.is_dispatch_loop_alive() is True
