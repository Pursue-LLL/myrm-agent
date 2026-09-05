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

from fastapi import APIRouter, Depends
from myrm_agent_harness.api import BehavioralStatsOptions
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
    MemoryEvidencePlaybackResponse,
    MemoryRecallBoundaryData,
    MemoryRepoEvidenceResponse,
)
from app.services.memory.behavioral.measurement_service import BehavioralMeasurementService
from app.services.memory.command_center.command_center import MemoryCommandCenterService
from app.services.memory.evidence.playback_service import EvidencePlaybackService
from app.services.memory.evidence.repo_digest_service import RepoHistoryDigestService
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

router = APIRouter(prefix="/command-center")


@router.get("/evidence/playback", response_model=MemoryEvidencePlaybackResponse)
async def get_evidence_playback(
    source_id: str | None = None,
    message_id: str | None = None,
    channel_id: str | None = None,
    quote_snippet: str | None = None,
    author_id: str | None = None,
    author_name: str | None = None,
    db: AsyncSession = Depends(get_db_session),
) -> MemoryEvidencePlaybackResponse:
    """Return sanitized conversation slice or graceful snapshot for evidence verification."""
    service = EvidencePlaybackService(db)
    return await service.get_playback(
        source_id=source_id,
        message_id=message_id,
        channel_id=channel_id,
        quote_snippet=quote_snippet,
        author_id=author_id,
        author_name=author_name,
    )


@router.get("/repo-evidence/digest", response_model=MemoryRepoEvidenceResponse)
async def get_repo_evidence_digest(
    workspace_path: str | None = None,
    max_commits: int = 5,
) -> MemoryRepoEvidenceResponse:
    """Return structured git repository recent commit and change evidence digest without LLM cost."""
    service = RepoHistoryDigestService()
    return service.get_repo_evidence_digest(
        workspace_path=workspace_path,
        max_commits=max_commits,
    )


@router.get("/behavioral-insights", response_model=MemoryBehavioralInsightsResponse)
async def get_behavioral_insights(
    lookback_days: int = 30,
    offset_minutes: int | None = None,
    client_timezone: str | None = None,
    locale_anchor: str | None = None,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryBehavioralInsightsResponse:
    """Return deterministic zero-model-cost behavioral routine metrics with dynamic timezone & locale stability."""
    service = BehavioralMeasurementService(db, memory_manager)

    # 1. Resolve effective timezone offset
    effective_offset = offset_minutes
    resolved_tz_name = client_timezone
    if effective_offset is None and client_timezone:
        from myrm_agent_harness.api import resolve_utc_offset_minutes

        effective_offset = resolve_utc_offset_minutes(client_timezone)

    final_offset = effective_offset if effective_offset is not None else 0

    opts = BehavioralStatsOptions(offset_minutes=final_offset)
    measurement = await service.measure(options=opts, lookback_days=lookback_days)

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
        offset_minutes=effective_offset,
        detected_timezone=resolved_tz_name,
        locale_anchor=locale_anchor,
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
        return MemoryCommandGraphResponse(has_graph=False, graph_state="storage_disabled")

    graph = memory_manager._graph
    stats_raw = await graph.get_stats()
    if stats_raw.node_count == 0:
        return MemoryCommandGraphResponse(
            has_graph=True,
            graph_state="empty_knowledge",
            stats=MemoryCommandGraphStats(
                node_count=0,
                relationship_count=0,
                node_label_counts=stats_raw.node_label_counts,
                relationship_type_counts=stats_raw.relationship_type_counts,
            ),
        )

    safe_limit = min(max(limit, 1), 300)
    safe_offset = max(offset, 0)
    nodes_raw = await graph.list_nodes(limit=safe_limit, offset=safe_offset)
    # Fetch higher edge limit to prevent cutting off connected clusters
    rels_raw = await graph.list_relationships(limit=min(safe_limit * 3, 600), offset=safe_offset)

    namespaces = [namespace] if namespace else None

    filtered_nodes = [
        n for n in nodes_raw if not namespaces or str(n.properties.get("primary_namespace", "")).strip() in namespaces
    ]
    filtered_node_ids = {n.id for n in filtered_nodes}

    # Degree and conflict tracking for dual-view ranking
    in_degrees: dict[str, int] = {}
    out_degrees: dict[str, int] = {}
    supported_counts: dict[str, int] = {}
    contradicted_counts: dict[str, int] = {}

    edges: list[MemoryCommandGraphEdge] = []
    for r in rels_raw:
        if r.start_id in filtered_node_ids and r.end_id in filtered_node_ids:
            edges.append(
                MemoryCommandGraphEdge(
                    id=r.id,
                    source=r.start_id,
                    target=r.end_id,
                    rel_type=r.rel_type,
                    properties=r.properties,
                )
            )
            out_degrees[r.start_id] = out_degrees.get(r.start_id, 0) + 1
            in_degrees[r.end_id] = in_degrees.get(r.end_id, 0) + 1
            if r.rel_type == "SUPPORTED_BY":
                supported_counts[r.start_id] = supported_counts.get(r.start_id, 0) + 1
            elif r.rel_type == "CONTRADICTED_BY":
                contradicted_counts[r.start_id] = contradicted_counts.get(r.start_id, 0) + 1

    # Extract ranked hubs (Claims prioritized by degree centrality and conflicts)
    from app.schemas.memory.command_center import MemoryCommandGraphHubItem

    ranked_hubs: list[MemoryCommandGraphHubItem] = []
    for n in filtered_nodes:
        in_deg = in_degrees.get(n.id, 0)
        out_deg = out_degrees.get(n.id, 0)
        total_deg = in_deg + out_deg
        supp_cnt = supported_counts.get(n.id, 0)
        contra_cnt = contradicted_counts.get(n.id, 0)

        # Label extraction
        display_label = n.labels[0] if n.labels else "Claim"
        props = n.properties or {}
        snippet = str(props.get("content") or props.get("name") or props.get("quote_snippet") or n.id[:12])
        if len(snippet) > 80:
            snippet = f"{snippet[:77]}..."

        ranked_hubs.append(
            MemoryCommandGraphHubItem(
                id=n.id,
                label=display_label,
                snippet=snippet,
                primary_namespace=str(props.get("primary_namespace", "")) or None,
                degree=total_deg,
                in_degree=in_deg,
                out_degree=out_deg,
                supported_count=supp_cnt,
                contradicted_count=contra_cnt,
                has_conflict=contra_cnt > 0,
            )
        )

    # Sort: conflicted hotspots first, then by total degree descending
    ranked_hubs.sort(key=lambda h: (h.contradicted_count > 0, h.degree, h.supported_count), reverse=True)

    nodes = [MemoryCommandGraphNode(id=n.id, labels=n.labels, properties=n.properties) for n in filtered_nodes]
    stats = MemoryCommandGraphStats(
        node_count=len(nodes),
        relationship_count=len(edges),
        node_label_counts=stats_raw.node_label_counts,
        relationship_type_counts=stats_raw.relationship_type_counts,
    )

    graph_state: Literal["ready", "storage_disabled", "empty_knowledge", "sparse_islands"] = "ready"
    if len(nodes) > 0 and len(edges) == 0:
        graph_state = "sparse_islands"

    return MemoryCommandGraphResponse(
        nodes=nodes,
        edges=edges,
        stats=stats,
        ranked_hubs=ranked_hubs[:30],
        graph_state=graph_state,
        has_graph=True,
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
