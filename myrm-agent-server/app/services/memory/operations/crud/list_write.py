"""Memory CRUD — list write.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
app.schemas.memory.crud::MemoryItem (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.crud::UpdateMemoryStatusRequest (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.crud::TasteSummaryResponse (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.archive::*Import* / *Archive* (POS: 记忆归档与导入 API Schema 层)

[OUTPUT]
memory CRUD handler functions、状态变更、偏好摘要、偏好管理、标签统计、服务端绑定导入、Memory Archive、导入后诊断和回滚预演端点

[POS]
记忆 API 操作层。提供标准记忆增删改查、偏好稳定性管理、单用户 archive 导出/校验，
以及 dry-run -> confirm -> diagnostic -> rollback preview -> rollback 的可审计导入流程。
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Query
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryType
from myrm_agent_harness.toolkits.memory.types import SemanticMemory
from pydantic import BaseModel

from app.database.standard_responses import create_success_response
from app.schemas.memory.crud import (
    CorrectMemoryRequest,
    CreateMemoryRequest,
    MemoryItem,
    MemoryListPaginatedResponse,
    MemorySearchResponse,
    MemoryStatsResponse,
    PaginationInfo,
    RateMemoryRequest,
    RateMemoryResponse,
    UpdateMemoryRequest,
    UpdateMemoryStatusRequest,
)
from app.services.memory.command_center import ALL_MEMORY_TYPES
from app.services.memory.manager_deps import get_crud_memory_manager
from app.services.memory.operations.crud._common import _SORT_KEYS, _record_memory_event
from app.services.memory.presentation import memory_to_item, parse_memory_type

logger = logging.getLogger(__name__)


async def list_memories_paginated(
    type: str | None = Query(None, description="Filter by memory type"),
    search: str | None = Query(None, description="Search query"),
    tag: str | None = Query(None, description="Filter by tag (exact match)"),
    sort_by: str = Query("created_at", description="Sort field: created_at, updated_at, importance"),
    sort_order: str = Query("desc", description="Sort order: asc or desc"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryListPaginatedResponse:
    """List user's memories with pagination and sorting."""
    types = [parse_memory_type(type)] if type else list(ALL_MEMORY_TYPES)

    all_memories: list[MemoryItem] = []
    total = 0

    for mem_type in types:
        try:
            count = await manager.count_memories(mem_type)
            total += count
            memories = await manager.list_memories(mem_type, limit=10000, offset=0)
            all_memories.extend([memory_to_item(m, mem_type) for m in memories])
        except Exception as e:
            logger.warning(f"Error listing {mem_type} memories: {e}")

    if search:
        search_lower = search.lower()
        all_memories = [m for m in all_memories if search_lower in m.content.lower()]
        total = len(all_memories)

    if tag:
        tag_lower = tag.lower()
        all_memories = [m for m in all_memories if any(t.lower() == tag_lower for t in m.tags)]
        total = len(all_memories)

    sort_attr = _SORT_KEYS.get(sort_by, "created_at")
    reverse = sort_order != "asc"
    all_memories.sort(key=lambda m: getattr(m, sort_attr, 0) or 0, reverse=reverse)

    offset = (page - 1) * page_size
    paginated = all_memories[offset : offset + page_size]
    total_pages = max(1, (total + page_size - 1) // page_size)

    return MemoryListPaginatedResponse(
        items=paginated,
        pagination=PaginationInfo(
            page=page,
            page_size=page_size,
            total=total,
            total_pages=total_pages,
            has_next=page < total_pages,
            has_prev=page > 1,
        ),
    )


async def create_memory(
    body: CreateMemoryRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryItem:
    """Create a new memory manually."""
    mem_type = parse_memory_type(body.memory_type)

    if mem_type == MemoryType.PROFILE:
        if not body.key or not body.value:
            raise HTTPException(status_code=400, detail="Profile memory requires 'key' and 'value'")
        if not manager.has_relational:
            raise HTTPException(status_code=400, detail="Profile memory is not enabled")
        await manager.set_profile_attribute(body.key, str(body.value))
        result = SemanticMemory(
            user_id="sandbox",
            content=f"{body.key}: {body.value}",
            importance=0.8,
            metadata={"key": body.key, "value": str(body.value)},
        )
        await _record_memory_event(
            kind=MemoryOperationKind.WRITE,
            summary="Profile memory created manually.",
            memory_id=result.id,
            memory_type=mem_type.value,
        )
        return memory_to_item(result, mem_type)

    elif mem_type == MemoryType.SEMANTIC:
        if not manager.has_vector:
            raise HTTPException(status_code=400, detail="Semantic memory is not enabled")
        memory = await manager.add_knowledge(body.content, importance=body.importance, tags=body.tags)
        await _record_memory_event(
            kind=MemoryOperationKind.WRITE,
            summary="Semantic memory created manually.",
            memory_id=memory.id,
            memory_type=mem_type.value,
        )
        return memory_to_item(memory, mem_type)

    elif mem_type == MemoryType.EPISODIC:
        if not manager.has_vector:
            raise HTTPException(status_code=400, detail="Episodic memory is not enabled")
        memory = await manager.add_event(
            body.content,
            event_type="user_manual",
            related_entities=body.related_entities or None,
        )
        await _record_memory_event(
            kind=MemoryOperationKind.WRITE,
            summary="Episodic memory created manually.",
            memory_id=memory.id,
            memory_type=mem_type.value,
        )
        return memory_to_item(memory, mem_type)

    elif mem_type == MemoryType.PROCEDURAL:
        if not body.trigger or not body.action:
            raise HTTPException(
                status_code=400,
                detail="Procedural memory requires 'trigger' and 'action'",
            )
        if not manager.has_relational:
            raise HTTPException(status_code=400, detail="Procedural memory is not enabled")
        memory = await manager.add_rule(body.trigger, body.action)
        await _record_memory_event(
            kind=MemoryOperationKind.WRITE,
            summary="Procedural memory created manually.",
            memory_id=memory.id,
            memory_type=mem_type.value,
        )
        return memory_to_item(memory, mem_type)

    else:
        raise HTTPException(status_code=400, detail=f"Unsupported memory type: {body.memory_type}")


async def update_memory(
    memory_type: str,
    memory_id: str,
    body: UpdateMemoryRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryItem:
    """Update an existing memory's content, importance, reasoning or application."""
    mem_type = parse_memory_type(memory_type)

    if mem_type == MemoryType.PROFILE:
        raise HTTPException(
            status_code=400,
            detail="Profile attributes cannot be updated via this endpoint. Use POST to set new values.",
        )

    try:
        lock_on_edit = mem_type == MemoryType.PROCEDURAL and body.content is not None
        updated = await manager.update_memory(
            memory_id,
            content=body.content,
            importance=body.importance,
            reasoning=body.reasoning,
            application=body.application,
            tags=body.tags,
            is_user_locked=True if lock_on_edit else None,
        )
        await _record_memory_event(
            kind=MemoryOperationKind.WRITE,
            summary="Memory updated manually.",
            memory_id=memory_id,
            memory_type=mem_type.value,
        )
        return memory_to_item(updated, mem_type)
    except Exception as e:
        raise HTTPException(status_code=404, detail="Memory not found") from e


async def correct_memory(
    memory_id: str,
    body: CorrectMemoryRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryItem:
    """Correct a factually wrong semantic memory: demote the old one and create a linked correction."""
    try:
        correction = await manager.correct_memory(memory_id, body.corrected_content)
        await _record_memory_event(
            kind=MemoryOperationKind.CORRECT,
            summary="Memory corrected manually.",
            memory_id=correction.id,
            memory_type=MemoryType.SEMANTIC.value,
            metadata={"correction_of": memory_id},
        )
        return memory_to_item(correction, MemoryType.SEMANTIC)
    except Exception as e:
        error_msg = str(e)
        if "not found" in error_msg.lower():
            raise HTTPException(status_code=404, detail=error_msg) from e
        if "only supports" in error_msg.lower():
            raise HTTPException(status_code=400, detail=error_msg) from e
        raise HTTPException(status_code=500, detail=f"Correction failed: {error_msg}") from e


async def delete_all_memories(
    memory_type: str | None = Query(None, description="Delete only this type"),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, object]:
    """Delete all user memories, optionally filtered by type."""
    if memory_type:
        mem_type = parse_memory_type(memory_type)
        count = await manager.delete_by_type(mem_type)
        await _record_memory_event(
            kind=MemoryOperationKind.FORGET,
            summary="Memories deleted by type.",
            memory_type=mem_type.value,
            metadata={"deleted_count": count},
        )
        return {"deleted_count": count}

    counts = await manager.delete_all()
    await _record_memory_event(
        kind=MemoryOperationKind.FORGET,
        summary="All memories deleted.",
        metadata={"deleted_count": sum(counts.values())},
    )
    return {"deleted_count": sum(counts.values()), "by_type": counts}


async def delete_memory_by_id(
    memory_id: str,
    memory_type: str = Query(..., description="Memory type"),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> object:
    """Delete a specific memory by ID.

    For Semantic/Episodic memories, performs a soft delete (archive with 7-day TTL).
    For Profile/Procedural memories, performs a hard delete (no vector status concept).
    """
    from myrm_agent_harness.toolkits.memory.types import MemoryStatus

    mem_type = parse_memory_type(memory_type)

    if mem_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
        try:
            await manager.update_memory(memory_id, status=MemoryStatus.ARCHIVED)
        except Exception as e:
            raise HTTPException(status_code=404, detail="Memory not found or could not be archived") from e
        await _record_memory_event(
            kind=MemoryOperationKind.FORGET,
            summary="Memory soft-deleted (archived with 7-day TTL).",
            memory_id=memory_id,
            memory_type=mem_type.value,
            metadata={"soft_delete": True},
        )
        return create_success_response(data={"deleted": True, "memory_id": memory_id, "soft_delete": True})

    success = False
    if mem_type == MemoryType.PROFILE:
        success = await manager.delete_profile(memory_id)
    elif mem_type == MemoryType.PROCEDURAL:
        success = await manager.delete_rule(memory_id)

    if not success:
        raise HTTPException(status_code=404, detail="Memory not found or could not be deleted")

    await _record_memory_event(
        kind=MemoryOperationKind.FORGET,
        summary="Memory deleted permanently.",
        memory_id=memory_id,
        memory_type=mem_type.value,
    )
    return create_success_response(data={"deleted": True, "memory_id": memory_id})


async def search_memories(
    query: str = Query(..., min_length=1, description="Search query"),
    memory_types: str | None = Query(None, description="Comma-separated memory types"),
    limit: int = Query(10, ge=1, le=50, description="Maximum results"),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemorySearchResponse:
    """Semantic search across user's memories using vector similarity."""
    types: list[MemoryType] | None = None
    if memory_types:
        types = [parse_memory_type(t.strip()) for t in memory_types.split(",")]

    results = await manager.search(query, memory_types=types, limit=limit)
    items = [memory_to_item(r.memory, r.memory_type) for r in results]
    scores = [r.score for r in results]
    await _record_memory_event(
        kind=MemoryOperationKind.RECALL,
        summary="Memory search executed.",
        metadata={"result_count": len(items), "limit": limit},
    )

    return MemorySearchResponse(results=items, scores=scores, query=query, total=len(items))


async def get_memory_stats(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryStatsResponse:
    """Get memory statistics for the user."""
    by_type: dict[str, int] = {}
    total = 0

    for mem_type in ALL_MEMORY_TYPES:
        try:
            count = await manager.count_memories(mem_type)
            by_type[mem_type.value] = count
            total += count
        except Exception as e:
            logger.warning(f"Error counting {mem_type} memories: {e}")
            by_type[mem_type.value] = 0

    return MemoryStatsResponse(total_memories=total, by_type=by_type)


async def get_memory_context(
    include_profile: bool = Query(True),
    include_rules: bool = Query(True),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, object]:
    """Get user context for agent prompting."""
    ctx = await manager.get_context(include_profile=include_profile, include_rules=include_rules)
    if isinstance(ctx, dict):
        return {str(k): v for k, v in ctx.items()}
    return {"value": ctx}


async def rate_memory(
    memory_id: str,
    request: RateMemoryRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> RateMemoryResponse:
    """Rate a memory with user feedback (1-5 scale). Updates via EMA."""
    ok = await manager.rate_memory(memory_id, request.score)
    if not ok:
        raise HTTPException(status_code=404, detail=f"Memory {memory_id} not found")
    await _record_memory_event(
        kind=MemoryOperationKind.WRITE,
        summary="Memory feedback rating updated.",
        memory_id=memory_id,
        metadata={"score": request.score},
    )
    return RateMemoryResponse(success=True, memory_id=memory_id, score=request.score)


class UndoConsolidationRequest(BaseModel):
    subsumed_ids: list[str]


async def undo_consolidation(
    body: UndoConsolidationRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> dict[str, str]:
    """Undo a cognitive consolidation by removing the 'subsumed' status."""
    from myrm_agent_harness.toolkits.memory.strategies.subsumption import (
        undo_subsumption,
    )

    restored_count = await undo_subsumption(manager, body.subsumed_ids)
    if restored_count == 0:
        raise HTTPException(
            status_code=400,
            detail="No memories were restored. They might be permanently deleted or already active.",
        )
    return {"message": f"Successfully restored {restored_count} memories."}


async def update_memory_status(
    memory_id: str,
    request: UpdateMemoryStatusRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryItem:
    """Change a memory's lifecycle status (active/disabled/archived)."""
    from myrm_agent_harness.toolkits.memory.types import MemoryStatus

    valid = {s.value for s in MemoryStatus}
    if request.status not in valid:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status '{request.status}'. Must be one of: {valid}",
        )
    new_status = MemoryStatus(request.status)
    try:
        updated = await manager.update_memory(memory_id, status=new_status)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e
    await _record_memory_event(
        kind=MemoryOperationKind.WRITE if new_status != MemoryStatus.ARCHIVED else MemoryOperationKind.FORGET,
        summary="Memory lifecycle status updated.",
        memory_id=memory_id,
        memory_type=getattr(updated, "memory_type", "semantic"),
        metadata={"status": request.status},
    )
    mt = MemoryType(getattr(updated, "memory_type", "semantic"))
    return memory_to_item(updated, mt)


class TagStatsItem(BaseModel):
    tag: str
    count: int


class TagStatsResponse(BaseModel):
    tags: list[TagStatsItem]
    total_tagged: int


async def get_memory_tags(
    limit: int = Query(20, ge=1, le=100, description="Max tags to return"),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> TagStatsResponse:
    """Get tag frequency statistics across all taggable memories."""
    from collections import Counter

    tag_counter: Counter[str] = Counter()
    tagged_count = 0

    for mem_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
        try:
            memories = await manager.list_memories(mem_type, limit=10000, offset=0)
            for mem in memories:
                tags = getattr(mem, "tags", None) or []
                if tags:
                    tagged_count += 1
                    tag_counter.update(tags)
        except Exception as e:
            logger.warning(f"Error reading {mem_type} tags: {e}")

    top_tags = [TagStatsItem(tag=t, count=c) for t, c in tag_counter.most_common(limit)]
    return TagStatsResponse(tags=top_tags, total_tagged=tagged_count)
