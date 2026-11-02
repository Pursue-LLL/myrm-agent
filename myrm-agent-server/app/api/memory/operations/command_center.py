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
    MemoryCommandEconomicsDashboard,
    MemoryRecallBoundaryData,
    MemoryRepoEvidenceResponse,
)
from app.services.memory.behavioral.measurement_service import BehavioralMeasurementService
from app.services.memory.command_center.command_center import MemoryCommandCenterService
from app.services.memory.command_center.command_center_economics import MemoryEconomicsService
from app.services.memory.evidence.repo_digest_service import RepoHistoryDigestService
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService

router = APIRouter(prefix="/command-center")


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


@router.get("/economics", response_model=MemoryCommandEconomicsDashboard)
async def get_memory_economics(
    session_id: str | None = None,
    limit_turns: int = 50,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandEconomicsDashboard:
    """Return Omri et al. 2026 three-phase economics, turn trajectories, and parasitic memory identification."""
    command_service = MemoryCommandCenterService(db, memory_manager)
    influence = await command_service._insights.build_influence()
    archived_ids = await command_service.get_archived_memory_ids()
    pinned_ids = await command_service.get_pinned_memory_ids()
    active_previews = await command_service.get_active_memory_previews()
    return await MemoryEconomicsService(db).build_economics_dashboard(
        influence=influence,
        session_id=session_id,
        archived_memory_ids=archived_ids,
        pinned_memory_ids=pinned_ids,
        memory_previews=active_previews,
        limit_turns=limit_turns,
    )


@router.post("/actions", response_model=MemoryCommandActionResponse)
async def run_memory_command_action(
    body: MemoryCommandActionRequest,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandActionResponse:
    """Execute a GUI governance action from the command center."""

    if body.target_kind == "pending_memory":
        await run_pending_action(body, memory_manager)
    elif body.target_kind == "shared_context_proposal":
        await run_shared_proposal_action(body, db)
    elif body.target_kind == "conflict_pair" or body.action in ("keep_new", "keep_old", "coexist"):
        await run_conflict_action(body, db, memory_manager)
    else:
        await run_memory_action(body, memory_manager)

    # The pending-review service writes its own, richer ledger events.
    if body.target_kind != "pending_memory":
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
