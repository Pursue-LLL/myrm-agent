"""Guardian write-side audit events for the memory operation ledger.

[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryOperationKind / MemoryOperationStatus
- myrm_agent_harness.toolkits.memory.health::MaintenanceReport
- app.services.agent.memory_guardian_guard_telemetry::enqueue_memory_guardian_guard_telemetry
- app.services.memory.ledger.guardian_policy::MemoryGuardianPolicy / resolve_guardian_intervals

[OUTPUT]
- record_maintenance_event / record_guard_unavailable_event / record_health_snapshot
- record_purge_audit / record_conflict_auto_resolve_event

[POS]
Guardian 写侧账本适配层。统一将维护周期汇总、守卫不可用告警、健康快照、归档清理与
冲突自动解决（keep_old）审计事件写入 operation_ledger；与读侧聚合 operation_ledger_guardian 对称。
"""

from __future__ import annotations

import logging

from myrm_agent_harness.toolkits.memory import MemoryOperationKind, MemoryOperationStatus
from myrm_agent_harness.toolkits.memory.health import MaintenanceReport

from app.services.memory.ledger.guardian_policy import (
    MemoryGuardianPolicy,
    resolve_guardian_intervals,
)

logger = logging.getLogger(__name__)

HEALTH_THRESHOLD = 70


async def record_maintenance_event(report: MaintenanceReport, *, forced: bool) -> None:
    """Record a single batched audit event for the completed maintenance cycle.

    Follows the bulk-audit pattern (one record per cycle) to avoid flooding
    the operation ledger during routine Guardian sweeps.
    """
    from app.database.connection import get_session
    from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

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


async def record_guard_unavailable_event(
    *,
    reason: str,
    guard: str,
    policy: MemoryGuardianPolicy,
) -> None:
    """Record warning-level observability event when safe guard dependencies are unavailable."""
    from app.database.connection import get_session
    from app.services.agent.memory_guardian_guard_telemetry import (
        enqueue_memory_guardian_guard_telemetry,
    )
    from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

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


async def record_health_snapshot(
    report: MaintenanceReport,
    *,
    policy: MemoryGuardianPolicy | None = None,
    guardian_running: bool = False,
    seconds_until_next: int | None = None,
) -> None:
    """Persist Guardian-computed health score so the Command Center shows fresh data."""
    from app.database.connection import get_session
    from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

    if not report.health:
        return

    active_policy = policy or MemoryGuardianPolicy()
    intervals = resolve_guardian_intervals(active_policy)
    health = report.health
    try:
        status_label = "healthy" if health.total >= HEALTH_THRESHOLD else "unhealthy"
        async with get_session() as db:
            await MemoryOperationLedgerService(db).save_health_snapshot(
                status=status_label,
                total=health.total,
                dimensions=dict(health.dimensions),
                suggestions=list(health.suggestions),
                has_graph=health.has_graph,
                sample_size=health.sample_size,
                guardian_running=guardian_running,
                seconds_until_next=seconds_until_next,
                ttl_seconds=intervals.healthy_hours * 3600,
                commit=True,
            )
    except Exception as exc:
        logger.warning("Memory guardian: failed to persist health snapshot: %s", exc)


async def record_purge_audit(purge_count: int) -> None:
    """Record an audit event for expired archive purging."""
    from app.database.connection import get_session
    from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

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


async def record_conflict_auto_resolve_event(count: int) -> None:
    """Record an audit event when the guardian auto-resolves expired conflicts.

    Every silent write-time decision must be logged so the judge's choice
    (keep_old) stays visible in the Command Center timeline and replayable.
    """
    from app.database.connection import get_session
    from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

    try:
        async with get_session() as db:
            await MemoryOperationLedgerService(db).record_event(
                kind=MemoryOperationKind.MAINTENANCE,
                status=MemoryOperationStatus.SUCCESS,
                summary=f"Guardian auto-resolved {count} expired low-risk conflicts (keep_old).",
                source="memory_guardian",
                metadata={
                    "auto_resolved_conflicts": count,
                    "operation": "conflict_auto_resolve",
                    "resolution": "keep_old",
                },
                commit=True,
            )
    except Exception as exc:
        logger.warning("Memory guardian: failed to record conflict auto-resolve audit event: %s", exc)
