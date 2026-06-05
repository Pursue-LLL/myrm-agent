"""Memory CRUD — trash.

[INPUT]
myrm_agent_harness.toolkits.memory::MemoryManager (POS: Unified memory manager and core facade of the Memory Toolkit)
app.schemas.memory.crud::MemoryItem (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.crud::UpdateMemoryStatusRequest (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.crud::TasteSummaryResponse (POS: 记忆 API 通用 Schema 层)
app.schemas.memory.archive::*Import* / *Archive* (POS: 记忆归档与导入 API Schema 层)

[OUTPUT]
memory CRUD handler functions、状态变更、偏好摘要、偏好管理、服务端绑定导入、Memory Archive、导入后诊断和回滚预演端点

[POS]
记忆 API 操作层。提供标准记忆增删改查、偏好稳定性管理、单用户 archive 导出/校验，
以及 dry-run -> confirm -> diagnostic -> rollback preview -> rollback 的可审计导入流程。
"""

from __future__ import annotations

import logging

from fastapi import Depends, HTTPException, Query
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryOperationKind, MemoryType

from app.database.standard_responses import create_success_response
from app.schemas.memory.crud import (
    MemoryItem,
    MemoryListPaginatedResponse,
    PaginationInfo,
)
from app.services.memory.manager_deps import get_crud_memory_manager
from app.services.memory.operations.crud._common import _record_memory_event
from app.services.memory.presentation import memory_to_item, parse_memory_type

logger = logging.getLogger(__name__)


async def list_trash_memories(
    type: str | None = Query(None, description="Filter by memory type"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page"),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryListPaginatedResponse:
    """List archived (soft-deleted) memories in the trash bin."""
    from myrm_agent_harness.toolkits.memory.types import MemoryStatus

    vector_types = [MemoryType.SEMANTIC, MemoryType.EPISODIC]
    types = [parse_memory_type(type)] if type else vector_types

    all_archived: list[MemoryItem] = []
    for mem_type in types:
        if mem_type not in vector_types:
            continue
        try:
            memories = await manager.list_memories(mem_type, limit=10000, include_archived=True)
            for m in memories:
                if getattr(m, "status", None) == MemoryStatus.ARCHIVED:
                    item = memory_to_item(m, mem_type)
                    item.metadata = {
                        **(item.metadata or {}),
                        **{
                            k: getattr(m, "metadata", {}).get(k, "")
                            for k in ("archived_at", "archive_expires_at", "archive_reason")
                            if getattr(m, "metadata", {}).get(k)
                        },
                    }
                    all_archived.append(item)
        except Exception as e:
            logger.warning("Error listing archived %s memories: %s", mem_type, e)

    all_archived.sort(key=lambda m: m.metadata.get("archived_at", "") if m.metadata else "", reverse=True)
    total = len(all_archived)
    offset = (page - 1) * page_size
    paginated = all_archived[offset : offset + page_size]
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


async def restore_trashed_memory(
    memory_id: str,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> MemoryItem:
    """Restore a soft-deleted memory from the trash bin back to active status."""
    from myrm_agent_harness.toolkits.memory.types import MemoryStatus

    try:
        restored = await manager.update_memory(memory_id, status=MemoryStatus.ACTIVE)
    except Exception as e:
        raise HTTPException(status_code=404, detail=str(e)) from e

    await _record_memory_event(
        kind=MemoryOperationKind.WRITE,
        summary="Memory restored from trash.",
        memory_id=memory_id,
        memory_type=getattr(restored, "memory_type", "semantic"),
        metadata={"restored": True},
    )
    mt = MemoryType(getattr(restored, "memory_type", "semantic"))
    return memory_to_item(restored, mt)


async def purge_trashed_memory(
    memory_id: str,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> object:
    """Permanently delete a memory from the trash bin (hard delete)."""
    from myrm_agent_harness.toolkits.memory.types import MemoryStatus

    existing = await manager.get_memory(memory_id)
    if existing is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    if getattr(existing, "status", None) != MemoryStatus.ARCHIVED:
        raise HTTPException(status_code=400, detail="Only archived memories can be permanently deleted from trash")

    mem_type_str = getattr(existing, "memory_type", "semantic")
    mem_type = MemoryType(mem_type_str)
    coll = manager.config.semantic_collection if mem_type == MemoryType.SEMANTIC else manager.config.episodic_collection
    deleted = await manager.delete_memory(coll, [memory_id])
    if deleted == 0:
        raise HTTPException(status_code=404, detail="Memory not found or could not be deleted")

    await _record_memory_event(
        kind=MemoryOperationKind.FORGET,
        summary="Memory permanently deleted from trash.",
        memory_id=memory_id,
        memory_type=mem_type_str,
        metadata={"purged": True},
    )
    return create_success_response(data={"purged": True, "memory_id": memory_id})
