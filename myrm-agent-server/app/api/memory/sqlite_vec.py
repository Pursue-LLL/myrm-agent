"""Embedded SQLite vector store API endpoints.

[POS]
FastAPI endpoints for observing embedded single-file SQLite vector store
metrics, dual-track execution status, and performing temporal decay retrieval.

[INPUT]
- fastapi (APIRouter, Depends, HTTPException)
- app.schemas.sqlite_vec (SqliteVecStatsResponse, SqliteVecSearchRequest, SqliteVecSearchResponse)
- app.services.memory.sqlite_vec (SqliteVecProvider, get_sqlite_vec_provider)

[OUTPUT]
- router: APIRouter with /stats, /search, and /health endpoints
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.sqlite_vec import (
    SqliteVecSearchRequest,
    SqliteVecSearchResponse,
    SqliteVecStatsResponse,
)
from app.services.memory.sqlite_vec import (
    SqliteVecProvider,
    get_sqlite_vec_provider,
)

router = APIRouter(prefix="/sqlite-vec", tags=["Memory SQLite Vector"])


@router.get(
    "/stats",
    response_model=SqliteVecStatsResponse,
    summary="Get embedded SQLite vector store metrics",
)
async def get_sqlite_vec_stats(
    provider: SqliteVecProvider = Depends(get_sqlite_vec_provider),
) -> SqliteVecStatsResponse:
    """Retrieve database metrics, file size, collection count, and execution mode."""
    return await provider.get_stats()


@router.post(
    "/search",
    response_model=SqliteVecSearchResponse,
    summary="Search vectors with optional temporal decay",
)
async def search_vectors(
    payload: SqliteVecSearchRequest,
    provider: SqliteVecProvider = Depends(get_sqlite_vec_provider),
) -> SqliteVecSearchResponse:
    """Perform dense vector retrieval with exponential time decay attenuation."""
    return await provider.search(
        collection=payload.collection,
        query_vector=payload.query_vector,
        limit=payload.limit,
        apply_decay=payload.apply_decay,
        half_life_seconds=payload.half_life_seconds,
        score_threshold=payload.score_threshold,
    )


@router.get(
    "/health",
    summary="Check SQLite vector store engine health",
    status_code=status.HTTP_200_OK,
)
async def check_engine_health(
    provider: SqliteVecProvider = Depends(get_sqlite_vec_provider),
) -> dict[str, str | bool]:
    """Verify underlying database file integrity and connection availability."""
    healthy = await provider.health_check()
    return {"healthy": healthy, "engine": "sqlite-vec"}
