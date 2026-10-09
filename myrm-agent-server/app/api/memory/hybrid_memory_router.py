# [POS]: app/api/memory/hybrid_memory_router.py
# [INPUT]: FastAPI APIRouter, Depends, HTTPException, and hybrid memory DTOs
# [OUTPUT]: REST endpoints for zero-config SQLite FTS5 CRUD, synonym registration, and dual-drive search

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import HybridMemoryItem

from app.schemas.hybrid_memory import (
    HybridEngineStatsDTO,
    HybridMemoryItemDTO,
    HybridSearchRequestDTO,
    HybridSearchResponseDTO,
    HybridSearchResultDTO,
    InsertHybridItemRequestDTO,
    InsertHybridItemResponseDTO,
    RegisterSynonymsRequestDTO,
    RegisterSynonymsResponseDTO,
)
from app.services.memory.hybrid_memory_service import (
    HybridMemoryService,
    get_hybrid_memory_service,
)

router = APIRouter(prefix="/hybrid", tags=["hybrid-memory"])


@router.post("/items", response_model=InsertHybridItemResponseDTO)
def insert_hybrid_item(
    payload: InsertHybridItemRequestDTO,
    service: HybridMemoryService = Depends(get_hybrid_memory_service),
) -> InsertHybridItemResponseDTO:
    """Insert or update a memory item in the local SQLite FTS5 store."""
    item = HybridMemoryItem(
        item_id=payload.item.item_id,
        content=payload.item.content,
        title=payload.item.title,
        tags=payload.item.tags,
        metadata=payload.item.metadata,
        created_at=payload.item.created_at,
    )
    service.insert_item(item)
    return InsertHybridItemResponseDTO(
        item_id=item.item_id,
        is_success=True,
    )


@router.get("/items/{item_id}", response_model=HybridMemoryItemDTO)
def get_hybrid_item(
    item_id: str,
    service: HybridMemoryService = Depends(get_hybrid_memory_service),
) -> HybridMemoryItemDTO:
    """Retrieve a memory item by ID."""
    item = service.get_item(item_id)
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory item '{item_id}' not found",
        )
    return HybridMemoryItemDTO(
        item_id=item.item_id,
        content=item.content,
        title=item.title,
        tags=item.tags,
        metadata=item.metadata,
        created_at=item.created_at,
    )


@router.delete("/items/{item_id}", status_code=status.HTTP_200_OK)
def delete_hybrid_item(
    item_id: str,
    service: HybridMemoryService = Depends(get_hybrid_memory_service),
) -> dict[str, str | bool]:
    """Remove a memory item by ID."""
    deleted = service.delete_item(item_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Memory item '{item_id}' not found",
        )
    return {"item_id": item_id, "deleted": True}


@router.post("/items/search", response_model=HybridSearchResponseDTO)
def search_hybrid_memory(
    payload: HybridSearchRequestDTO,
    service: HybridMemoryService = Depends(get_hybrid_memory_service),
) -> HybridSearchResponseDTO:
    """Execute dual-drive hybrid search with synonym expansion and graceful degradation."""
    hits, mode = service.search(
        query=payload.query,
        limit=payload.limit,
        enable_vector=payload.enable_vector,
    )
    result_dtos = [
        HybridSearchResultDTO(
            item_id=h.item_id,
            title=h.title,
            content=h.content,
            score=h.score,
            source_channel=h.source_channel,
            rank=h.rank,
            matched_terms=h.matched_terms,
        )
        for h in hits
    ]
    return HybridSearchResponseDTO(
        query=payload.query,
        mode=mode.value,
        total_hits=len(result_dtos),
        results=result_dtos,
    )


@router.post("/synonyms", response_model=RegisterSynonymsResponseDTO)
def register_synonyms(
    payload: RegisterSynonymsRequestDTO,
    service: HybridMemoryService = Depends(get_hybrid_memory_service),
) -> RegisterSynonymsResponseDTO:
    """Register or extend an offline synonym cluster."""
    count = service.register_synonyms(payload.primary_term, payload.synonyms)
    return RegisterSynonymsResponseDTO(
        primary_term=payload.primary_term,
        total_synonyms=count,
        is_success=True,
    )


@router.get("/stats", response_model=HybridEngineStatsDTO)
def get_hybrid_engine_stats(
    service: HybridMemoryService = Depends(get_hybrid_memory_service),
) -> HybridEngineStatsDTO:
    """Get operational telemetry of the hybrid engine."""
    stats = service.get_stats()
    return HybridEngineStatsDTO(
        total_items=stats.total_items,
        synonym_terms_count=stats.synonym_terms_count,
        dense_vector_available=stats.dense_vector_available,
        active_mode=stats.active_mode.value,
        db_path=stats.db_path,
        last_updated=stats.last_updated,
    )
