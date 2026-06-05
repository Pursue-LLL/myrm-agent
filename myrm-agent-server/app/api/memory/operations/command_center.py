"""Memory command center endpoint.

[INPUT]
app.services.memory.command_center::MemoryCommandCenterService (POS: 个人大脑指挥中心聚合服务)

[OUTPUT]
router: `/memory/command-center` memory command center snapshot endpoint.

[POS]
记忆指挥中心 API 操作层。将单用户/单沙箱记忆运行快照暴露给设置页 UI。
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryOperationStatus, MemoryType
from myrm_agent_harness.toolkits.memory.types import MemoryStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.dependencies import get_db_session
from app.api.memory.utils import get_crud_memory_manager
from app.database.models.memory import PendingMemory
from app.schemas.memory.command_center import (
    MemoryCommandActionRequest,
    MemoryCommandActionResponse,
    MemoryCommandCenterResponse,
    MemoryCommandDiagnosticActionRequest,
    MemoryCommandDiagnosticActionResponse,
    MemoryCommandGraphEdge,
    MemoryCommandGraphNode,
    MemoryCommandGraphResponse,
    MemoryCommandGraphStats,
    MemoryCommandPlaneSummary,
    MemoryCommandRepairActionRequest,
    MemoryCommandRepairActionResponse,
    MemoryCommandTimelineEvent,
)
from app.services.memory.command_center import MemoryCommandCenterService
from app.services.memory.diagnostic_repair_executor import MemoryDiagnosticRepairExecutor
from app.services.memory.diagnostics import MemoryDiagnosticsService
from app.services.memory.operation_ledger import MemoryOperationLedgerService
from app.services.memory.shared_context import SharedContextService
from app.services.memory.shared_context_materializer import SharedContextProposalMaterializer

router = APIRouter(prefix="/command-center")


@router.get("", response_model=MemoryCommandCenterResponse)
async def get_memory_command_center(
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandCenterResponse:
    """Return the personalized memory command center snapshot."""

    return await MemoryCommandCenterService(db, memory_manager).build_snapshot()


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


@router.get("/graph", response_model=MemoryCommandGraphResponse)
async def get_memory_graph(
    limit: int = 50,
    offset: int = 0,
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandGraphResponse:
    """Return claim graph nodes and edges for visualization."""

    if not memory_manager.has_graph:
        return MemoryCommandGraphResponse(has_graph=False)

    graph = memory_manager._graph
    nodes_raw = await graph.list_nodes(limit=min(max(limit, 1), 200), offset=max(offset, 0))
    rels_raw = await graph.list_relationships(limit=min(max(limit, 1), 200), offset=max(offset, 0))
    stats_raw = await graph.get_stats()

    nodes = [MemoryCommandGraphNode(id=n.id, labels=n.labels, properties=n.properties) for n in nodes_raw]
    edges = [
        MemoryCommandGraphEdge(id=r.id, source=r.start_id, target=r.end_id, rel_type=r.rel_type, properties=r.properties)
        for r in rels_raw
    ]
    stats = MemoryCommandGraphStats(
        node_count=stats_raw.node_count,
        relationship_count=stats_raw.relationship_count,
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
        await _run_pending_action(body, db, memory_manager)
    elif body.target_kind == "shared_context_proposal":
        await _run_shared_proposal_action(body, db)
    else:
        await _run_memory_action(body, memory_manager)

    await MemoryOperationLedgerService(db).record_event(
        kind=_action_to_operation(body.action),
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


@router.post("/diagnostics/actions", response_model=MemoryCommandDiagnosticActionResponse)
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


@router.post("/diagnostics/repairs", response_model=MemoryCommandRepairActionResponse)
async def run_memory_diagnostic_repair(
    body: MemoryCommandRepairActionRequest,
    db: AsyncSession = Depends(get_db_session),
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryCommandRepairActionResponse:
    """Execute a structured Memory Doctor repair plan through a whitelist."""

    result, run = await MemoryDiagnosticRepairExecutor(db, memory_manager).run(body.plan_id, body.mode)
    return MemoryCommandRepairActionResponse(result=result, run=run)


async def _run_pending_action(body: MemoryCommandActionRequest, db: AsyncSession, manager: MemoryManager) -> None:
    pending = await db.get(PendingMemory, body.target_id)
    if pending is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending memory not found")
    if body.action == "approve":
        await manager.approve(body.target_id)
        return
    if body.action == "reject":
        await manager.reject(body.target_id)
        return
    if body.action == "edit":
        if not body.content or not body.content.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Edited memory content is required")
        pending.content = body.content.strip()
        await db.commit()
        return
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported pending memory action")


async def _run_shared_proposal_action(body: MemoryCommandActionRequest, db: AsyncSession) -> None:
    service = SharedContextService(db)
    proposal = await service.get_write_proposal(body.target_id)
    if proposal is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Shared context proposal not found")
    if body.action == "approve":
        await SharedContextProposalMaterializer(db).approve_write_proposal(body.target_id)
        return
    if body.action == "reject":
        await service.set_write_proposal_status(body.target_id, "rejected")
        return
    if body.action == "edit":
        if not body.content or not body.content.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Edited proposal content is required")
        await service.update_write_proposal(body.target_id, content=body.content.strip())
        return
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported shared proposal action")


async def _run_memory_action(body: MemoryCommandActionRequest, manager: MemoryManager) -> None:
    if body.action == "correct":
        if not body.content or not body.content.strip():
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Corrected memory content is required")
        await manager.correct_memory(body.target_id, body.content.strip())
        return
    if body.action == "pin":
        await manager.pin_memory(body.target_id)
        return
    if body.action == "unpin":
        await manager.unpin_memory(body.target_id)
        return
    if body.action == "forget":
        if not body.memory_type:
            await manager.update_memory(body.target_id, status=MemoryStatus.ARCHIVED)
            return
        mem_type = MemoryType(body.memory_type)
        if mem_type == MemoryType.PROFILE:
            await manager.delete_profile(body.target_id)
        elif mem_type == MemoryType.PROCEDURAL:
            await manager.delete_rule(body.target_id)
        else:
            await manager.update_memory(body.target_id, status=MemoryStatus.ARCHIVED)
        return
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported memory action")


def _action_to_operation(action: str) -> MemoryOperationKind:
    if action == "approve":
        return MemoryOperationKind.APPROVE
    if action == "reject":
        return MemoryOperationKind.REJECT
    if action == "correct":
        return MemoryOperationKind.CORRECT
    if action == "forget":
        return MemoryOperationKind.FORGET
    if action in {"pin", "unpin", "edit"}:
        return MemoryOperationKind.WRITE
    return MemoryOperationKind.OBSERVE


def _diagnostic_action_status(run_status: str) -> Literal["completed", "completed_with_findings", "failed"]:
    if run_status == "ready":
        return "completed"
    if run_status in {"warning", "missing"}:
        return "completed_with_findings"
    return "failed"


# ── Consolidation Rollback Endpoints ──


@router.get("/consolidation/last-summary")
async def get_consolidation_last_summary(
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, object]:
    """Get the latest consolidation event summary with rollback availability status."""
    from myrm_agent_harness.toolkits.memory.strategies.consolidation_rollback import (
        get_last_consolidation_summary,
    )

    summary = await get_last_consolidation_summary(memory_manager)
    if summary is None:
        return {"available": False}
    return {"available": True, **summary}


@router.post("/consolidation/rollback")
async def rollback_consolidation(
    memory_manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, object]:
    """Rollback the most recent consolidation cycle."""
    from myrm_agent_harness.toolkits.memory.strategies.consolidation_rollback import (
        get_last_consolidation_summary,
        rollback_last_consolidation,
    )

    summary = await get_last_consolidation_summary(memory_manager)
    if summary is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No consolidation event found to rollback",
        )
    if not summary.get("rollback_available"):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Cannot rollback: some memories were manually modified after consolidation",
        )

    result = await rollback_last_consolidation(memory_manager)
    return {
        "rolled_back": result.rolled_back,
        "skipped_conflict": result.skipped_conflict,
        "errors": result.errors,
        "conflict_ids": result.conflict_ids,
    }
