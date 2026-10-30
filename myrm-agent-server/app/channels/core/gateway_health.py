"""Channel health supervision: the run of one channel, the health loop, backoff and restart.

Health loop:
- Calls ``channel.health_check()`` every ``_HEALTH_CHECK_INTERVAL`` seconds
- Updates ``channel.health`` (ChannelHealth) on success/failure; a failure the channel already recorded in its own
  ``health_check`` is not recorded a second time
- Uses exponential backoff with jitter for restart decisions
- Consecutive failures ≥ DEGRADED_THRESHOLD → DEGRADED (warn only)
- DEGRADED/ERROR channels restart once their own backoff window has elapsed; the window opens when a restart is issued
  and is cleared when the channel is healthy again, removed or reloaded; the restart stops the channel with a capped wait.
  IDLE channels are never restarted
- A dead router consume loop or bus dispatch loop is restarted behind its own backoff

[INPUT]
- channels.core.base::BaseChannel (POS: channel abstract base class)
- channels.core.channel_stop::stop_channel (POS: the capped, logged stop of one channel)
- channels.core.bus::MessageBus (POS: async message bus; types only)
- channels.routing.router::AgentRouter (POS: inbound message routing hub; types only)
- channels.types::ChannelStatus (POS: lifecycle status of a channel)

[OUTPUT]
- ChannelHealthMixin: ``_run_channel`` (start one channel with error isolation), ``_health_loop`` and the checks it runs
  (channel, router consume loop, bus dispatch loop), ``_compute_backoff``, ``_restart_due``, ``_restart_channel``
- _HEALTH_CHECK_INTERVAL, _BASE_BACKOFF, _MAX_BACKOFF, _BACKOFF_FACTOR, _JITTER_RATIO, _DEGRADED_THRESHOLD: the timing and thresholds of the supervision

[POS]
Supervision segment of ``ChannelGateway``: keeps every registered channel, the router consume loop and the bus dispatch
loop running. One failing channel never stops the supervision of the rest.
"""

from __future__ import annotations

import asyncio
import logging
import random
import time
from typing import TYPE_CHECKING

from app.channels.core.base import BaseChannel
from app.channels.core.channel_stop import stop_channel
from app.channels.types import ChannelStatus

if TYPE_CHECKING:
    from app.channels.core.bus import MessageBus
    from app.channels.routing.router import AgentRouter

logger = logging.getLogger(__name__)

_HEALTH_CHECK_INTERVAL = 60.0
_BASE_BACKOFF = 5.0
_MAX_BACKOFF = 300.0
_BACKOFF_FACTOR = 2.0
_JITTER_RATIO = 0.25
_DEGRADED_THRESHOLD = 2


