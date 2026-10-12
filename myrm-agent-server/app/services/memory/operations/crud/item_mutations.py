"""Memory CRUD — single-item mutations.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
app.schemas.memory.crud::MemoryItem / UpdateMemoryRequest (POS: 记忆 API 通用 Schema 层)
app.services.memory.operations.crud._common::_record_memory_event (POS: 记忆操作事件记录)

[OUTPUT]
- update_memory_item: 单条记忆就地更新（含用户保护语义：显式请求时程序性规则锁定、语义/情景记忆固定；编辑程序性规则内容默认锁定）
- delete_memory_item: 单条记忆删除（语义/情景软删除，其余硬删除；permanent 强制清除）

[POS]
记忆单条变更的唯一实现。记忆中心路由与学习时间线路由共用，保证锁定语义、软删除与异常语义一致。
"""

from __future__ import annotations

from fastapi import HTTPException
from myrm_agent_harness.toolkits.memory import (
    MemoryError,
    MemoryManager,
    MemoryNotFoundError,
    MemoryOperationKind,
    MemoryType,
)
from myrm_agent_harness.toolkits.memory.types import MemoryStatus

from app.schemas.memory.crud import MemoryItem, UpdateMemoryRequest
from app.services.memory.operations.crud._common import _record_memory_event
from app.services.memory.operations.presentation import memory_to_item

_SOFT_DELETE_TYPES = (MemoryType.SEMANTIC, MemoryType.EPISODIC)


async def update_memory_item(
    manager: MemoryManager,
    mem_type: MemoryType,
    memory_id: str,
    body: UpdateMemoryRequest,
) -> MemoryItem:
    """Update one memory in place.

    An explicit ``is_user_locked`` from the client expresses the user's own protection
    intent and wins. Otherwise editing a procedural rule's content implies the user
    endorses it, so it stays protected by default; semantic/episodic memories are only
    protected on explicit request. Rules persist protection as ``is_user_locked``;
    semantic/episodic memories persist it as ``pinned``, applied after the edit succeeds
    so a rejected edit never leaves an unedited memory pinned.
    """
    if mem_type == MemoryType.PROFILE:
        raise HTTPException(
            status_code=400,
            detail="Profile attributes cannot be updated via this endpoint. Use POST to set new values.",
        )

    is_procedural = mem_type == MemoryType.PROCEDURAL
    if body.is_user_locked is not None:
        resolved_lock: bool | None = body.is_user_locked
    else:
        resolved_lock = True if is_procedural and body.content is not None else None

    try:
        updated = await manager.update_memory(
            memory_id,
            content=body.content,
            importance=body.importance,
            reasoning=body.reasoning,
            application=body.application,
            tags=body.tags,
            is_user_locked=resolved_lock if is_procedural else None,
            is_exact_fact=body.is_exact_fact,
        )
        if resolved_lock and not is_procedural:
            updated = await manager.pin_memory(memory_id)
    except MemoryNotFoundError as exc:
        raise HTTPException(status_code=404, detail="Memory not found") from exc
    except MemoryError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    await _record_memory_event(
        kind=MemoryOperationKind.WRITE,
        summary="Memory updated manually.",
        memory_id=memory_id,
        memory_type=mem_type.value,
    )
    return memory_to_item(updated, mem_type)


async def delete_memory_item(
    manager: MemoryManager,
    mem_type: MemoryType,
    memory_id: str,
    *,
    permanent: bool = False,
) -> dict[str, bool | str]:
    """Delete one memory.

    Semantic/episodic memories are archived with a retention TTL unless ``permanent``
    is set (then the vector index, embedding cache and claim graph are purged too).
    Profile/procedural memories are always removed permanently.
    """
    soft_capable = mem_type in _SOFT_DELETE_TYPES
    if soft_capable and not permanent:
        try:
            await manager.update_memory(memory_id, status=MemoryStatus.ARCHIVED)
        except MemoryNotFoundError as exc:
            raise HTTPException(status_code=404, detail="Memory not found") from exc
        except MemoryError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        await _record_memory_event(
            kind=MemoryOperationKind.FORGET,
            summary="Memory soft-deleted (archived with 7-day TTL).",
            memory_id=memory_id,
            memory_type=mem_type.value,
            metadata={"soft_delete": True},
        )
        return {"deleted": True, "memory_id": memory_id, "soft_delete": True}

    if soft_capable:
        collection = manager.config.semantic_collection if mem_type == MemoryType.SEMANTIC else manager.config.episodic_collection
        success = await manager.delete_memory(collection, [memory_id]) > 0
    elif mem_type == MemoryType.PROFILE:
        success = await manager.delete_profile(memory_id)
    elif mem_type == MemoryType.PROCEDURAL:
        success = await manager.delete_rule(memory_id)
    else:
        raise HTTPException(status_code=400, detail=f"Unsupported memory type: {mem_type.value}")

    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or could not be deleted")

    await _record_memory_event(
        kind=MemoryOperationKind.FORGET,
        summary="Memory permanently deleted (purged)." if soft_capable else "Memory deleted permanently.",
        memory_id=memory_id,
        memory_type=mem_type.value,
        metadata={"permanent": True} if soft_capable else None,
    )
    payload: dict[str, bool | str] = {"deleted": True, "memory_id": memory_id}
    if soft_capable:
        payload["permanent"] = True
    return payload
