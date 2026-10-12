"""REST endpoints for SQLite FTS5 CRUD, synonym registration, dual-drive search, and circuit breaker telemetry.

[POS]
app/api/memory/hybrid_memory_router.py

[INPUT]
- FastAPI APIRouter, Depends, HTTPException, and hybrid memory DTOs

[OUTPUT]
- REST endpoints for SQLite FTS5 CRUD, synonym registration, dual-drive search, and circuit breaker telemetry
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from myrm_agent_harness.toolkits.memory import (
    AdaptiveRrfConfig,
    HybridMemoryItem,
)

from app.schemas.hybrid_memory import (
    CircuitBreakerStatsDTO,
    HybridEngineStatsDTO,
    HybridMemoryItemDTO,
    HybridSearchRequestDTO,
    HybridSearchResponseDTO,
    HybridSearchResultDTO,
    InsertHybridItemRequestDTO,
    InsertHybridItemResponseDTO,
    RegisterSynonymsRequestDTO,
    RegisterSynonymsResponseDTO,
    ResetCircuitBreakerResponseDTO,
    TripCircuitBreakerRequestDTO,
    TripCircuitBreakerResponseDTO,
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
        importance=payload.item.importance,
        timestamp=payload.item.timestamp,
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
        importance=item.importance,
        timestamp=item.timestamp,
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
    """Execute dual-drive hybrid search with adaptive RRF and circuit-breaker degradation."""
    override_rrf: AdaptiveRrfConfig | None = None
    if payload.adaptive_rrf:
        override_rrf = AdaptiveRrfConfig(
            rrf_k=payload.adaptive_rrf.rrf_k,
            fts_weight=payload.adaptive_rrf.fts_weight,
            vector_weight=payload.adaptive_rrf.vector_weight,
            importance_weight=payload.adaptive_rrf.importance_weight,
            half_life_seconds=payload.adaptive_rrf.half_life_seconds,
            apply_recency_decay=payload.adaptive_rrf.apply_recency_decay,
        )

    hits, mode = service.search(
        query=payload.query,
        limit=payload.limit,
        enable_vector=payload.enable_vector,
        override_rrf_config=override_rrf,
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
            importance=h.importance,
            recency_factor=h.recency_factor,
            is_degraded=h.is_degraded,
            degradation_reason=h.degradation_reason,
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
    """Get operational telemetry of the hybrid engine and embedding circuit breaker."""
    stats = service.get_stats()
    cb = stats.circuit_breaker
    return HybridEngineStatsDTO(
        total_items=stats.total_items,
        synonym_terms_count=stats.synonym_terms_count,
        dense_vector_available=stats.dense_vector_available,
        active_mode=stats.active_mode.value,
        db_path=stats.db_path,
        circuit_breaker=CircuitBreakerStatsDTO(
            state=cb.state.value,
            failure_count=cb.failure_count,
            consecutive_successes=cb.consecutive_successes,
            last_failure_time=cb.last_failure_time,
            tripped_count=cb.tripped_count,
        ),
        last_updated=stats.last_updated,
    )


@router.post("/circuit-breaker/trip", response_model=TripCircuitBreakerResponseDTO)
def trip_circuit_breaker(
    payload: TripCircuitBreakerRequestDTO,
    service: HybridMemoryService = Depends(get_hybrid_memory_service),
) -> TripCircuitBreakerResponseDTO:
    """Manually trip the embedding circuit breaker for disaster simulation."""
    state_str, tripped_count = service.trip_circuit_breaker(reason=payload.reason)
    return TripCircuitBreakerResponseDTO(
        is_success=True,
        state=state_str,
        tripped_count=tripped_count,
    )


@router.post("/circuit-breaker/reset", response_model=ResetCircuitBreakerResponseDTO)
def reset_circuit_breaker(
    service: HybridMemoryService = Depends(get_hybrid_memory_service),
) -> ResetCircuitBreakerResponseDTO:
    """Reset the embedding circuit breaker back to normal closed state."""
    state_str = service.reset_circuit_breaker()
    return ResetCircuitBreakerResponseDTO(
        is_success=True,
        state=state_str,
    )


@router.get("/circuit-breaker/stats", response_model=CircuitBreakerStatsDTO)
def get_circuit_breaker_stats(
    service: HybridMemoryService = Depends(get_hybrid_memory_service),
) -> CircuitBreakerStatsDTO:
    """Get focused embedding circuit breaker metrics."""
    cb = service.get_stats().circuit_breaker
    return CircuitBreakerStatsDTO(
        state=cb.state.value,
        failure_count=cb.failure_count,
        consecutive_successes=cb.consecutive_successes,
        last_failure_time=cb.last_failure_time,
        tripped_count=cb.tripped_count,
    )
