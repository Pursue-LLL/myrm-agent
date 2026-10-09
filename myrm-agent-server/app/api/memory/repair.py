"""[POS]: app/api/memory/repair.py
[INPUT]: HTTP requests for memory integrity diagnostics, self-healing, stale pruning, and health metrics.
[OUTPUT]: FastAPI APIRouter endpoints managing database self-repair and prompt cache compaction barriers.
"""

from fastapi import APIRouter, Depends
from myrm_agent_harness.toolkits.memory import (
    IntegrityCheckReport,
    MemoryRepairService,
    PruneSummary,
    RepairReport,
    StalePrunePolicy,
)

from app.schemas.memory_repair import (
    IntegrityCheckResponse,
    MemoryHealthResponse,
    PruneStaleRequest,
    PruneStaleResponse,
    RepairDatabaseRequest,
    RepairDatabaseResponse,
)
from app.services.memory.repair import get_memory_repair_service

router = APIRouter(prefix="/repair", tags=["memory_repair"])


@router.get("/check", response_model=IntegrityCheckResponse)
def check_integrity(
    service: MemoryRepairService = Depends(get_memory_repair_service),
) -> IntegrityCheckResponse:
    """Execute non-destructive integrity diagnostics on SQLite and FTS tables."""
    report: IntegrityCheckReport = service.check_integrity()
    return IntegrityCheckResponse(
        db_status=str(report.db_status),
        fts_healthy=report.fts_healthy,
        issues=report.issues,
        checked_at_epoch=report.checked_at_epoch,
        table_counts=report.table_counts,
    )


@router.post("/heal", response_model=RepairDatabaseResponse)
def heal_database(
    _req: RepairDatabaseRequest,
    service: MemoryRepairService = Depends(get_memory_repair_service),
) -> RepairDatabaseResponse:
    """Execute automated self-healing on damaged indexes, FTS tables, and WAL log."""
    report: RepairReport = service.repair_database()
    return RepairDatabaseResponse(
        status=str(report.status),
        repaired_items=report.repaired_items,
        error_details=report.error_details,
        duration_ms=report.duration_ms,
    )


@router.post("/prune", response_model=PruneStaleResponse)
def prune_stale_memories(
    req: PruneStaleRequest,
    service: MemoryRepairService = Depends(get_memory_repair_service),
) -> PruneStaleResponse:
    """Execute adaptive stale memory pruning with prompt cache preservation barrier."""
    policy = StalePrunePolicy(
        stale_days_threshold=req.stale_days_threshold,
        min_recall_count=req.min_recall_count,
        decay_rate=req.decay_rate,
        protect_pinned=req.protect_pinned,
        dry_run=req.dry_run,
    )
    summary: PruneSummary = service.prune_stale_entries(
        table_name=req.table_name,
        policy=policy,
        active_session_id=req.session_id,
    )
    return PruneStaleResponse(
        evaluated_count=summary.evaluated_count,
        archived_count=summary.archived_count,
        protected_count=summary.protected_count,
        archived_ids=summary.archived_ids,
        duration_ms=summary.duration_ms,
    )


@router.get("/health", response_model=MemoryHealthResponse)
def get_memory_health(
    table_name: str = "myrm_memories",
    service: MemoryRepairService = Depends(get_memory_repair_service),
) -> MemoryHealthResponse:
    """Retrieve holistic memory health score, integrity status, and item counts."""
    metric = service.get_health_metric(table_name=table_name)
    return MemoryHealthResponse(
        overall_health_score=metric.overall_health_score,
        total_entries=metric.total_entries,
        active_entries=metric.active_entries,
        stale_entries=metric.stale_entries,
        integrity_status=str(metric.integrity_status),
    )
