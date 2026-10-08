"""Memory Command Center Action Handlers.

[INPUT]
app.services.memory.operations.pending_review::{approve_pending, reject_pending} (POS: 审批队列统一审批与审计入口)
app.schemas.memory.command_center::{MemoryCommandActionRequest}
myrm_agent_harness.toolkits.memory::{MemoryManager, MemoryOperationKind, MemoryType, MemoryStatus}
app.services.memory.shared_context.shared_context::SharedContextService
app.services.memory.shared_context.shared_context_materializer::SharedContextProposalMaterializer

[OUTPUT]
Functions: `run_pending_action`, `run_shared_proposal_action`, `run_memory_action`, `action_to_operation`.

[POS]
记忆指挥中心动作执行实现层。处理 GUI 治理动作（审批、拒绝、编辑、修正、Pin/Unpin、遗忘）。待审批记忆的批准/拒绝走审批队列的统一审批入口。
"""

from __future__ import annotations

from fastapi import HTTPException, status
from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
    MemoryNotFoundError,
    MemoryOperationKind,
    MemoryType,
)
from myrm_agent_harness.toolkits.memory.types import MemoryStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.schemas.memory.command_center import MemoryCommandActionRequest
from app.services.memory.operations.pending_review import (
    PendingReviewSource,
    approve_pending,
    reject_pending,
)
from app.services.memory.shared_context.shared_context import SharedContextService
from app.services.memory.shared_context.shared_context_materializer import (
    SharedContextProposalMaterializer,
)


async def run_pending_action(body: MemoryCommandActionRequest, manager: MemoryManager) -> None:
    """Approve or reject a queued proposal; editing happens in the review dialog via ``edited_content``."""
    if body.action not in ("approve", "reject"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Unsupported pending memory action",
        )
    try:
        if body.action == "approve":
            await approve_pending(manager, body.target_id, source=PendingReviewSource.COMMAND_CENTER)
        else:
            await reject_pending(manager, body.target_id, source=PendingReviewSource.COMMAND_CENTER)
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending memory not found") from exc


async def run_shared_proposal_action(body: MemoryCommandActionRequest, db: AsyncSession) -> None:
    service = SharedContextService(db)
    proposal = await service.get_write_proposal(body.target_id)
    if proposal is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Shared context proposal not found",
        )
    if body.action == "approve":
        await SharedContextProposalMaterializer(db).approve_write_proposal(body.target_id)
        return
    if body.action == "reject":
        await service.set_write_proposal_status(body.target_id, "rejected")
        return
    if body.action == "edit":
        if not body.content or not body.content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Edited proposal content is required",
            )
        await service.update_write_proposal(body.target_id, content=body.content.strip())
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported shared proposal action",
    )


async def run_conflict_action(body: MemoryCommandActionRequest, db: AsyncSession, manager: MemoryManager) -> None:
    """Resolve a `pending_memories.is_conflict` row from the command center.

    Delegates to the same resolver the REST endpoint uses so the command center
    and the conflict API can never drift apart.
    """
    from app.api.memory.operations.conflicts import resolve_conflict
    from app.schemas.memory.crud import ResolveConflictRequest

    conflict_id = body.target_id.replace("conflict:", "")
    if body.action not in ("keep_new", "keep_old", "coexist"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported conflict resolution action")

    action = "coexist" if body.action == "coexist" else body.action
    await resolve_conflict(conflict_id, ResolveConflictRequest(resolution=action), manager)


async def run_memory_action(body: MemoryCommandActionRequest, manager: MemoryManager) -> None:
    if body.action in ("correct", "correct_and_lock"):
        if not body.content or not body.content.strip():
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Corrected memory content is required",
            )
        await manager.correct_memory(body.target_id, body.content.strip())
        if body.action == "correct_and_lock":
            await manager.pin_memory(body.target_id)
        return
    if body.action == "pin":
        await manager.pin_memory(body.target_id)
        return
    if body.action == "unpin":
        await manager.unpin_memory(body.target_id)
        return
    if body.action == "forget":
        mem_type = MemoryType(body.memory_type) if body.memory_type else None
        if mem_type == MemoryType.PROFILE:
            await manager.delete_profile(body.target_id)
        elif mem_type == MemoryType.PROCEDURAL:
            await manager.delete_rule(body.target_id)
        else:
            # Archiving already cascades derived graph cleanup and is restorable.
            await manager.update_memory(body.target_id, status=MemoryStatus.ARCHIVED)
        return
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported memory action")


def action_to_operation(action: str) -> MemoryOperationKind:
    if action == "approve":
        return MemoryOperationKind.APPROVE
    if action == "reject":
        return MemoryOperationKind.REJECT
    if action == "correct":
        return MemoryOperationKind.CORRECT
    if action == "forget":
        return MemoryOperationKind.FORGET
    if action in {"pin", "unpin", "edit", "correct_and_lock"}:
        return MemoryOperationKind.WRITE
    return MemoryOperationKind.OBSERVE
