"""Memory Guardian — facade for periodic autonomous memory maintenance.

[INPUT]
- app.lifecycle.cognitive_clock::(get_clock_coordinator, execute_t2_idle_maintenance)
- app.lifecycle.memory_guardian_ops::(create_guardian_memory_manager, auto_resolve_expired_conflicts,
  purge_expired_archives, harvest_session_blind_spots, sync_external_harness_transcripts)
- app.services.memory.ledger.guardian_policy::(MemoryGuardianPolicy, load_memory_guardian_policy,
  resolve_guardian_intervals, is_within_quiet_window, seconds_until_quiet_window_open, current_local_hour)
- app.services.memory.ledger.guardian_events::(HEALTH_THRESHOLD, record_maintenance_event,
  record_purge_audit, record_conflict_auto_resolve_event, record_health_snapshot, record_guard_unavailable_event)

[OUTPUT]
- start_memory_guardian_scheduler: Start periodic background memory maintenance
- stop_memory_guardian_scheduler: Graceful shutdown
- get_memory_guardian_status: Expose scheduler state for API
- run_memory_guardian_once: Manual trigger entry point (maintenance only)
- run_pattern_discovery_once: Manual trigger entry point (pattern discovery)

[POS]
Server lifecycle tier. Provides memory guardian facade delegation,
maintaining stable public scheduling contracts and manual trigger access.
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal, Optional

from myrm_agent_harness.toolkits.memory.health import MaintenanceReport

from app.lifecycle.cognitive_clock import get_clock_coordinator
from app.lifecycle.memory_guardian_ops import (
    auto_resolve_expired_conflicts,
    create_guardian_memory_manager,
    harvest_session_blind_spots,
    purge_expired_archives,
    sync_external_harness_transcripts,
)
from app.services.memory.ledger.guardian_events import (
    HEALTH_THRESHOLD,
    record_conflict_auto_resolve_event,
    record_guard_unavailable_event,
    record_health_snapshot,
    record_maintenance_event,
    record_purge_audit,
)
from app.services.memory.ledger.guardian_policy import (
    MemoryGuardianPolicy,
    current_local_hour,
    is_within_quiet_window,
    load_memory_guardian_policy,
    resolve_guardian_intervals,
    seconds_until_quiet_window_open,
)

logger = logging.getLogger(__name__)

# Module-level state mirrors for backward compatibility with tests and telemetry
_scheduler_task: Optional[asyncio.Task[None]] = None
_last_run: Optional[float] = None
_next_run: Optional[float] = None
_consecutive_unhealthy: int = 0
_last_pattern_discovery: float = 0.0

_HEALTH_CRITICAL_THRESHOLD = 35
_INITIAL_DELAY_MINUTES = 15
_PATTERN_DISCOVERY_INTERVAL_HOURS = 168  # weekly
_QUIET_WINDOW_RECHECK_SECONDS = 15 * 60

_DEFAULT_POLICY = MemoryGuardianPolicy()
_DEFAULT_INTERVALS = resolve_guardian_intervals(_DEFAULT_POLICY)


def _pattern_discovery_due(
    *,
    now: float,
    last: float,
    interval_hours: float = _PATTERN_DISCOVERY_INTERVAL_HOURS,
) -> bool:
    """Check whether enough time has elapsed since last weekly pattern discovery."""
    return (now - last) >= interval_hours * 3600


async def _run_pattern_discovery_cycle() -> None:
    """Periodic delegate for weekly pattern discovery."""
    from app.lifecycle.pattern_discovery_trigger import (
        run_pattern_discovery_cycle as _cycle,
    )

    await _cycle()


async def run_pattern_discovery_once() -> dict[str, object]:
    """Execute weekly cross-cycle pattern discovery manually once."""
    from app.lifecycle.pattern_discovery_trigger import (
        run_pattern_discovery_once as _trigger,
    )

    return await _trigger()


def get_memory_guardian_status(*, policy: Optional[MemoryGuardianPolicy] = None) -> dict[str, object]:
    """Return current memory guardian scheduler status for API consumption."""
    active_policy = policy or _DEFAULT_POLICY
    intervals = resolve_guardian_intervals(active_policy)
    quiet_window_open = is_within_quiet_window(policy=active_policy)
    return {
        "running": _scheduler_task is not None and not _scheduler_task.done(),
        "last_run": _last_run,
        "next_run": _next_run,
        "healthy_interval_hours": intervals.healthy_hours,
        "unhealthy_interval_hours": intervals.unhealthy_hours,
        "health_threshold": HEALTH_THRESHOLD,
        "seconds_until_next": max(0.0, _next_run - time.time()) if _next_run else None,
        "consecutive_unhealthy": _consecutive_unhealthy,
        "last_pattern_discovery": _last_pattern_discovery,
        "frequency_tier": active_policy.frequency_tier,
        "quiet_window_enabled": active_policy.quiet_window_enabled,
        "quiet_window_start_hour": active_policy.quiet_window_start_hour,
        "quiet_window_end_hour": active_policy.quiet_window_end_hour,
        "timezone_offset_minutes": active_policy.timezone_offset_minutes,
        "local_hour": current_local_hour(policy=active_policy),
        "within_quiet_window": quiet_window_open,
        "seconds_until_quiet_window": (
            seconds_until_quiet_window_open(policy=active_policy)
            if active_policy.quiet_window_enabled and not quiet_window_open
            else 0
        ),
    }


async def _record_guard_unavailable(*, reason: str, guard: str, policy: MemoryGuardianPolicy) -> None:
    """Report a guard-unavailable skip to telemetry and persist its audit event."""
    from app.services.agent.memory_guardian_guard_telemetry import (
        enqueue_memory_guardian_guard_telemetry,
    )

    enqueue_memory_guardian_guard_telemetry(
        reason=reason,
        guard=guard,
        frequency_tier=policy.frequency_tier,
        quiet_window_enabled=policy.quiet_window_enabled,
    )
    await record_guard_unavailable_event(reason=reason, guard=guard, policy=policy)


async def _run_sqlite_backup() -> None:
    """Trigger SQLite backup if configured."""
    try:
        from app.database.operations.backup import get_sqlite_backup_manager

        mgr = get_sqlite_backup_manager()
        if mgr:
            await mgr.create_backup(label="memory_guardian")
    except Exception as exc:
        logger.warning("Memory guardian: backup failed: %s", exc)


async def _run_guardian_cycle(
    *,
    force: bool = False,
    policy: Optional[MemoryGuardianPolicy] = None,
) -> tuple[Optional[MaintenanceReport], Optional[str]]:
    """Execute a single memory maintenance cycle with guards."""
    global _last_run, _consecutive_unhealthy
    active_policy = policy or await load_memory_guardian_policy()

    if not force and active_policy.quiet_window_enabled and not is_within_quiet_window(policy=active_policy):
        return None, "outside_quiet_window"

    if not force:
        try:
            from app.services.agent.gateway import get_agent_gateway

            gw = get_agent_gateway()
            if gw and gw.active_count > 0:
                return None, "active_sessions"
        except Exception:
            await _record_guard_unavailable(
                reason="active_session_guard_unavailable",
                guard="active_session",
                policy=active_policy,
            )
            return None, "active_session_guard_unavailable"

        try:
            from app.services.budget.enforcer import should_block_execution

            if await should_block_execution():
                return None, "budget_blocked"
        except Exception:
            await _record_guard_unavailable(
                reason="budget_guard_unavailable",
                guard="budget",
                policy=active_policy,
            )
            return None, "budget_guard_unavailable"

    from myrm_agent_harness.runtime.maintenance.protocols import (
        CapacityDenial,
        MaintenanceTaskType,
    )
    from myrm_agent_harness.runtime.maintenance.scheduler import (
        get_maintenance_scheduler,
    )

    adaptive_scheduler = None
    ticket = None
    if not force:
        try:
            adaptive_scheduler = get_maintenance_scheduler()
        except Exception:
            await _record_guard_unavailable(
                reason="capacity_guard_unavailable",
                guard="capacity",
                policy=active_policy,
            )
            return None, "capacity_guard_unavailable"

        if adaptive_scheduler:
            try:
                ticket_or_denial = await adaptive_scheduler.request_capacity(
                    task_type=MaintenanceTaskType.MEMORY_MAINTENANCE,
                )
            except Exception:
                await _record_guard_unavailable(
                    reason="capacity_guard_unavailable",
                    guard="capacity",
                    policy=active_policy,
                )
                return None, "capacity_guard_unavailable"

            if isinstance(ticket_or_denial, CapacityDenial):
                return None, "capacity_denied"
            ticket = ticket_or_denial

    effective_force = force or _consecutive_unhealthy >= 2
    try:
        manager = await create_guardian_memory_manager()
        report = await manager.run_maintenance_cycle(force=effective_force)
        _last_run = time.time()

        if adaptive_scheduler and ticket:
            adaptive_scheduler.report_outcome(ticket.task_type, success=True)

        if report.skipped:
            return report, report.skip_reason

        purged = await purge_expired_archives(manager)
        if purged > 0:
            await record_purge_audit(purged_count=purged, policy=active_policy)

        resolved = await auto_resolve_expired_conflicts()
        if resolved > 0:
            await record_conflict_auto_resolve_event(resolved_count=resolved, policy=active_policy)

        await harvest_session_blind_spots()
        await sync_external_harness_transcripts()
        await record_maintenance_event(report=report, policy=active_policy)

        if report.health is not None:
            await record_health_snapshot(
                health=report.health,
                source="memory_guardian",
                policy=active_policy,
            )

        backup_res = _run_sqlite_backup()
        if asyncio.iscoroutine(backup_res):
            await backup_res
        return report, None
    except Exception as exc:
        if adaptive_scheduler and ticket:
            adaptive_scheduler.report_outcome(ticket.task_type, success=False)
        raise exc


async def run_memory_guardian_once(
    *,
    mode: Literal["safe", "force"] = "safe",
) -> dict[str, object]:
    """Execute a single maintenance cycle on demand via API."""
    force = mode == "force"
    report, skipped_reason = await _run_guardian_cycle(force=force)

    response: dict[str, object] = {
        "triggered": True,
        "mode": mode,
        "applied": report is not None and not report.skipped,
    }
    if skipped_reason:
        response["skipped_reason"] = skipped_reason
    if report and report.health:
        response["health"] = (
            report.health.to_dict() if hasattr(report.health, "to_dict") else report.health
        )
    return response


async def start_memory_guardian_scheduler() -> None:
    """Start periodic memory maintenance coordinator loop."""
    global _scheduler_task, _next_run

    if _scheduler_task is not None:
        return

    coordinator = get_clock_coordinator()
    coordinator.start()
    _scheduler_task = coordinator._loop_task
    _next_run = coordinator._next_run_t2


async def stop_memory_guardian_scheduler() -> None:
    """Stop the memory guardian coordinator."""
    global _scheduler_task, _next_run

    coordinator = get_clock_coordinator()
    await coordinator.stop()
    _scheduler_task = None
    _next_run = None
