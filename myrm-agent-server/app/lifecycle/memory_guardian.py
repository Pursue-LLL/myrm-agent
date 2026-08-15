"""Memory Guardian — periodic autonomous memory maintenance scheduler.

[INPUT]
- myrm_agent_harness.toolkits.memory.strategies.pattern_discovery (POS: Cross-cycle pattern discovery)
- myrm_agent_harness.runtime.maintenance.scheduler::GlobalAdaptiveScheduler (POS: Load-aware capacity)
- app.database.operations.backup::get_sqlite_backup_manager (POS: SQLite 备份管理器工厂)
- app.services.agent.gateway::AgentGateway (POS: Active session tracking)
- app.services.budget.enforcer::should_block_execution (POS: Budget enforcement)
- app.lifecycle.memory_guardian_ops::create_guardian_memory_manager (POS: guardian 上下文 MemoryManager 工厂)
- app.services.memory.ledger.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本)
- app.services.memory.ledger.guardian_policy::MemoryGuardianPolicy (POS: 受约束调度策略)

[OUTPUT]
- start_memory_guardian_scheduler: Start periodic background memory maintenance
- stop_memory_guardian_scheduler: Graceful shutdown
- get_memory_guardian_status: Expose scheduler state for API
- run_memory_guardian_once: Manual trigger entry point (maintenance only)
- run_pattern_discovery_once: Manual trigger entry point (pattern discovery)

[POS]
记忆守护者调度器。独立于用户会话的周期性记忆维护，支持频率档位驱动的自适应调度与 quiet window，
用户活跃时自动暂停，预算耗尽时跳过，通过 GlobalAdaptiveScheduler 进行容量控制。
每次维护周期结束后自动创建 SQLite 热备份（通过 SQLiteBackupManager），并将维护结果
（遗忘/归档/合并/纠正计数）以 MAINTENANCE 审计事件写入 operation_ledger，SSE 实时推送
到 Command Center 时间线。

写侧审计事件记录位于 app/services/memory/ledger/guardian_events.py，
维护子任务位于 app/lifecycle/memory_guardian_ops.py，本模块只负责调度与控制流。

Health Recovery: 连续两个周期 health < critical 阈值后，下一个周期自动 force 维护。
Pattern Discovery: 每 _PATTERN_DISCOVERY_INTERVAL_HOURS 触发一次跨周期行为模式发现。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

from myrm_agent_harness.toolkits.memory.health import MaintenanceReport

from app.lifecycle.memory_guardian_ops import (
    auto_resolve_expired_conflicts,
    create_guardian_memory_manager,
    purge_expired_archives,
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

_scheduler_task: asyncio.Task[None] | None = None
_last_run: float | None = None
_next_run: float | None = None

_HEALTH_CRITICAL_THRESHOLD = 35
_INITIAL_DELAY_MINUTES = 15
_PATTERN_DISCOVERY_INTERVAL_HOURS = 168  # weekly
_QUIET_WINDOW_RECHECK_SECONDS = 15 * 60

_DEFAULT_POLICY = MemoryGuardianPolicy()
_DEFAULT_INTERVALS = resolve_guardian_intervals(_DEFAULT_POLICY)

_consecutive_unhealthy: int = 0
_last_pattern_discovery: float = 0.0


def get_memory_guardian_status(*, policy: MemoryGuardianPolicy | None = None) -> dict[str, object]:
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
        "seconds_until_next": max(0, _next_run - time.time()) if _next_run else None,
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
    """Report a guard-unavailable skip to telemetry and persist its audit event.

    Telemetry lives in the agent service domain (lifecycle may depend on it),
    while the ledger audit event stays in the memory ledger domain.
    """
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


async def _run_guardian_cycle(
    *,
    force: bool = False,
    policy: MemoryGuardianPolicy | None = None,
) -> tuple[MaintenanceReport | None, str | None]:
    """Execute a single memory maintenance cycle with all safety guards.

    Returns (MaintenanceReport | None, skipped_reason | None).
    Non-forced mode enforces quiet-window / active-session / budget / capacity guards.
    """
    global _last_run
    active_policy = policy or await load_memory_guardian_policy()

    if not force and active_policy.quiet_window_enabled and not is_within_quiet_window(policy=active_policy):
        logger.debug("Memory guardian: skipped (outside quiet window)")
        return None, "outside_quiet_window"

    if not force:
        try:
            from app.services.agent.gateway import get_agent_gateway

            gateway = get_agent_gateway()
            if gateway and gateway.active_count > 0:
                logger.debug("Memory guardian: skipped (active sessions: %d)", gateway.active_count)
                return None, "active_sessions"
        except Exception as exc:
            logger.warning("Memory guardian: skipped (active-session guard unavailable): %s", exc)
            await _record_guard_unavailable(
                reason="active_session_guard_unavailable",
                guard="active_session",
                policy=active_policy,
            )
            return None, "active_session_guard_unavailable"

        try:
            from app.services.budget.enforcer import should_block_execution

            if await should_block_execution():
                logger.info("Memory guardian: skipped (daily budget exhausted)")
                return None, "budget_blocked"
        except Exception as exc:
            logger.warning("Memory guardian: skipped (budget guard unavailable): %s", exc)
            await _record_guard_unavailable(
                reason="budget_guard_unavailable",
                guard="budget",
                policy=active_policy,
            )
            return None, "budget_guard_unavailable"

    from myrm_agent_harness.runtime.maintenance.protocols import CapacityDenial, MaintenanceTaskType
    from myrm_agent_harness.runtime.maintenance.scheduler import get_maintenance_scheduler

    adaptive_scheduler = None
    ticket = None
    if not force:
        try:
            adaptive_scheduler = get_maintenance_scheduler()
        except Exception as exc:
            logger.warning("Memory guardian: skipped (capacity guard unavailable): %s", exc)
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
        except Exception as exc:
            logger.warning("Memory guardian: skipped (capacity guard request failed): %s", exc)
            await _record_guard_unavailable(
                reason="capacity_guard_unavailable",
                guard="capacity",
                policy=active_policy,
            )
            return None, "capacity_guard_unavailable"
        if isinstance(ticket_or_denial, CapacityDenial):
            logger.info("Memory guardian: skipped (capacity denied: %s)", ticket_or_denial.reason)
            return None, "capacity_denied"
        ticket = ticket_or_denial

    report: MaintenanceReport | None = None
    effective_force = force or _consecutive_unhealthy >= 2
    try:
        manager = await create_guardian_memory_manager()
        report = await manager.run_maintenance_cycle(force=effective_force)
        _last_run = time.time()

        if adaptive_scheduler and ticket:
            adaptive_scheduler.report_outcome(ticket.task_type, success=True)

        if report.skipped:
            logger.info("Memory guardian: cycle skipped (%s)", report.skip_reason)
        else:
            force_tag = " [FORCED]" if effective_force else ""
            logger.info(
                "Memory guardian: cycle complete%s — merged=%d corrected=%d forgotten=%d archived=%d health=%s (%.0fms)",
                force_tag,
                report.consolidation_merged,
                report.consolidation_corrected,
                report.forgotten_count,
                report.archived_count,
                report.health.total if report.health else "N/A",
                report.duration_ms,
            )
            await record_maintenance_event(report, forced=effective_force)

    except Exception as exc:
        logger.error("Memory guardian: cycle failed: %s", exc, exc_info=True)
        if adaptive_scheduler and ticket:
            adaptive_scheduler.report_outcome(ticket.task_type, success=False)
        return None, "execution_failed"
    finally:
        if adaptive_scheduler and ticket:
            await adaptive_scheduler.release_capacity(ticket)

    if report and not report.skipped and report.health:
        await record_health_snapshot(
            report,
            policy=active_policy,
            guardian_running=_scheduler_task is not None and not _scheduler_task.done(),
            seconds_until_next=int(max(0, _next_run - time.time())) if _next_run else None,
        )

    try:
        purge_mgr = await create_guardian_memory_manager()
        purge_count = await purge_expired_archives(purge_mgr)
        if purge_count > 0:
            await record_purge_audit(purge_count)
    except Exception as exc:
        logger.warning("Memory guardian: archive purge pass failed (non-fatal): %s", exc)

    try:
        resolved_count = await auto_resolve_expired_conflicts()
        if resolved_count > 0:
            logger.info("Memory guardian: auto-resolved %d expired conflicts (keep_old)", resolved_count)
            await record_conflict_auto_resolve_event(resolved_count)
    except Exception as exc:
        logger.warning("Memory guardian: conflict auto-resolve failed (non-fatal): %s", exc)

    _run_sqlite_backup()
    if report and report.skipped:
        return report, report.skip_reason or "maintenance_skipped"
    return report, None


def _run_sqlite_backup() -> None:
    """Create a SQLite hot-backup after each guardian cycle.

    Runs synchronously (backup is sub-millisecond for typical database sizes)
    and never raises — failures are logged but do not block the guardian.
    """
    try:
        from app.database.operations.backup import get_sqlite_backup_manager

        manager = get_sqlite_backup_manager()
        if manager is not None:
            manager.create_backup()
    except Exception as exc:
        logger.warning("Memory guardian: SQLite backup failed (non-fatal): %s", exc)


async def run_memory_guardian_once(*, mode: Literal["safe", "force"] = "safe") -> dict[str, object]:
    """Run a single memory guardian cycle on demand (for manual trigger API).

    - safe mode: respects quiet-window / active-session / budget / capacity guards.
    - force mode: bypasses guards and runs one deterministic maintenance pass.
    """
    try:
        if mode not in {"safe", "force"}:
            mode = "safe"
        report, skipped_reason = await _run_guardian_cycle(force=(mode == "force"))
        payload: dict[str, object] = {
            "triggered": True,
            "mode": mode,
            "applied": bool(report is not None and not report.skipped),
        }
        if skipped_reason:
            payload["skipped_reason"] = skipped_reason
        if report and report.health is not None:
            payload["health"] = report.health.to_dict()
        return payload
    except Exception as exc:
        return {"triggered": True, "mode": mode, "applied": False, "error": str(exc)}


async def _run_pattern_discovery_cycle() -> None:
    """Delegate to pattern_discovery_trigger module."""
    from app.lifecycle.pattern_discovery_trigger import run_pattern_discovery_cycle

    await run_pattern_discovery_cycle()


async def run_pattern_discovery_once() -> dict[str, object]:
    """Delegate to pattern_discovery_trigger module."""
    from app.lifecycle.pattern_discovery_trigger import run_pattern_discovery_once as _trigger

    return await _trigger()


async def start_memory_guardian_scheduler() -> None:
    """Start periodic memory maintenance scheduler.

    Initial delay: 15 minutes after startup (let the system stabilize).
    Adaptive interval: 6h when healthy (score >= 70), 2h when unhealthy.
    """
    global _scheduler_task, _next_run

    if _scheduler_task is not None:
        return

    async def guardian_loop() -> None:
        global _next_run, _consecutive_unhealthy, _last_pattern_discovery

        interval_hours = _DEFAULT_INTERVALS.healthy_hours

        await asyncio.sleep(_INITIAL_DELAY_MINUTES * 60)

        try:
            from myrm_agent_harness.toolkits.memory.strategies.pattern_discovery import (
                get_last_pattern_discovery_at,
            )

            mgr = await create_guardian_memory_manager()
            last_ts = await get_last_pattern_discovery_at(mgr)
            if last_ts is not None:
                _last_pattern_discovery = last_ts.timestamp()
                logger.info("Memory guardian: restored last pattern discovery at %s", last_ts.isoformat())
        except Exception:
            pass

        logger.info("Memory guardian: initial delay complete, starting first cycle")

        while True:
            _next_run = time.time() + 1

            try:
                policy = await load_memory_guardian_policy()
                intervals = resolve_guardian_intervals(policy)

                if policy.quiet_window_enabled and not is_within_quiet_window(policy=policy):
                    until_window = max(60, seconds_until_quiet_window_open(policy=policy))
                    sleep_seconds = min(until_window, _QUIET_WINDOW_RECHECK_SECONDS)
                    _next_run = time.time() + sleep_seconds
                    logger.info(
                        "Memory guardian: deferred (quiet window closed), recheck in %d min (window opens in %d min)",
                        max(1, int(sleep_seconds // 60)),
                        max(1, int(until_window // 60)),
                    )
                    await asyncio.sleep(sleep_seconds)
                    continue

                report, _skipped_reason = await _run_guardian_cycle(force=False, policy=policy)

                if report and report.health:
                    if report.health.total < _HEALTH_CRITICAL_THRESHOLD:
                        _consecutive_unhealthy += 1
                    else:
                        _consecutive_unhealthy = 0

                    interval_hours = (
                        intervals.healthy_hours
                        if report.health.total >= HEALTH_THRESHOLD
                        else intervals.unhealthy_hours
                    )
                else:
                    interval_hours = intervals.healthy_hours

                now = time.time()
                pattern_elapsed_h = (now - _last_pattern_discovery) / 3600
                if pattern_elapsed_h >= _PATTERN_DISCOVERY_INTERVAL_HOURS:
                    await _run_pattern_discovery_cycle()
                    _last_pattern_discovery = now

            except Exception as exc:
                logger.error("Memory guardian loop error: %s", exc, exc_info=True)

            sleep_seconds = interval_hours * 3600
            _next_run = time.time() + sleep_seconds
            logger.info("Memory guardian: next cycle in %dh (health-adaptive)", interval_hours)
            await asyncio.sleep(sleep_seconds)

    _scheduler_task = asyncio.create_task(guardian_loop())
    logger.info(
        "Memory guardian scheduler started (initial delay: %dm, adaptive interval: %d-%dh)",
        _INITIAL_DELAY_MINUTES,
        _DEFAULT_INTERVALS.unhealthy_hours,
        _DEFAULT_INTERVALS.healthy_hours,
    )


async def stop_memory_guardian_scheduler() -> None:
    """Stop the memory guardian scheduler."""
    global _scheduler_task, _next_run

    if _scheduler_task is None:
        return

    try:
        _scheduler_task.cancel()
        try:
            await _scheduler_task
        except asyncio.CancelledError:
            pass
        logger.info("[Shutdown] Memory guardian scheduler stopped")
    except Exception as exc:
        logger.error("[Shutdown] Memory guardian scheduler stop failed: %s", exc)
    finally:
        _scheduler_task = None
        _next_run = None
