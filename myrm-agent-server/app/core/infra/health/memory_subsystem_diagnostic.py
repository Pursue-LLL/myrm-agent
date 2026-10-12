"""Memory subsystem health probe for /health/doctor.

[INPUT]
- app.services.ops.snapshot_service::OpsAggregatedSnapshotService (POS: ops memory ledger probe)

[OUTPUT]
- MemorySubsystemDiagnostic: maps OpsMemoryInfo to HealthReport for the Doctor dashboard.

[POS]
Server-layer diagnostic; reuses ops snapshot memory aggregation (SSOT with GET /ops/snapshot).
"""

from __future__ import annotations

from myrm_agent_harness.observability.diagnostics.protocols import DiagnosticProtocol, HealthReport

from app.services.ops.snapshot_service import OpsAggregatedSnapshotService


class MemorySubsystemDiagnostic(DiagnosticProtocol):
    """Surface memory ledger health, extract retry backlog, and storage mode in Doctor."""

    async def check_health(self) -> HealthReport:
        info = await OpsAggregatedSnapshotService._collect_memory_info()
        meta = {
            "health_status": info.health_status,
            "storage_mode": info.storage_mode,
            "event_count": info.event_count,
            "failed_event_count": info.failed_event_count,
            "queue_backlog": info.queue_backlog,
        }
        metrics = {
            "memory_operation_events_total": float(info.event_count),
            "memory_operation_events_error": float(info.failed_event_count),
            "memory_extract_retry_pending": float(info.queue_backlog),
        }

        if info.health_status == "critical":
            return HealthReport(
                component_name="MemorySubsystem",
                status="fail",
                code="ERR_MEMORY_LEDGER_PROBE",
                meta_data=meta,
                metrics=metrics,
                message="Memory subsystem health check failed.",
                detail="Could not probe memory_operation_events or extract retry queue.",
                fix_suggestion="Check database connectivity and server logs, then open Settings → Memory.",
            )

        if info.health_status == "degraded" or info.failed_event_count > 0 or info.queue_backlog > 0:
            detail_parts: list[str] = []
            if info.failed_event_count > 0:
                detail_parts.append(f"{info.failed_event_count} ledger error event(s)")
            if info.queue_backlog > 0:
                detail_parts.append(f"{info.queue_backlog} pending extract retry(ies)")
            return HealthReport(
                component_name="MemorySubsystem",
                status="warn",
                code="WARN_MEMORY_SUBSYSTEM_DEGRADED",
                meta_data=meta,
                metrics=metrics,
                message="Memory subsystem needs attention.",
                detail=", ".join(detail_parts) if detail_parts else "Memory health is degraded.",
                fix_suggestion="Open Settings → Memory Command Center to review recent operations.",
            )

        return HealthReport(
            component_name="MemorySubsystem",
            status="pass",
            code="PASS_MEMORY_SUBSYSTEM",
            meta_data=meta,
            metrics=metrics,
            message="Memory subsystem is healthy.",
            detail=f"Storage mode: {info.storage_mode}. Ledger events: {info.event_count}.",
        )