class ChannelHealthMixin:
    """Mixin: run each channel with error isolation and restart what stops being healthy."""

    # Assigned in ``ChannelGateway.__init__``.
    bus: MessageBus
    _channel_tasks: dict[str, asyncio.Task[None]]
    _channel_restart_not_before: dict[str, float]
    _running: bool
    _router: AgentRouter | None
    _router_restart_attempts: int
    _router_restart_not_before: float
    _dispatch_restart_attempts: int
    _dispatch_restart_not_before: float

    async def _run_channel(self, name: str, channel: BaseChannel) -> None:
        """Run a single channel with error isolation."""
        if channel.status == ChannelStatus.DISABLED:
            logger.debug("Channel '%s' registered as disabled, skipping start", name)
            return
        if not channel.should_auto_start():
            logger.debug("Channel '%s' on-demand, staying idle", name)
            return
        try:
            await channel.start()
            if channel.status == ChannelStatus.RUNNING:
                logger.info("Channel '%s' started", name)
            else:
                logger.debug("Channel '%s' idle (not configured)", name)
        except Exception as e:
            logger.warning("Channel '%s' failed to start: %s", name, e)
            channel._status = ChannelStatus.ERROR

    async def _health_loop(self) -> None:
        """Periodic health check with exponential backoff restart."""
        while self._running:
            try:
                await asyncio.sleep(_HEALTH_CHECK_INTERVAL)
            except asyncio.CancelledError:
                break

            await self._check_router_health()
            self._check_dispatch_health()

            # Snapshot: a concurrent credential swap adds/removes channels on this same dict,
            # and awaiting a channel's health check yields control mid-iteration.
            for name, channel in list(self.bus.channels.items()):
                try:
                    await self._check_channel_health(name, channel)
                except Exception:
                    # One misbehaving channel must not stop health monitoring for the rest.
                    logger.exception("Health check failed for channel '%s'", name)

    async def _check_channel_health(self, name: str, channel: BaseChannel) -> None:
        """Run one channel's health check and react to the outcome."""
        if channel.status in (ChannelStatus.STOPPED, ChannelStatus.DISABLED):
            return

        failed_at = channel.health.last_failure_at
        try:
            healthy = await channel.health_check()
        except Exception as exc:
            healthy = False
            logger.warning("Health check exception for '%s': %s", name, exc)

        if healthy:
            if channel.health.consecutive_failures > 0:
                logger.warning(
                    "Channel '%s' recovered after %d failures",
                    name,
                    channel.health.consecutive_failures,
                )
            channel.health.record_success()
            self._channel_restart_not_before.pop(name, None)
            if channel.status == ChannelStatus.DEGRADED:
                channel._status = ChannelStatus.RUNNING
            return

        # Most providers record a failed check in ``health_check`` themselves; recording it here too would count one
        # failure twice and restart the channel on its first transient failure.
        if channel.health.last_failure_at == failed_at:
            channel.health.record_failure()

        failures = channel.health.consecutive_failures
        if failures >= _DEGRADED_THRESHOLD and channel.status == ChannelStatus.RUNNING:
            channel._status = ChannelStatus.DEGRADED
            logger.warning(
                "Channel '%s' degraded (%d consecutive failures)",
                name,
                failures,
            )

        if self._restart_due(name, channel):
            backoff = self._compute_backoff(failures)
            self._channel_restart_not_before[name] = time.monotonic() + backoff
            logger.warning(
                "Channel '%s' restarting (failures=%d, next restart in %.1fs at the earliest)",
                name,
                failures,
                backoff,
            )
            await self._restart_channel(name, channel)

    async def _check_router_health(self) -> None:
        """Restart the router's consume loop if its task has died.

        The loop absorbs a per-message handler error, so a finished task means it ended
        unrecoverably (inbound routing is down while the process still looks healthy). A
        backoff gates restarts so a deterministic startup crash cannot spin this into a
        tight loop; the failure itself is already logged by the task's observer.
        """
        if self._router is None or not self._running or self._router.is_consume_loop_alive():
            return

        now = time.monotonic()
        if now < self._router_restart_not_before:
            return

        self._router_restart_attempts += 1
        backoff = min(
            _BASE_BACKOFF * (_BACKOFF_FACTOR ** (self._router_restart_attempts - 1)),
            _MAX_BACKOFF,
        )
        self._router_restart_not_before = now + backoff

        logger.error(
            "AgentRouter consume loop is not running; restarting (attempt=%d, backoff=%.1fs)",
            self._router_restart_attempts,
            backoff,
        )
        try:
            await self._router.start()
        except Exception:
            logger.exception("AgentRouter restart failed")
            return

        if self._router.is_consume_loop_alive():
            self._router_restart_attempts = 0
            self._router_restart_not_before = 0.0

    def _check_dispatch_health(self) -> None:
        """Restart the bus outbound dispatch loop if its task has died.

        The loop absorbs a per-message failure, so a finished task means it ended unrecoverably
        and no channel can deliver anything. A backoff gates restarts so a deterministic crash
        cannot spin; the failure itself is already logged by the task's observer.
        """
        if not self._running or self.bus.is_dispatch_loop_alive():
            return

        now = time.monotonic()
        if now < self._dispatch_restart_not_before:
            return

        self._dispatch_restart_attempts += 1
        backoff = min(
            _BASE_BACKOFF * (_BACKOFF_FACTOR ** (self._dispatch_restart_attempts - 1)),
            _MAX_BACKOFF,
        )
        self._dispatch_restart_not_before = now + backoff

        logger.error(
            "Outbound dispatch loop is not running; restarting (attempt=%d, backoff=%.1fs)",
            self._dispatch_restart_attempts,
            backoff,
        )
        if self.bus.ensure_dispatch_loop_alive():
            self._dispatch_restart_attempts = 0
            self._dispatch_restart_not_before = 0.0

    @staticmethod
    def _compute_backoff(failures: int) -> float:
        base = min(_BASE_BACKOFF * (_BACKOFF_FACTOR ** (failures - 1)), _MAX_BACKOFF)
        jitter = base * _JITTER_RATIO * (2 * random.random() - 1)
        return base + jitter

    def _restart_due(self, name: str, channel: BaseChannel) -> bool:
        """Whether a failing channel is restarted by this health check.

        The backoff window is kept per channel in ``_channel_restart_not_before``: every health check
        re-stamps ``ChannelHealth.last_failure_at``, so the time since the last failure can never outgrow
        the check interval. IDLE (not configured or on-demand) is left alone because stopping it for a
        restart would turn it STOPPED.
        """
        if channel.status not in (ChannelStatus.ERROR, ChannelStatus.DEGRADED):
            return False
        if channel.health.consecutive_failures < _DEGRADED_THRESHOLD:
            return False
        return time.monotonic() >= self._channel_restart_not_before.get(name, 0.0)

    async def _restart_channel(self, name: str, channel: BaseChannel) -> None:
        """Restart a failed channel."""
        await stop_channel(name, channel)

        old_task = self._channel_tasks.get(name)
        if old_task and not old_task.done():
            old_task.cancel()
            try:
                await old_task
            except asyncio.CancelledError:
                pass

        self._channel_tasks[name] = asyncio.create_task(
            self._run_channel(name, channel),
            name=f"channel-{name}",
        )
