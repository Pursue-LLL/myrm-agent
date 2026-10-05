"""Pending memory operations.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
app.schemas.memory.crud::PendingMemoryItem (POS: 记忆 API 通用 Schema 层)

[OUTPUT]
router: 待处理记忆列表、批准、拒绝、批量操作端点

[POS]
待处理记忆 API 操作层。提供待处理记忆的审批流管理。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryOperationStatus
from myrm_agent_harness.toolkits.memory.types import PendingRecord

from app.api.memory.utils import get_memory_manager
from app.database.connection import get_session
from app.database.models import PendingMemory
from app.schemas.memory.crud import (
    ApproveMemoryRequest,
    BatchMemoryRequest,
    BatchMemoryResponse,
    PendingMemoriesResponse,
    PendingMemoryItem,
    ResolveConflictRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.memory.ledger.operation_ledger import MemoryOperationLedgerService
from app.services.skills.experience_ledger import (
    ExperienceEntityType,
    ExperienceEventType,
    ExperienceLedgerWrite,
    record_experience_event,
)

logger = logging.getLogger(__name__)

router = APIRouter()


async def _load_pending_memory(memory_id: str) -> PendingMemory | None:
    async with get_session() as db:
        return await db.get(PendingMemory, memory_id)


async def _record_pending_event(
    *,
    kind: MemoryOperationKind,
    memory_id: str,
    memory_type: str | None,
    summary: str,
) -> None:
    async with get_session() as db:
        await MemoryOperationLedgerService(db).record_event(
            kind=kind,
            status=MemoryOperationStatus.SUCCESS,
            summary=summary,
            memory_id=memory_id,
            memory_type=memory_type,
            source="memory_pending_api",
            target_kind="pending_memory",
            target_id=memory_id,
            commit=True,
        )


def _record_to_item(r: PendingRecord) -> PendingMemoryItem:
    return PendingMemoryItem(
        id=r.id,
        user_id="sandbox",
        memory_type=r.memory_type.value,
        content=r.content,
        extra_data=r.memory_data,
        source_chat_id=r.source_chat_id,
        source_message_id=r.source_message_id,
        status=r.status,
        created_at=r.created_at,
        resolved_at=r.resolved_at,
        is_conflict=r.is_conflict,
        conflict_old_memory_id=r.conflict_old_memory_id,
        conflict_old_content=r.conflict_old_content,
        conflict_accuracy_score=r.conflict_accuracy_score,
        conflict_importance=r.conflict_importance,
        conflict_auto_resolve_at=r.conflict_auto_resolve_at,
        confidence=r.confidence,
        importance=r.importance,
        kind=r.kind,
        influence_explanation=r.influence_explanation,
        expected_valid_days=r.expected_valid_days,
        tags=r.tags,
    )


@router.get("/pending", response_model=PendingMemoriesResponse)
async def get_pending_memories(
    manager: MemoryManager = Depends(get_memory_manager),
) -> PendingMemoriesResponse:
    """Get pending memories awaiting user approval."""
    if not manager.approval_required:
        return PendingMemoriesResponse(items=[], total=0)
    records = await manager.list_pending()
    total = await manager.count_pending()
    return PendingMemoriesResponse(items=[_record_to_item(r) for r in records], total=total)


@router.post("/pending/{memory_id}/approve")
async def approve_pending_memory(
    memory_id: str,
    request: ApproveMemoryRequest,
    manager: MemoryManager = Depends(get_memory_manager),
) -> StandardSuccessResponse:
    """Approve a pending memory and persist to permanent storage."""
    if not manager.approval_required:
        raise HTTPException(status_code=400, detail="Approval is not enabled")
    pending = await _load_pending_memory(memory_id)
    try:
        await manager.approve(memory_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if pending is not None:
        await record_experience_event(
            ExperienceLedgerWrite(
                event_type=ExperienceEventType.REVIEW_APPROVED,
                entity_type=ExperienceEntityType.REVIEW,
                entity_id=memory_id,
                lineage_id=f"memory:{memory_id}",
                outcome="approved",
                summary=f"Review approved for memory:{memory_id}",
                artifact_refs={"review_type": "memory", "memory_type": pending.memory_type},
                detail={"review_type": "memory", "review_id": memory_id},
            )
        )
        await _record_pending_event(
            kind=MemoryOperationKind.APPROVE,
            memory_id=memory_id,
            memory_type=pending.memory_type,
            summary="Pending memory approved.",
        )
    return create_success_response(data={"status": "approved", "memory_id": memory_id})


@router.post("/pending/{memory_id}/reject")
async def reject_pending_memory(
    memory_id: str,
    manager: MemoryManager = Depends(get_memory_manager),
) -> StandardSuccessResponse:
    """Reject a pending memory (will not be stored)."""
    if not manager.approval_required:
        raise HTTPException(status_code=400, detail="Approval is not enabled")
    pending = await _load_pending_memory(memory_id)
    try:
        await manager.reject(memory_id)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    if pending is not None:
        await record_experience_event(
            ExperienceLedgerWrite(
                event_type=ExperienceEventType.REVIEW_REJECTED,
                entity_type=ExperienceEntityType.REVIEW,
                entity_id=memory_id,
                lineage_id=f"memory:{memory_id}",
                outcome="rejected",
                summary=f"Review rejected for memory:{memory_id}",
                artifact_refs={"review_type": "memory", "memory_type": pending.memory_type},
                detail={"review_type": "memory", "review_id": memory_id},
            )
        )
        await _record_pending_event(
            kind=MemoryOperationKind.REJECT,
            memory_id=memory_id,
            memory_type=pending.memory_type,
            summary="Pending memory rejected.",
        )
    return create_success_response(data={"status": "rejected", "memory_id": memory_id})


@router.post("/pending/batch/approve", response_model=BatchMemoryResponse)
async def batch_approve_memories(
    request: BatchMemoryRequest,
    manager: MemoryManager = Depends(get_memory_manager),
) -> BatchMemoryResponse:
    """Batch approve multiple pending memories and persist to storage."""
    if not manager.approval_required:
        raise HTTPException(status_code=400, detail="Approval is not enabled")
    pending_map = {
        memory_id: pending for memory_id in request.memory_ids if (pending := await _load_pending_memory(memory_id)) is not None
    }
    success, failed = await manager.batch_approve(request.memory_ids)
    for memory_id in request.memory_ids:
        pending = pending_map.get(memory_id)
        if pending is None or memory_id in failed:
            continue
        await record_experience_event(
            ExperienceLedgerWrite(
                event_type=ExperienceEventType.REVIEW_APPROVED,
                entity_type=ExperienceEntityType.REVIEW,
                entity_id=memory_id,
                lineage_id=f"memory:{memory_id}",
                outcome="approved",
                summary=f"Review approved for memory:{memory_id}",
                artifact_refs={"review_type": "memory", "memory_type": pending.memory_type},
                detail={"review_type": "memory", "review_id": memory_id, "batch": True},
            )
        )
        await _record_pending_event(
            kind=MemoryOperationKind.APPROVE,
            memory_id=memory_id,
            memory_type=pending.memory_type,
            summary="Pending memory approved in batch.",
        )
    return BatchMemoryResponse(
        success_count=success,
        failed_count=len(failed),
        failed_ids=failed,
    )


@router.post("/pending/batch/reject", response_model=BatchMemoryResponse)
async def batch_reject_memories(
    request: BatchMemoryRequest,
    manager: MemoryManager = Depends(get_memory_manager),
) -> BatchMemoryResponse:
    """Batch reject multiple pending memories."""
    if not manager.approval_required:
        raise HTTPException(status_code=400, detail="Approval is not enabled")
    pending_map = {
        memory_id: pending for memory_id in request.memory_ids if (pending := await _load_pending_memory(memory_id)) is not None
    }
    count = await manager.batch_reject(request.memory_ids)
    for memory_id in request.memory_ids:
        pending = pending_map.get(memory_id)
        if pending is None:
            continue
        current = await _load_pending_memory(memory_id)
        if current is None or current.status != "rejected":
            continue
        await record_experience_event(
            ExperienceLedgerWrite(
                event_type=ExperienceEventType.REVIEW_REJECTED,
                entity_type=ExperienceEntityType.REVIEW,
                entity_id=memory_id,
                lineage_id=f"memory:{memory_id}",
                outcome="rejected",
                summary=f"Review rejected for memory:{memory_id}",
                artifact_refs={"review_type": "memory", "memory_type": pending.memory_type},
                detail={"review_type": "memory", "review_id": memory_id, "batch": True},
            )
        )
        await _record_pending_event(
            kind=MemoryOperationKind.REJECT,
            memory_id=memory_id,
            memory_type=pending.memory_type,
            summary="Pending memory rejected in batch.",
        )
    return BatchMemoryResponse(
        success_count=count,
        failed_count=len(request.memory_ids) - count,
        failed_ids=[],
    )


# ── Conflict Resolution Endpoints ───────────────────────────────────


def _conflict_to_item(c: PendingMemory) -> PendingMemoryItem:
    metadata = c.metadata_json or {}
    return PendingMemoryItem(
        id=c.id,
        user_id="sandbox",
        memory_type=c.memory_type,
        content=c.content,
        extra_data=metadata,
        status=c.status,
        created_at=c.created_at,
        resolved_at=c.resolved_at,
        is_conflict=True,
        conflict_old_memory_id=c.conflict_old_memory_id,
        conflict_old_content=c.conflict_old_content,
        conflict_accuracy_score=c.conflict_accuracy_score,
        conflict_importance=c.conflict_importance,
        conflict_auto_resolve_at=c.conflict_auto_resolve_at,
        confidence=c.confidence,
        importance=c.conflict_importance
        or (
            float(metadata["importance"])
            if isinstance(metadata.get("importance"), (int, float))
            else None
        ),
        kind=(
            str(metadata.get("projected_category") or metadata.get("kind"))
            if metadata.get("projected_category") or metadata.get("kind")
            else None
        ),
        influence_explanation=(
            str(metadata.get("influence_explanation") or metadata.get("reasoning"))
            if metadata.get("influence_explanation") or metadata.get("reasoning")
            else None
        ),
        expected_valid_days=(
            int(metadata["expected_valid_days"])
            if isinstance(metadata.get("expected_valid_days"), int)
            else None
        ),
        tags=[str(t) for t in metadata.get("tags", []) if isinstance(t, (str, int))]
        if isinstance(metadata.get("tags"), list)
        else [],
    )


@router.get("/conflicts", response_model=PendingMemoriesResponse)
async def get_pending_conflicts(
    manager: MemoryManager = Depends(get_memory_manager),
) -> PendingMemoriesResponse:
    """Get pending memory conflicts awaiting user resolution."""
    from sqlalchemy import select

    async with get_session() as db:
        result = await db.execute(
            select(PendingMemory)
            .where(PendingMemory.is_conflict.is_(True), PendingMemory.status == "pending")
            .order_by(PendingMemory.created_at.desc())
        )
        conflicts = result.scalars().all()

    items = [_conflict_to_item(c) for c in conflicts]
    return PendingMemoriesResponse(items=items, total=len(items))


@router.post("/conflicts/{conflict_id}/resolve")
async def resolve_conflict(
    conflict_id: str,
    request: ResolveConflictRequest,
    manager: MemoryManager = Depends(get_memory_manager),
) -> StandardSuccessResponse:
    """Resolve a memory conflict with a user decision.

    The candidate fact lives on the ``pending_memories.is_conflict`` row; the
    stale counterpart is identified by ``conflict_old_memory_id``. Resolutions
    reuse the harness mutations (``update_memory`` / ``add_knowledge``) so old
    and new facts stay consistent with the rest of the memory lifecycle.
    """
    from sqlalchemy import select

    async with get_session() as db:
        result = await db.execute(
            select(PendingMemory).where(
                PendingMemory.id == conflict_id,
                PendingMemory.is_conflict.is_(True),
            )
        )
        conflict = result.scalar_one_or_none()

    if not conflict or conflict.status != "pending":
        raise HTTPException(status_code=404, detail="Conflict not found or already resolved")

    resolution = request.resolution
    old_memory_id = conflict.conflict_old_memory_id
    candidate_content = conflict.content or ""

    if resolution == "keep_new":
        if old_memory_id:
            await manager.update_memory(old_memory_id, importance=0.01)
        if candidate_content.strip():
            await manager.add_knowledge(candidate_content)
    elif resolution == "keep_old":
        if old_memory_id:
            await manager.update_memory(old_memory_id, confidence=0.95, is_user_locked=True)
    elif resolution == "coexist":
        if old_memory_id:
            await manager.update_memory(old_memory_id, confidence=0.85)
        if candidate_content.strip():
            await manager.add_knowledge(candidate_content)
    elif resolution == "merge":
        if not request.merged_content:
            raise HTTPException(status_code=400, detail="merged_content required for merge resolution")
        if old_memory_id:
            await manager.update_memory(old_memory_id, content=request.merged_content)
    elif resolution == "discard_both":
        if old_memory_id:
            await manager.update_memory(old_memory_id, importance=0.01)
    else:
        raise HTTPException(status_code=400, detail=f"Invalid resolution: {resolution}")

    await _mark_conflict_resolved(conflict_id, resolution)

    await _record_pending_event(
        kind=MemoryOperationKind.APPROVE,
        memory_id=conflict_id,
        memory_type=conflict.memory_type,
        summary=f"Conflict resolved: {resolution}",
    )
    return create_success_response(data={"status": "resolved", "resolution": resolution, "conflict_id": conflict_id})


async def _mark_conflict_resolved(conflict_id: str, resolution: str) -> None:
    from datetime import UTC
    from datetime import datetime as dt

    async with get_session() as db:
        record = await db.get(PendingMemory, conflict_id)
        if record is None:
            return
        record.status = "resolved"
        record.resolved_at = dt.now(UTC)
        record.metadata_json = {**(record.metadata_json or {}), "resolution": resolution}
        await db.commit()
