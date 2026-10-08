"""Dual-engine hybrid search API router.

[POS]
FastAPI endpoints for executing hybrid FTS + vector search queries with multi-factor
re-ranking, monitoring circuit breaker states, and manually healing fallback states.

[INPUT]
- fastapi (APIRouter, Depends, status)
- app.schemas.hybrid_search (
    CircuitBreakerStatusDTO,
    HybridSearchQueryDTO,
    HybridSearchResponseDTO,
    ResetCircuitBreakerResponseDTO,
  )
- app.services.memory.hybrid_search (
    DualEngineHybridSearchService,
    get_hybrid_search_service,
  )

[OUTPUT]
- router: APIRouter with /query, /circuit-status, and /circuit-reset endpoints
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.hybrid_search import (
    CircuitBreakerStatusDTO,
    HybridSearchQueryDTO,
    HybridSearchResponseDTO,
    ResetCircuitBreakerResponseDTO,
)
from app.services.memory.hybrid_search import (
    DualEngineHybridSearchService,
    get_hybrid_search_service,
)

router = APIRouter(prefix="/hybrid-search", tags=["Memory Dual-Engine Hybrid Search"])


@router.post(
    "/query",
    response_model=HybridSearchResponseDTO,
    summary="Execute dual-engine hybrid search with multi-factor re-ranking and graceful fallback",
    status_code=status.HTTP_200_OK,
)
async def execute_hybrid_search(
    payload: HybridSearchQueryDTO,
    service: DualEngineHybridSearchService = Depends(get_hybrid_search_service),
) -> HybridSearchResponseDTO:
    """Execute concurrent FTS and vector search, apply MMR diversity, and return ranked results."""
    return await service.search(payload)


@router.get(
    "/circuit-status",
    response_model=CircuitBreakerStatusDTO,
    summary="Get current vector engine circuit breaker telemetry",
    status_code=status.HTTP_200_OK,
)
async def get_circuit_breaker_status(
    service: DualEngineHybridSearchService = Depends(get_hybrid_search_service),
) -> CircuitBreakerStatusDTO:
    """Check whether the vector provider circuit breaker is CLOSED, OPEN, or HALF_OPEN."""
    return service.get_circuit_status()


@router.post(
    "/circuit-reset",
    response_model=ResetCircuitBreakerResponseDTO,
    summary="Manually reset circuit breaker to closed state",
    status_code=status.HTTP_200_OK,
)
async def reset_circuit_breaker(
    service: DualEngineHybridSearchService = Depends(get_hybrid_search_service),
) -> ResetCircuitBreakerResponseDTO:
    """Force circuit breaker back to CLOSED state to resume vector queries immediately."""
    return service.reset_circuit_breaker()
