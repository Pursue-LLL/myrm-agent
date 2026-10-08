"""Pending memory operations.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
app.schemas.memory.crud::PendingMemoryItem (POS: 记忆 API 通用 Schema 层)
app.services.memory.operations.pending_review::{approve_pending, reject_pending, batch_approve_pending, batch_reject_pending} (POS: 审批队列统一审批与审计入口)

[OUTPUT]
router: 待处理记忆列表、批准、拒绝、批量操作端点

[POS]
待处理记忆 API 操作层。提供待处理记忆的审批流管理。
"""

import logging

from fastapi import APIRouter, Depends, HTTPException
from myrm_agent_harness.toolkits.memory import (
    InvalidPendingEditError,
    MemoryManager,
    MemoryNotFoundError,
)
from myrm_agent_harness.toolkits.memory.types import PendingRecord

from app.api.memory.utils import get_memory_manager
from app.schemas.memory.crud import (
    ApproveMemoryRequest,
    BatchMemoryRequest,
    BatchMemoryResponse,
    PendingMemoriesResponse,
    PendingMemoryItem,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.memory.operations.pending_review import (
    PendingReviewSource,
    approve_pending,
    batch_approve_pending,
    batch_reject_pending,
    reject_pending,
)

logger = logging.getLogger(__name__)

router = APIRouter()


def _raise_approval_http_error(exc: Exception) -> None:
    """Map a harness approval failure to the right HTTP status.

    A missing record is a 404; an unusable edit (blank, or on a proposal without
    editable text) is a 400; any other failure (wrong memory type, storage error)
    is a server-side 500 — never a misleading 404.
    """
    if isinstance(exc, MemoryNotFoundError):
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    if isinstance(exc, InvalidPendingEditError):
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    logger.error("Memory approval failed", exc_info=True)
    raise HTTPException(status_code=500, detail="Memory approval failed") from exc


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
        resolution_action=r.resolution_action.value if r.resolution_action is not None else None,
        target_memory_id=r.target_memory_id,
        target_content=r.target_content,
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


# Batch routes MUST be declared before the ``/pending/{memory_id}/...`` routes:
# Starlette matches in registration order, so a parameterized route declared
# first would capture "batch" as a memory_id and shadow these handlers.
@router.post("/pending/batch/approve", response_model=BatchMemoryResponse)
async def batch_approve_memories(
    request: BatchMemoryRequest,
    manager: MemoryManager = Depends(get_memory_manager),
) -> BatchMemoryResponse:
    """Batch approve multiple pending memories and persist to storage."""
    if not manager.approval_required:
        raise HTTPException(status_code=400, detail="Approval is not enabled")
    success, failed = await batch_approve_pending(manager, request.memory_ids, source=PendingReviewSource.WEB_API)
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
    count = await batch_reject_pending(manager, request.memory_ids, source=PendingReviewSource.WEB_API)
    return BatchMemoryResponse(
        success_count=count,
        failed_count=len(request.memory_ids) - count,
        failed_ids=[],
    )


@router.post("/pending/{memory_id}/approve")
async def approve_pending_memory(
    memory_id: str,
    request: ApproveMemoryRequest,
    manager: MemoryManager = Depends(get_memory_manager),
) -> StandardSuccessResponse:
    """Approve a pending memory and persist to permanent storage."""
    if not manager.approval_required:
        raise HTTPException(status_code=400, detail="Approval is not enabled")
    try:
        await approve_pending(manager, memory_id, source=PendingReviewSource.WEB_API, edited_content=request.edited_content)
    except Exception as e:
        _raise_approval_http_error(e)
    return create_success_response(data={"status": "approved", "memory_id": memory_id})


@router.post("/pending/{memory_id}/reject")
async def reject_pending_memory(
    memory_id: str,
    manager: MemoryManager = Depends(get_memory_manager),
) -> StandardSuccessResponse:
    """Reject a pending memory (will not be stored)."""
    if not manager.approval_required:
        raise HTTPException(status_code=400, detail="Approval is not enabled")
    try:
        await reject_pending(manager, memory_id, source=PendingReviewSource.WEB_API)
    except Exception as e:
        _raise_approval_http_error(e)
    return create_success_response(data={"status": "rejected", "memory_id": memory_id})
