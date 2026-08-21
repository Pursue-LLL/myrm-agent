"""Memory command center endpoint.

[INPUT]
app.services.memory.command_center.command_center::MemoryCommandCenterService (POS: 个人大脑指挥中心聚合服务)

[OUTPUT]
router: `/memory/command-center` memory command center snapshot endpoint.

[POS]
记忆指挥中心 API 操作层。将单用户/单沙箱记忆运行快照暴露给设置页 UI。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
    MemoryOperationKind,
    MemoryOperationStatus,
    MemoryType,
)
from myrm_agent_harness.toolkits.memory.types import MemoryStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.api.memory.utils import get_crud_memory_manager
from app.database.models.memory import MemoryOperationEventModel, PendingMemory
from app.schemas.memory.command_center import (
    MemoryCommandActionRequest,
    MemoryCommandActionResponse,
    MemoryCommandCenterResponse,
    MemoryCommandGraphEdge,
    MemoryCommandGraphNode,
    MemoryCommandGraphResponse,
    MemoryCommandGraphStats,
    MemoryCommandPlaneSummary,
    MemoryCommandTimelineEvent,
    MemoryRecallBoundaryData,
)
from app.services.memory.command_center.command_center import MemoryCommandCenterService
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService
from app.services.memory.ledger.operation_ledger_guardian import as_aware
from app.api.memory.operations.command_center_actions import (
    action_to_operation,
    run_memory_action,
    run_pending_action,
    run_shared_proposal_action,
)

router = APIRouter(prefix="/command-center")


@router.get("", response_model=MemoryCommandCenterResponse)
async def get_memory_command_center(
    project_id: str | None = None,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandCenterResponse:
    """Return the personalized memory command center snapshot.

    Args:
        project_id: Optional project ID to scope the snapshot to a single project's memory spaces.
    """

    return await MemoryCommandCenterService(
        db, memory_manager, project_id=project_id or None
    ).build_snapshot()


@router.get("/events", response_model=list[MemoryCommandTimelineEvent])
async def list_memory_command_events(
    limit: int = 50,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> list[MemoryCommandTimelineEvent]:
    """Return durable memory operation events for live/replay surfaces."""

    snapshot = await MemoryCommandCenterService(db, memory_manager).build_snapshot()
    return snapshot.live_stream[: min(max(limit, 1), 100)]


@router.get("/plane-summary", response_model=MemoryCommandPlaneSummary)
async def get_memory_plane_summary(
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandPlaneSummary:
    """Return a content-free memory health envelope for sandbox control planes."""

    snapshot = await MemoryCommandCenterService(db, memory_manager).build_snapshot()
    return snapshot.plane_summary


@router.get("/recall-boundary", response_model=MemoryRecallBoundaryData)
async def get_memory_recall_boundary(
    agent_id: str | None = None,
    task_id: str | None = None,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryRecallBoundaryData:
    """Return review-first per-task memory recall boundary and candidate/approved partition snapshot."""

    return await MemoryCommandCenterService(
        db, memory_manager
    ).build_recall_boundary_snapshot(
        agent_id=agent_id,
        task_id=task_id,
    )


@router.get("/graph", response_model=MemoryCommandGraphResponse)
async def get_memory_graph(
    limit: int = 50,
    offset: int = 0,
    namespace: str | None = None,
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandGraphResponse:
    """Return claim graph nodes and edges for visualization.

    Args:
        namespace: Filter nodes by primary_namespace property. None = show all.
    """

    if not memory_manager.has_graph:
        return MemoryCommandGraphResponse(has_graph=False)

    graph = memory_manager._graph
    safe_limit = min(max(limit, 1), 200)
    safe_offset = max(offset, 0)
    nodes_raw = await graph.list_nodes(limit=safe_limit, offset=safe_offset)
    rels_raw = await graph.list_relationships(limit=safe_limit, offset=safe_offset)
    stats_raw = await graph.get_stats()

    namespaces = [namespace] if namespace else None

    filtered_nodes = [
        n
        for n in nodes_raw
        if not namespaces
        or str(n.properties.get("primary_namespace", "")).strip() in namespaces
    ]
    filtered_node_ids = {n.id for n in filtered_nodes}

    nodes = [
        MemoryCommandGraphNode(id=n.id, labels=n.labels, properties=n.properties)
        for n in filtered_nodes
    ]
    edges = [
        MemoryCommandGraphEdge(
            id=r.id,
            source=r.start_id,
            target=r.end_id,
            rel_type=r.rel_type,
            properties=r.properties,
        )
        for r in rels_raw
        if r.start_id in filtered_node_ids and r.end_id in filtered_node_ids
    ]
    stats = MemoryCommandGraphStats(
        node_count=len(nodes),
        relationship_count=len(edges),
        node_label_counts=stats_raw.node_label_counts,
        relationship_type_counts=stats_raw.relationship_type_counts,
    )
    return MemoryCommandGraphResponse(
        nodes=nodes, edges=edges, stats=stats, has_graph=True
    )


@router.post("/actions", response_model=MemoryCommandActionResponse)
async def run_memory_command_action(
    body: MemoryCommandActionRequest,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandActionResponse:
    """Execute a GUI governance action from the command center."""

    if body.target_kind == "pending_memory":
        await run_pending_action(body, db, memory_manager)
    elif body.target_kind == "shared_context_proposal":
        await run_shared_proposal_action(body, db)
    else:
        await run_memory_action(body, memory_manager)

    await MemoryOperationLedgerService(db).record_event(
        kind=action_to_operation(body.action),
        status=MemoryOperationStatus.SUCCESS,
        summary=f"Command center action {body.action} completed for {body.target_kind}:{body.target_id}.",
        memory_id=body.target_id if body.target_kind == "memory" else None,
        memory_type=body.memory_type,
        source="memory_command_center",
        target_kind=body.target_kind,
        target_id=body.target_id,
        commit=True,
    )
    return MemoryCommandActionResponse(
        status="success",
        target_kind=body.target_kind,
        target_id=body.target_id,
        action=body.action,
    )


@router.post(
    "/diagnostics/actions", response_model=MemoryCommandDiagnosticActionResponse
)
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
    return MemoryCommandDiagnosticActionResponse(
        status=_diagnostic_action_status(run.status), action=body.action, run=run
    )


@router.get(
    "/diagnostics/history", response_model=MemoryCommandDiagnosticHistoryResponse
)
async def list_memory_diagnostic_history(
    limit: int = 24,
    offset: int = 0,
    db: AsyncSession = Depends(get_db_session),
) -> MemoryCommandDiagnosticHistoryResponse:
    """Return persisted Memory Doctor benchmark history for regression trends."""

    events = await MemoryOperationLedgerService(db).list_diagnostic_events(
        limit=limit, offset=offset
    )
    items = [_diagnostic_history_item(event) for event in events]
    return MemoryCommandDiagnosticHistoryResponse(items=items)


@router.post("/diagnostics/repairs", response_model=MemoryCommandRepairActionResponse)
async def run_memory_diagnostic_repair(
    body: MemoryCommandRepairActionRequest,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandRepairActionResponse:
    """Execute a structured Memory Doctor repair plan through a whitelist."""

    result, run = await MemoryDiagnosticRepairExecutor(db, memory_manager).run(
        body.plan_id, body.mode
    )
    return MemoryCommandRepairActionResponse(result=result, run=run)


def _diagnostic_action_status(
    run_status: str,
) -> Literal["completed", "completed_with_findings", "failed"]:
    if run_status == "ready":
        return "completed"
    if run_status in {"warning", "missing"}:
        return "completed_with_findings"
    return "failed"


def _diagnostic_history_item(
    event: MemoryOperationEventModel,
) -> MemoryCommandDiagnosticHistoryItem:
    """Map one diagnostic audit ledger row into a trend-ready history item.

    Benchmark metrics are reconstructed from metadata keys persisted by
    `MemoryDiagnosticsService._record_run_event`; per-category detail is stored
    under `benchmark_categories` and restored as the summary `categories` map.
    """

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
            categories=(
                {str(k): str(v) for k, v in categories_raw.items()}
                if isinstance(categories_raw, dict)
                else {}
            ),
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
        embedding_model=(
            embedding_model
            if isinstance(embedding_model, str) and embedding_model
            else None
        ),
    )


def _history_status(
    event_status: str, metadata: dict[str, object]
) -> Literal["ready", "warning", "critical", "missing"]:
    diagnostic_status = metadata.get("diagnostic_status")
    if isinstance(diagnostic_status, str) and diagnostic_status in {
        "ready",
        "warning",
        "critical",
        "missing",
    }:
        return diagnostic_status  # type: ignore[return-value]
    if event_status in {"ready", "warning", "critical", "missing"}:
        return event_status  # type: ignore[return-value]
    return "missing"
