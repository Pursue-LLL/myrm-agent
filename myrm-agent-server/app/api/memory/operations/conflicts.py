"""Memory conflict resolution operations.

[INPUT]
- myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
- app.schemas.memory.crud::{PendingMemoryItem, PendingMemoriesResponse, ResolveConflictRequest} (POS: 记忆 API 通用 Schema 层)

[OUTPUT]
router: 冲突列表与冲突裁决端点

[POS]
待裁决记忆冲突的 API 操作层。读取并裁决 `pending_memories.is_conflict` 记录，复用 Harness 记忆变更（update_memory / add_knowledge）保证新旧事实生命周期一致。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind

from app.api.memory.operations.pending import _record_pending_event
from app.api.memory.utils import get_memory_manager
from app.database.connection import get_session
from app.database.models import PendingMemory
from app.schemas.memory.crud import (
    PendingMemoriesResponse,
    PendingMemoryItem,
    ResolveConflictRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response

logger = logging.getLogger(__name__)

router = APIRouter()


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
