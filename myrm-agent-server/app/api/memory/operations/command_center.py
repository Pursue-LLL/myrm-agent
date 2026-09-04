"""Memory command center endpoint.

[INPUT]
app.services.memory.command_center.command_center::MemoryCommandCenterService (POS: 个人大脑指挥中心聚合服务)

[OUTPUT]
router: `/memory/command-center` memory command center snapshot endpoint.

[POS]
记忆指挥中心 API 操作层。将单用户/单沙箱记忆运行快照暴露给设置页 UI。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
    MemoryOperationStatus,
)
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.api.memory.operations.command_center_actions import (
    action_to_operation,
    run_conflict_action,
    run_memory_action,
    run_pending_action,
    run_shared_proposal_action,
)
from app.api.memory.utils import get_crud_memory_manager
from app.schemas.memory.command_center import (
    MemoryBehavioralInsightsResponse,
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
from app.services.memory.behavioral.measurement_service import BehavioralMeasurementService
from app.services.memory.command_center.command_center import MemoryCommandCenterService
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

router = APIRouter(prefix="/command-center")


@router.get("/behavioral-insights", response_model=MemoryBehavioralInsightsResponse)
async def get_behavioral_insights(
    lookback_days: int = 30,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryBehavioralInsightsResponse:
    """Return deterministic zero-model-cost behavioral routine metrics."""
    service = BehavioralMeasurementService(db, memory_manager)
    measurement = await service.measure(lookback_days=lookback_days)
    return MemoryBehavioralInsightsResponse(
        hour_histogram=measurement.hour_histogram,
        workday_hour_histogram=measurement.workday_hour_histogram,
        weekend_hour_histogram=measurement.weekend_hour_histogram,
        weekday_histogram=measurement.weekday_histogram,
        reply_latency_p50_ms=measurement.reply_latency_p50_ms,
        reply_latency_p90_ms=measurement.reply_latency_p90_ms,
        self_message_count=measurement.self_message_count,
        latency_sample_count=measurement.latency_sample_count,
        channel_distribution=measurement.channel_distribution,
        peak_active_window=measurement.peak_active_window,
        workday_peak_window=measurement.workday_peak_window,
        weekend_peak_window=measurement.weekend_peak_window,
        top_collaborators=measurement.top_collaborators,
        offset_minutes=480,
        source="computed_deterministic",
    )


@router.post("/behavioral-sync")
async def trigger_behavioral_sync(
    lookback_days: int = 30,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, object]:
    """Execute deterministic behavioral measurement and sync qualified profiles."""
    service = BehavioralMeasurementService(db, memory_manager)
    updated_keys = await service.sync_profile_attributes(lookback_days=lookback_days)
    return {
        "status": "success",
        "updated_profile_keys": updated_keys,
        "count": len(updated_keys),
    }


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

    return await MemoryCommandCenterService(db, memory_manager, project_id=project_id or None).build_snapshot()


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

    return await MemoryCommandCenterService(db, memory_manager).build_recall_boundary_snapshot(
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

    if not memory_manager.has_graph or memory_manager._graph is None:
        return MemoryCommandGraphResponse(has_graph=False)

    graph = memory_manager._graph
    safe_limit = min(max(limit, 1), 200)
    safe_offset = max(offset, 0)
    nodes_raw = await graph.list_nodes(limit=safe_limit, offset=safe_offset)
    rels_raw = await graph.list_relationships(limit=safe_limit, offset=safe_offset)
    stats_raw = await graph.get_stats()

    namespaces = [namespace] if namespace else None

    filtered_nodes = [
        n for n in nodes_raw if not namespaces or str(n.properties.get("primary_namespace", "")).strip() in namespaces
    ]
    filtered_node_ids = {n.id for n in filtered_nodes}

    nodes = [MemoryCommandGraphNode(id=n.id, labels=n.labels, properties=n.properties) for n in filtered_nodes]
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
    return MemoryCommandGraphResponse(nodes=nodes, edges=edges, stats=stats, has_graph=True)


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
    elif body.target_kind == "conflict_pair" or body.action in ("keep_new", "keep_old", "coexist"):
        await run_conflict_action(body, db, memory_manager)
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
