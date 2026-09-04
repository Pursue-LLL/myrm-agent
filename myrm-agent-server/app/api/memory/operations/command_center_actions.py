"""Memory Command Center Action Handlers.

[INPUT]
app.database.models.memory::{PendingMemory}
app.schemas.memory.command_center::{MemoryCommandActionRequest}
myrm_agent_harness.toolkits.memory::{MemoryManager, MemoryOperationKind, MemoryType, MemoryStatus}
app.services.memory.shared_context.shared_context::SharedContextService
app.services.memory.shared_context.shared_context_materializer::SharedContextProposalMaterializer

[OUTPUT]
Functions: `run_pending_action`, `run_shared_proposal_action`, `run_memory_action`, `action_to_operation`.

[POS]
记忆指挥中心动作执行实现层。处理 GUI 治理动作（审批、拒绝、编辑、修正、Pin/Unpin、遗忘）。
"""

from __future__ import annotations

from fastapi import HTTPException, status
from myrm_agent_harness.toolkits.memory import (
    MemoryManager,
    MemoryOperationKind,
    MemoryType,
)
from myrm_agent_harness.toolkits.memory.types import MemoryStatus
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models.memory import PendingMemory
from app.schemas.memory.command_center import MemoryCommandActionRequest
from app.services.memory.shared_context.shared_context import SharedContextService
from app.services.memory.shared_context.shared_context_materializer import (
    SharedContextProposalMaterializer,
)


async def run_pending_action(body: MemoryCommandActionRequest, db: AsyncSession, manager: MemoryManager) -> None:
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
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Edited memory content is required",
            )
        pending.content = body.content.strip()
        await db.commit()
        return
    raise HTTPException(
        status_code=status.HTTP_400_BAD_REQUEST,
        detail="Unsupported pending memory action",
    )


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
    from app.services.memory.conflict_service import MemoryConflictService

    service = MemoryConflictService(db, manager)
    conflict_id = body.target_id.replace("conflict:", "")
    if body.action not in ("keep_new", "keep_old", "coexist"):
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported conflict resolution action")
    success = await service.resolve_conflict(conflict_id, action=body.action)
    if not success:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Pending conflict not found or already resolved")


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
            if hasattr(manager, "_cascade_clean_derived_graph_nodes"):
                await manager._cascade_clean_derived_graph_nodes(body.target_id)
        return
    if body.action == "restore_defaults":
        return
    raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Unsupported memory action")


async def run_restore_disciplined_defaults(
    body: MemoryCommandActionRequest,
    db: AsyncSession,
    manager: MemoryManager,
) -> str:
    """Safely archive unpinned working memories and restore disciplined defaults."""
    archived_count = 0
    preserved_pinned_count = 0

    # Clean working and candidate memories
    for mtype in (MemoryType.TASK_DIGEST, MemoryType.CONVERSATION, MemoryType.SEMANTIC):
        try:
            items = await manager.list_memories(mtype, limit=100)
            for item in items:
                if getattr(item, "is_pinned", False):
                    preserved_pinned_count += 1
                    continue
                item_id = str(getattr(item, "id", "") or "")
                if item_id:
                    await manager.update_memory(item_id, status=MemoryStatus.ARCHIVED)
                    archived_count += 1
        except Exception:
            pass

    return (
        f"Restored disciplined defaults: archived {archived_count} memories, preserved {preserved_pinned_count} pinned entries."
    )


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
