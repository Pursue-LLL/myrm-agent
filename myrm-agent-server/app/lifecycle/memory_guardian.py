"""Memory Guardian — periodic autonomous memory maintenance scheduler.

[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager)
- myrm_agent_harness.toolkits.memory.strategies.pattern_discovery (POS: Cross-cycle pattern discovery)
- myrm_agent_harness.runtime.maintenance.scheduler::GlobalAdaptiveScheduler (POS: Load-aware capacity)
- app.database.backup::get_sqlite_backup_manager (POS: SQLite 备份管理器工厂)
- app.services.agent.gateway::AgentGateway (POS: Active session tracking)
- app.services.budget.enforcer::should_block_execution (POS: Budget enforcement)
- app.core.memory.adapters.setup::create_memory_manager (POS: 业务层记忆管理器工厂)
- app.services.memory.operation_ledger::MemoryOperationLedgerService (POS: 记忆操作账本)
- app.services.memory.guardian_policy::MemoryGuardianPolicy (POS: 受约束调度策略)

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

Health Recovery: 连续两个周期 health < critical 阈值后，下一个周期自动 force 维护。
Pattern Discovery: 每 _PATTERN_DISCOVERY_INTERVAL_HOURS 触发一次跨周期行为模式发现。
"""

from __future__ import annotations

import asyncio
import logging
import time
from typing import Literal

from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryOperationStatus
from myrm_agent_harness.toolkits.memory.health import MaintenanceReport

