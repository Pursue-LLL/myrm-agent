"""Nested multi-frequency cognitive clock coordinator.

[INPUT]
- .activity_sensor::get_activity_sensor
- .wakeup_guard::get_wakeup_guard
- .executors::(execute_t1_session_debounce, execute_t2_idle_maintenance, execute_t3_epoch_discovery)
- app.services.memory.ledger.guardian_policy::(MemoryGuardianPolicy, load_memory_guardian_policy,
  resolve_guardian_intervals, is_within_quiet_window, seconds_until_quiet_window_open, current_local_hour)
- app.services.budget.enforcer::should_block_execution
- myrm_agent_harness.runtime.maintenance.scheduler::get_maintenance_scheduler

[OUTPUT]
- CognitiveClockCoordinator: Central coordinator unifying T0-T3 multi-frequency execution.
- get_clock_coordinator: Singleton accessor.

[POS]
Server lifecycle tier. Direct orchestrator managing nested cognitive clock cycles.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Optional

from myrm_agent_harness.runtime.maintenance.protocols import CapacityDenial, MaintenanceTaskType
from myrm_agent_harness.runtime.maintenance.scheduler import get_maintenance_scheduler
from myrm_agent_harness.toolkits.memory.health import MaintenanceReport

from app.lifecycle.cognitive_clock.activity_sensor import get_activity_sensor
from app.lifecycle.cognitive_clock.executors import (
    execute_t2_idle_maintenance,
    execute_t3_epoch_discovery,
)
from app.lifecycle.cognitive_clock.wakeup_guard import get_wakeup_guard
from app.services.memory.ledger.guardian_events import HEALTH_THRESHOLD
from app.services.memory.ledger.guardian_policy import (
    MemoryGuardianPolicy,
    current_local_hour,
    is_within_quiet_window,
    load_memory_guardian_policy,
    resolve_guardian_intervals,
    seconds_until_quiet_window_open,
)

logger = logging.getLogger(__name__)

_INITIAL_DELAY_MINUTES = 15
_PATTERN_DISCOVERY_INTERVAL_HOURS = 168
_QUIET_WINDOW_RECHECK_SECONDS = 15 * 60


class CognitiveClockCoordinator:
    """Orchestrates nested cognitive clock ticks across four HOPE frequency tiers."""

    def __init__(self) -> None:
        self._loop_task: Optional[asyncio.Task[None]] = None
        self._last_run_t2: Optional[float] = None
        self._next_run_t2: Optional[float] = None
        self._last_run_t3: float = 0.0
        self._consecutive_unhealthy: int = 0
        self._last_skip_reason: Optional[str] = None
        self._consecutive_skips: int = 0
        self._activity_sensor = get_activity_sensor()
        self._wakeup_guard = get_wakeup_guard()

    def is_running(self) -> bool:
        return self._loop_task is not None and not self._loop_task.done()

    def start(self) -> None:
        """Start the background coordinator loop if not already running."""
        if self.is_running():
            return
        self._loop_task = asyncio.create_task(self._main_loop(), name="cognitive_clock_loop")
        logger.info("CognitiveClockCoordinator started")

    async def stop(self) -> None:
        """Stop background coordinator loop gracefully."""
        if self._loop_task and not self._loop_task.done():
            self._loop_task.cancel()
            try:
                await self._loop_task
            except asyncio.CancelledError:
                pass
        self._loop_task = None
        logger.info("CognitiveClockCoordinator stopped")

    async def get_status(self, policy: Optional[MemoryGuardianPolicy] = None) -> dict[str, object]:
        """Return comprehensive status for REST API and Command Center UI."""
        active_policy = policy or await load_memory_guardian_policy()
        intervals = resolve_guardian_intervals(active_policy)
        quiet_open = is_within_quiet_window(policy=active_policy)
        return {
            "running": self.is_running(),
            "last_run": self._last_run_t2,
            "next_run": self._next_run_t2,
            "healthy_interval_hours": intervals.healthy_hours,
            "unhealthy_interval_hours": intervals.unhealthy_hours,
            "health_threshold": HEALTH_THRESHOLD,
            "seconds_until_next": max(0.0, self._next_run_t2 - time.time()) if self._next_run_t2 else None,
            "consecutive_unhealthy": self._consecutive_unhealthy,
            "last_pattern_discovery": self._last_run_t3,
            "frequency_tier": active_policy.frequency_tier,
            "quiet_window_enabled": active_policy.quiet_window_enabled,
            "quiet_window_start_hour": active_policy.quiet_window_start_hour,
            "quiet_window_end_hour": active_policy.quiet_window_end_hour,
            "timezone_offset_minutes": active_policy.timezone_offset_minutes,
            "local_hour": current_local_hour(policy=active_policy),
            "within_quiet_window": quiet_open,
            "seconds_until_quiet_window": (
                seconds_until_quiet_window_open(policy=active_policy)
                if active_policy.quiet_window_enabled and not quiet_open
                else 0
            ),
            "wakeup_grace_period_active": self._wakeup_guard.is_in_grace_period(),
            "user_activity_detected": self._activity_sensor.is_user_active(),
            "seconds_since_last_user_activity": self._activity_sensor.seconds_since_last_activity,
            "last_skip_reason": self._last_skip_reason,
            "consecutive_skips": self._consecutive_skips,
        }

    def _record_skip(self, reason: str) -> tuple[None, str]:
        """Record suppression reason and increment skip counter."""
        self._last_skip_reason = reason
        self._consecutive_skips += 1
        return None, reason

    async def trigger_t2_cycle(
        self,
        force: bool = False,
        policy: Optional[MemoryGuardianPolicy] = None,
    ) -> tuple[Optional[MaintenanceReport], Optional[str]]:
        """Run a single T2 Macro-Idle maintenance cycle checking safety guards."""
        active_policy = policy or await load_memory_guardian_policy()

        # 1. Wakeup Guard: suppress right after system resume
        if not force and self._wakeup_guard.is_in_grace_period():
            logger.info("CognitiveClock T2: suppressed by wakeup smoothing guard")
            return self._record_skip("wakeup_smoothing_active")

        # 2. Activity Sensor: back off if user is actively typing
        if not force and self._activity_sensor.is_user_active():
            logger.info("CognitiveClock T2: suppressed due to foreground user activity")
            return self._record_skip("user_active")

        # 3. Quiet Window Guard
        if not force and active_policy.quiet_window_enabled and not is_within_quiet_window(policy=active_policy):
            return self._record_skip("outside_quiet_window")

        # 4. Active session guard & Budget guard
        if not force:
            try:
                from app.services.agent.gateway import get_agent_gateway

                gw = get_agent_gateway()
                if gw and gw.active_count > 0:
                    return self._record_skip("active_sessions")
            except Exception:
                pass

            try:
                from app.services.budget.enforcer import should_block_execution

                if await should_block_execution():
                    return self._record_skip("budget_blocked")
            except Exception:
                pass

        # 5. Capacity Ticket Guard
        ticket = None
        scheduler = None
        if not force:
            try:
                scheduler = get_maintenance_scheduler()
                if scheduler:
                    ticket_or_denial = await scheduler.request_capacity(
                        task_type=MaintenanceTaskType.MEMORY_MAINTENANCE
                    )
                    if isinstance(ticket_or_denial, CapacityDenial):
                        return self._record_skip("capacity_denied")
                    ticket = ticket_or_denial
            except Exception:
                pass

        try:
            report, skip_reason = await execute_t2_idle_maintenance(force=force, policy=active_policy)
            self._last_run_t2 = time.time()
            if report and not report.skipped:
                self._last_skip_reason = None
                self._consecutive_skips = 0
            elif skip_reason:
                self._last_skip_reason = skip_reason
                self._consecutive_skips += 1

            if report and report.health is not None:
                if report.health.total < HEALTH_THRESHOLD:
                    self._consecutive_unhealthy += 1
                else:
                    self._consecutive_unhealthy = 0
            if scheduler and ticket:
                scheduler.report_outcome(ticket.task_type, success=report is not None and not report.skipped)
            return report, skip_reason
        except Exception as exc:
            if scheduler and ticket:
                scheduler.report_outcome(ticket.task_type, success=False)
            raise exc

    async def _main_loop(self) -> None:
        """Periodic loop advancing T2 and T3 clock cadences."""
        try:
            await asyncio.sleep(_INITIAL_DELAY_MINUTES * 60)
            while True:
                policy = await load_memory_guardian_policy()
                intervals = resolve_guardian_intervals(policy)
                interval_hours = (
                    intervals.unhealthy_hours
                    if self._consecutive_unhealthy > 0
                    else intervals.healthy_hours
                )
                self._next_run_t2 = time.time() + interval_hours * 3600

                report, skip_reason = await self.trigger_t2_cycle(force=False, policy=policy)

                # Transient suppression: fast retry via _QUIET_WINDOW_RECHECK_SECONDS
                if report is None and skip_reason in (
                    "user_active",
                    "wakeup_smoothing_active",
                    "outside_quiet_window",
                    "active_sessions",
                    "capacity_denied",
                ):
                    sleep_seconds = _QUIET_WINDOW_RECHECK_SECONDS
                    self._next_run_t2 = time.time() + sleep_seconds
                    await asyncio.sleep(sleep_seconds)
                    continue

                # Check T3 Weekly Discovery
                now = time.time()
                if (now - self._last_run_t3) >= _PATTERN_DISCOVERY_INTERVAL_HOURS * 3600:
                    await execute_t3_epoch_discovery()
                    self._last_run_t3 = now

                await asyncio.sleep(interval_hours * 3600)
        except asyncio.CancelledError:
            pass
        except Exception as exc:
            logger.error("CognitiveClockCoordinator encountered fatal error: %s", exc, exc_info=True)


_GLOBAL_COORDINATOR: Optional[CognitiveClockCoordinator] = None


def get_clock_coordinator() -> CognitiveClockCoordinator:
    """Return or initialize global CognitiveClockCoordinator singleton."""
    global _GLOBAL_COORDINATOR
    if _GLOBAL_COORDINATOR is None:
        _GLOBAL_COORDINATOR = CognitiveClockCoordinator()
    return _GLOBAL_COORDINATOR
