"""Mem0-compatible API endpoint implementations.

[INPUT]
app.api.mem0_compat.types (POS: Mem0-wire request/response schemas)
app.api.mem0_compat.converter (POS: format conversion utilities)
app.services.memory.manager_deps::get_crud_memory_manager (POS: MemoryManager DI)

[OUTPUT]
FastAPI route handlers implementing the Mem0 SDK wire protocol.

[POS]
Thin adapter layer — converts between Mem0's request/response format and
our internal memory service. Zero business logic: only format translation
and delegation to existing handlers.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Query
from myrm_agent_harness.toolkits.memory import MemoryManager, MemoryType

from app.api.mem0_compat.converter import (
    extract_content_from_messages,
    memory_item_to_mem0,
    memory_item_to_mem0_search,
)
from app.api.mem0_compat.types import (
    Mem0AddRequest,
    Mem0AddResponse,
    Mem0DeleteResponse,
    Mem0GetAllRequest,
    Mem0GetAllResponse,
    Mem0HistoryItem,
    Mem0MemoryItem,
    Mem0PingResponse,
    Mem0SearchRequest,
    Mem0SearchResponse,
    Mem0UpdateRequest,
    datetime_to_mem0_str,
)
from app.schemas.memory.crud import MemoryItem
from app.services.memory.command_center import ALL_MEMORY_TYPES
from app.services.memory.manager_deps import get_crud_memory_manager
from app.services.memory.presentation import memory_to_item

logger = logging.getLogger(__name__)

router = APIRouter()


@router.get("/v1/ping/")
async def ping() -> Mem0PingResponse:
    """Health check endpoint — Mem0 SDK calls this on initialization."""
    return Mem0PingResponse(status="ok")


@router.post("/v3/memories/add/")
async def add_memory(
    body: Mem0AddRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> Mem0AddResponse:
    """Add a memory from chat messages (Mem0 format)."""
    content = extract_content_from_messages(body.messages)
    if not content.strip():
        raise HTTPException(status_code=400, detail="No content extracted from messages")

    from app.schemas.memory.crud import CreateMemoryRequest

    create_req = CreateMemoryRequest(
        memory_type="semantic",
        content=content,
        importance=0.5,
    )

    from app.services.memory.operations.crud.list_write import create_memory

    item = await create_memory(body=create_req, manager=manager)
    return Mem0AddResponse(results=[memory_item_to_mem0(item)])


@router.get("/v1/memories/{memory_id}/")
async def get_memory(
    memory_id: str,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> Mem0MemoryItem:
    """Retrieve a specific memory by ID."""
    item = await _find_memory_by_id(manager, memory_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found")
    return memory_item_to_mem0(item)


@router.post("/v3/memories/")
async def get_all_memories(
    body: Mem0GetAllRequest,
    page: int = Query(1, ge=1),
    page_size: int = Query(100, ge=1, le=1000),
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> Mem0GetAllResponse:
    """Retrieve all memories with optional pagination."""
    all_items: list[MemoryItem] = []
    for mem_type in ALL_MEMORY_TYPES:
        try:
            memories = await manager.list_memories(mem_type, limit=10000, offset=0)
            all_items.extend([memory_to_item(m, mem_type) for m in memories])
        except Exception as e:
            logger.warning("Error listing %s memories for mem0-compat: %s", mem_type, e)

    total = len(all_items)
    all_items.sort(key=lambda m: m.created_at, reverse=True)

    start = (page - 1) * page_size
    end = start + page_size
    paginated = all_items[start:end]

    results = [memory_item_to_mem0(item) for item in paginated]
    has_next = end < total
    has_prev = page > 1

    return Mem0GetAllResponse(
        count=total,
        next=f"?page={page + 1}&page_size={page_size}" if has_next else None,
        previous=f"?page={page - 1}&page_size={page_size}" if has_prev else None,
        results=results,
    )


@router.post("/v3/memories/search/")
async def search_memories(
    body: Mem0SearchRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> Mem0SearchResponse:
    """Semantic search across memories."""
    results = await manager.search(body.query, limit=body.top_k)
    items = [
        memory_item_to_mem0_search(memory_to_item(r.memory, r.memory_type), r.score)
        for r in results
    ]
    return Mem0SearchResponse(results=items)


@router.put("/v1/memories/{memory_id}/")
async def update_memory(
    memory_id: str,
    body: Mem0UpdateRequest,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> Mem0MemoryItem:
    """Update a memory's content."""
    if not body.text and not body.metadata:
        raise HTTPException(status_code=400, detail="At least one of text or metadata must be provided")

    item = await _find_memory_by_id(manager, memory_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    if body.text:
        try:
            await manager.update_memory(memory_id, content=body.text)
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to update memory: {e}") from e

    updated_item = await _find_memory_by_id(manager, memory_id)
    if updated_item is None:
        raise HTTPException(status_code=404, detail="Memory not found after update")
    return memory_item_to_mem0(updated_item)


@router.delete("/v1/memories/{memory_id}/")
async def delete_memory(
    memory_id: str,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> Mem0DeleteResponse:
    """Delete a specific memory by ID."""
    from myrm_agent_harness.toolkits.memory.types import MemoryStatus

    item = await _find_memory_by_id(manager, memory_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    mem_type = _parse_type_from_item(item)
    if mem_type in (MemoryType.SEMANTIC, MemoryType.EPISODIC):
        await manager.update_memory(memory_id, status=MemoryStatus.ARCHIVED)
    elif mem_type == MemoryType.PROFILE:
        await manager.delete_profile(memory_id)
    elif mem_type == MemoryType.PROCEDURAL:
        await manager.delete_rule(memory_id)

    return Mem0DeleteResponse(message="Memory deleted successfully!")


@router.delete("/v1/memories/")
async def delete_all_memories(
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> Mem0DeleteResponse:
    """Delete all memories."""
    for mem_type in ALL_MEMORY_TYPES:
        try:
            await manager.delete_all(mem_type)
        except Exception as e:
            logger.warning("Error deleting %s memories for mem0-compat: %s", mem_type, e)

    return Mem0DeleteResponse(message="Memories deleted successfully!")


@router.get("/v1/memories/{memory_id}/history/")
async def memory_history(
    memory_id: str,
    manager: MemoryManager = Depends(get_crud_memory_manager),
) -> list[Mem0HistoryItem]:
    """Retrieve memory history (simplified — our system tracks via operation events)."""
    item = await _find_memory_by_id(manager, memory_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Memory not found")

    return [
        Mem0HistoryItem(
            id=f"{memory_id}_created",
            memory_id=memory_id,
            old_memory=None,
            new_memory=item.content,
            event="ADD",
            timestamp=datetime_to_mem0_str(item.created_at),
        )
    ]


async def _find_memory_by_id(
    manager: MemoryManager, memory_id: str,
) -> MemoryItem | None:
    """Search across all memory types to find a memory by ID."""
    for mem_type in ALL_MEMORY_TYPES:
        try:
            memories = await manager.list_memories(mem_type, limit=10000, offset=0)
            for m in memories:
                item_id = getattr(m, "id", "")
                if item_id == memory_id:
                    return memory_to_item(m, mem_type)
        except Exception:
            continue
    return None


def _parse_type_from_item(item: MemoryItem) -> MemoryType:
    """Parse MemoryType from a MemoryItem's memory_type string."""
    from app.services.memory.presentation import parse_memory_type

    return parse_memory_type(item.memory_type)
