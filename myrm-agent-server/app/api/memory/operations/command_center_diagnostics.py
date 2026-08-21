"""Memory command center diagnostic and repair endpoints.

[INPUT]
app.services.memory.diagnostics.diagnostics::MemoryDiagnosticsService (POS: 记忆诊断服务)
app.services.memory.diagnostics.diagnostic.diagnostic_repair_executor::MemoryDiagnosticRepairExecutor (POS: 记忆修复执行器)
app.services.memory.ledger.operation_ledger::MemoryOperationLedgerService (POS: 记忆账本服务)

[OUTPUT]
router: `/command-center/diagnostics` diagnostic actions, history, and repair endpoints.

[POS]
记忆指挥中心诊断与修复 API 操作层。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends
from myrm_agent_harness.toolkits.memory import MemoryManager
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.api.memory.utils import get_crud_memory_manager
from app.database.models.memory import MemoryOperationEventModel
from app.schemas.memory.command_center import (
    MemoryCommandBenchmarkSummary,
    MemoryCommandDiagnosticActionRequest,
    MemoryCommandDiagnosticActionResponse,
    MemoryCommandDiagnosticHistoryItem,
    MemoryCommandDiagnosticHistoryResponse,
    MemoryCommandRepairActionRequest,
    MemoryCommandRepairActionResponse,
)
from app.services.memory.command_center.command_center import MemoryCommandCenterService
from app.services.memory.diagnostics.diagnostic.diagnostic_repair_executor import (
    MemoryDiagnosticRepairExecutor,
)
from app.services.memory.diagnostics.diagnostics import MemoryDiagnosticsService
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService
from app.services.memory.ledger.operation_ledger_guardian import as_aware

router = APIRouter(prefix="/command-center/diagnostics")


def _diagnostic_action_status(
    run_status: str,
) -> Literal["completed", "completed_with_findings", "failed"]:
    if run_status == "ready":
        return "completed"
    if run_status in {"warning", "missing"}:
        return "completed_with_findings"
    return "failed"


def _history_status(status: str, metadata: dict[str, object]) -> Literal["healthy", "degraded", "failed"]:
    explicit = str(metadata.get("status") or "").lower()
    if explicit in {"healthy", "degraded", "failed"}:
        return explicit  # type: ignore[return-value]
    if status == "success":
        failed_count = int(metadata.get("failed_count") or 0)
        return "degraded" if failed_count > 0 else "healthy"
    return "failed"


def _diagnostic_history_item(
    event: MemoryOperationEventModel,
) -> MemoryCommandDiagnosticHistoryItem:
    """Map one diagnostic audit ledger row into a trend-ready history item."""
    metadata = event.metadata_json or {}
    benchmark = None
    if isinstance(metadata.get("benchmark_recall_at_k"), (int, float)):
        categories_raw = metadata.get("benchmark_categories")
        benchmark = MemoryCommandBenchmarkSummary(
            case_count=int(metadata.get("benchmark_case_count") or 0),
            passed_count=int(metadata.get("benchmark_passed_count") or 0),
            recall_at_k=float(metadata["benchmark_recall_at_k"]),
            ndcg_at_k=float(metadata.get("benchmark_ndcg_at_k") or 0.0),
            mrr_score=float(metadata.get("benchmark_mrr_score") or 0.0),
            precision_at_k=float(metadata.get("benchmark_precision_at_k") or 0.0),
            latency_p50_ms=float(metadata.get("benchmark_latency_p50_ms") or 0.0),
            latency_p95_ms=float(metadata.get("benchmark_latency_p95_ms") or 0.0),
            top_k=int(metadata.get("benchmark_top_k") or 5),
            categories=({str(k): str(v) for k, v in categories_raw.items()} if isinstance(categories_raw, dict) else {}),
        )
    embedding_model = metadata.get("benchmark_embedding_model")
    return MemoryCommandDiagnosticHistoryItem(
        run_id=str(metadata.get("diagnostic_run_id") or event.id),
        status=_history_status(event.status, metadata),
        occurred_at=as_aware(event.occurred_at),
        duration_ms=float(metadata.get("duration_ms") or 0.0),
        probe_count=int(metadata.get("probe_count") or 0),
        failed_count=int(metadata.get("failed_count") or 0),
        benchmark=benchmark,
        embedding_model=(embedding_model if isinstance(embedding_model, str) and embedding_model.strip() else None),
    )


@router.post("/actions", response_model=MemoryCommandDiagnosticActionResponse)
async def run_memory_diagnostic_action(
    body: MemoryCommandDiagnosticActionRequest,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandDiagnosticActionResponse:
    """Execute a GUI Memory Doctor action from the command center."""
    command_center = MemoryCommandCenterService(db, memory_manager)
    if body.action == "run_health_refresh":
        await command_center.refresh_health()
    snapshot = await command_center.build_snapshot()
    run = await MemoryDiagnosticsService(db, memory_manager).run_diagnostics(
        health_cache_status=snapshot.health.cache_status,
        runtime=snapshot.runtime,
    )
    return MemoryCommandDiagnosticActionResponse(status=_diagnostic_action_status(run.status), action=body.action, run=run)


@router.get("/history", response_model=MemoryCommandDiagnosticHistoryResponse)
async def list_memory_diagnostic_history(
    limit: int = 24,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
) -> MemoryCommandDiagnosticHistoryResponse:
    """Return persisted Memory Doctor benchmark history for regression trends."""
    events = await MemoryOperationLedgerService(db).list_diagnostic_events(limit=limit, offset=offset)
    items = [_diagnostic_history_item(event) for event in events]
    return MemoryCommandDiagnosticHistoryResponse(items=items)


@router.post("/repairs", response_model=MemoryCommandRepairActionResponse)
async def run_memory_diagnostic_repair(
    body: MemoryCommandRepairActionRequest,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandRepairActionResponse:
    """Execute a structured Memory Doctor repair plan through a whitelist."""
    result, run = await MemoryDiagnosticRepairExecutor(db, memory_manager).run(body.plan_id, body.mode)
    return MemoryCommandRepairActionResponse(result=result, run=run)