from app.services.memory.guardian_policy import (
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

_HEALTH_THRESHOLD = 70
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
        "health_threshold": _HEALTH_THRESHOLD,
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


async def _create_memory_manager() -> MemoryManager:
    """Create a MemoryManager for background maintenance (no user session context)."""
    from app.core.memory.adapters.setup import create_memory_manager, resolve_context_binding
    from app.services.agent.platform_config import require_platform_embedding_config

    binding = resolve_context_binding(
        namespaces=None,
        agent_id=None,
        channel_id=None,
        conversation_id=None,
        task_id=None,
    )
    embedding_cfg = await require_platform_embedding_config()
    return await create_memory_manager(
        binding,
        embedding_cfg,
        approval_required=False,
    )


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
            await _record_guard_unavailable_event(
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
            await _record_guard_unavailable_event(
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
            await _record_guard_unavailable_event(
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
            await _record_guard_unavailable_event(
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
        manager = await _create_memory_manager()
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
            await _record_maintenance_event(report, forced=effective_force)

    except Exception as exc:
        logger.error("Memory guardian: cycle failed: %s", exc, exc_info=True)
        if adaptive_scheduler and ticket:
            adaptive_scheduler.report_outcome(ticket.task_type, success=False)
        return None, "execution_failed"
    finally:
        if adaptive_scheduler and ticket:
            await adaptive_scheduler.release_capacity(ticket)

    if report and not report.skipped and report.health:
        await _persist_health_snapshot(report, policy=active_policy)

    try:
        purge_mgr = await _create_memory_manager()
        purge_count = await _purge_expired_archives(purge_mgr)
        if purge_count > 0:
            await _record_purge_audit(purge_count)
    except Exception as exc:
        logger.warning("Memory guardian: archive purge pass failed (non-fatal): %s", exc)

    try:
        resolved_count = await _auto_resolve_expired_conflicts()
        if resolved_count > 0:
            logger.info("Memory guardian: auto-resolved %d expired conflicts (keep_old)", resolved_count)
    except Exception as exc:
        logger.warning("Memory guardian: conflict auto-resolve failed (non-fatal): %s", exc)

    _run_sqlite_backup()
    if report and report.skipped:
        return report, report.skip_reason or "maintenance_skipped"
    return report, None


async def _record_maintenance_event(report: MaintenanceReport, *, forced: bool) -> None:
    """Record a single batched audit event for the completed maintenance cycle.

    Follows the bulk-audit pattern (one record per cycle) to avoid flooding
    the operation ledger during routine Guardian sweeps.
    """
    from app.database.connection import get_session
    from app.services.memory.operation_ledger import MemoryOperationLedgerService

    parts: list[str] = []
    if report.forgotten_count:
        parts.append(f"forgot {report.forgotten_count}")
    if report.archived_count:
        parts.append(f"archived {report.archived_count}")
    if report.staleness_removed:
        parts.append(f"stale_removed {report.staleness_removed}")
    if report.staleness_extended:
        parts.append(f"stale_extended {report.staleness_extended}")
    if report.consolidation_merged:
        parts.append(f"merged {report.consolidation_merged}")
    if report.consolidation_corrected:
        parts.append(f"corrected {report.consolidation_corrected}")

    if not parts:
        return

    summary = f"Guardian maintenance: {', '.join(parts)}"
    if forced:
        summary += " [forced]"

    try:
        async with get_session() as db:
            await MemoryOperationLedgerService(db).record_event(
                kind=MemoryOperationKind.MAINTENANCE,
                status=MemoryOperationStatus.SUCCESS,
                summary=summary,
                source="memory_guardian",
                metadata={
                    "forgotten_count": report.forgotten_count,
                    "archived_count": report.archived_count,
                    "staleness_reviewed": report.staleness_reviewed,
                    "staleness_removed": report.staleness_removed,
                    "staleness_extended": report.staleness_extended,
                    "merged_count": report.consolidation_merged,
                    "corrected_count": report.consolidation_corrected,
                    "health_score": report.health.total if report.health else None,
                    "duration_ms": int(report.duration_ms),
                    "forced": forced,
                },
                commit=True,
            )
    except Exception as exc:
        logger.warning("Memory guardian: failed to record maintenance audit event: %s", exc)


async def _record_guard_unavailable_event(
    *,
    reason: str,
    guard: str,
    policy: MemoryGuardianPolicy,
) -> None:
    """Record warning-level observability event when safe guard dependencies are unavailable."""
    from app.services.agent.memory_guardian_guard_telemetry import (
        enqueue_memory_guardian_guard_telemetry,
    )
    from app.database.connection import get_session
    from app.services.memory.operation_ledger import MemoryOperationLedgerService

    enqueue_memory_guardian_guard_telemetry(
        reason=reason,
        guard=guard,
        frequency_tier=policy.frequency_tier,
        quiet_window_enabled=policy.quiet_window_enabled,
    )

    try:
        async with get_session() as db:
            await MemoryOperationLedgerService(db).record_event(
                kind=MemoryOperationKind.MAINTENANCE,
                status=MemoryOperationStatus.WARNING,
                summary="Guardian paused for safety due to temporary dependency status.",
                source="memory_guardian",
                metadata={
                    "operation": "guard_unavailable_skip",
                    "reason": reason,
                    "guard": guard,
                    "frequency_tier": policy.frequency_tier,
                    "quiet_window_enabled": policy.quiet_window_enabled,
                },
                commit=True,
            )
    except Exception as exc:
        logger.warning("Memory guardian: failed to record guard-unavailable warning event: %s", exc)


async def _persist_health_snapshot(
    report: MaintenanceReport,
    *,
    policy: MemoryGuardianPolicy | None = None,
) -> None:
    """Persist Guardian-computed health score so the Command Center shows fresh data."""
    from app.database.connection import get_session
    from app.services.memory.operation_ledger import MemoryOperationLedgerService

    if not report.health:
        return

    active_policy = policy or _DEFAULT_POLICY
    intervals = resolve_guardian_intervals(active_policy)
    health = report.health
    try:
        status_label = "healthy" if health.total >= _HEALTH_THRESHOLD else "unhealthy"
        async with get_session() as db:
            await MemoryOperationLedgerService(db).save_health_snapshot(
                status=status_label,
                total=health.total,
                dimensions=dict(health.dimensions),
                suggestions=list(health.suggestions),
                has_graph=health.has_graph,
                sample_size=health.sample_size,
                guardian_running=_scheduler_task is not None and not _scheduler_task.done(),
                seconds_until_next=int(max(0, _next_run - time.time())) if _next_run else None,
                ttl_seconds=intervals.healthy_hours * 3600,
                commit=True,
            )
    except Exception as exc:
        logger.warning("Memory guardian: failed to persist health snapshot: %s", exc)


async def _record_purge_audit(purge_count: int) -> None:
    """Record an audit event for expired archive purging."""
    from app.database.connection import get_session
    from app.services.memory.operation_ledger import MemoryOperationLedgerService

    try:
        async with get_session() as db:
            await MemoryOperationLedgerService(db).record_event(
                kind=MemoryOperationKind.MAINTENANCE,
                status=MemoryOperationStatus.SUCCESS,
                summary=f"Guardian purged {purge_count} expired archived memories.",
                source="memory_guardian",
                metadata={"purged_count": purge_count, "operation": "archive_ttl_purge"},
                commit=True,
            )
    except Exception as exc:
        logger.warning("Memory guardian: failed to record purge audit event: %s", exc)


async def _auto_resolve_expired_conflicts() -> int:
    """Resolve conflicts whose auto_resolve_at deadline has passed.

    Applies KEEP_OLD (safe default): the old memory stays, the conflicting
    new content is discarded. Returns the number of resolved conflicts.
    """
    from datetime import UTC, datetime as dt

    from sqlalchemy import update

    from app.database.connection import get_session
    from app.database.models import PendingMemory

    now = dt.now(UTC)

    async with get_session() as db:
        stmt = (
            update(PendingMemory)
            .where(
                PendingMemory.is_conflict.is_(True),
                PendingMemory.status == "pending",
                PendingMemory.conflict_auto_resolve_at.isnot(None),
                PendingMemory.conflict_auto_resolve_at <= now,
            )
            .values(
                status="resolved",
                resolved_at=now,
                metadata_json={"resolution": "keep_old", "auto_resolved": True},
            )
        )
        result = await db.execute(stmt)
        await db.commit()
        return result.rowcount  # type: ignore[return-value]


async def _purge_expired_archives(manager: MemoryManager) -> int:
    """Hard-delete archived memories whose archive_expires_at TTL has passed.

    Returns total number of memories purged across all types.
    """
    from datetime import UTC, datetime

    from myrm_agent_harness.toolkits.memory import MemoryType
    from myrm_agent_harness.toolkits.memory.types import MemoryStatus

    total_purged = 0
    for mem_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
        try:
            memories = await manager.list_memories(mem_type, limit=10000, include_archived=True)
            expired_ids: list[str] = []
            now = datetime.now(UTC)

            for m in memories:
                if getattr(m, "status", None) != MemoryStatus.ARCHIVED:
                    continue
                expires_str = getattr(m, "metadata", {}).get("archive_expires_at", "")
                if not expires_str:
                    continue
                try:
                    expires_at = datetime.fromisoformat(expires_str)
                    if now >= expires_at:
                        expired_ids.append(m.id)
                except (ValueError, TypeError):
                    continue

            if not expired_ids:
                continue

            coll = manager.config.semantic_collection if mem_type == MemoryType.SEMANTIC else manager.config.episodic_collection
            deleted = await manager.delete_memory(coll, expired_ids)
            total_purged += deleted
            logger.info(
                "Memory guardian: purged %d/%d expired archived %s memories",
                deleted,
                len(expired_ids),
                mem_type.value,
            )
        except Exception as exc:
            logger.warning("Memory guardian: failed to purge expired %s archives: %s", mem_type.value, exc)
    return total_purged


def _run_sqlite_backup() -> None:
    """Create a SQLite hot-backup after each guardian cycle.

    Runs synchronously (backup is sub-millisecond for typical database sizes)
    and never raises — failures are logged but do not block the guardian.
    """
    try:
        from app.database.backup import get_sqlite_backup_manager

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

            mgr = await _create_memory_manager()
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
                        if report.health.total >= _HEALTH_THRESHOLD
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
