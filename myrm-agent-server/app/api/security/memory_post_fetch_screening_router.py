"""
[POS] app/api/security/memory_post_fetch_screening_router.py
[INPUT] app/schemas/memory_post_fetch_screening.py, app/services/security/memory_post_fetch_screening_service.py
[OUTPUT] router

FastAPI router for memory retrieval post-fetch injection screening suite.

Exposes REST endpoints to screen memory passages, view quarantine archives,
and configure dual-path degradation thresholds.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Query, status

from app.schemas.memory_post_fetch_screening import (
    MemoryScreeningMetricsResponse,
    MemoryScreeningPolicyUpdateRequest,
    QuarantinedPassageReportSchema,
    ScreenMemoryPassagesRequest,
    ScreenMemoryPassagesResponse,
)
from app.services.security.memory_post_fetch_screening_service import (
    MemoryPostFetchScreeningService,
    get_memory_post_fetch_screening_service,
)

router = APIRouter(
    prefix="/memory-screening",
    tags=["Memory Post-Fetch Screening"],
)


@router.post(
    "/screen-passages",
    response_model=ScreenMemoryPassagesResponse,
    status_code=status.HTTP_200_OK,
    summary="Screen candidate retrieved memory passages",
)
def screen_memory_passages(
    request: ScreenMemoryPassagesRequest,
) -> ScreenMemoryPassagesResponse:
    """Screen candidate passages retrieved from memory store and isolate toxic entries."""
    service: MemoryPostFetchScreeningService = get_memory_post_fetch_screening_service()
    return service.screen_passages(request)


@router.get(
    "/quarantine-records",
    response_model=list[QuarantinedPassageReportSchema],
    status_code=status.HTTP_200_OK,
    summary="Get quarantined memory passages audit records",
)
def get_quarantined_records(
    limit: int = Query(default=50, ge=1, le=500, description="Max number of records to retrieve."),
) -> list[QuarantinedPassageReportSchema]:
    """Retrieve historical quarantine reports of blocked memory passages."""
    service: MemoryPostFetchScreeningService = get_memory_post_fetch_screening_service()
    return service.get_quarantine_records(limit=limit)


@router.get(
    "/metrics",
    response_model=MemoryScreeningMetricsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get memory screening operational metrics",
)
def get_memory_screening_metrics() -> MemoryScreeningMetricsResponse:
    """Retrieve operational telemetry and dual-path execution statistics."""
    service: MemoryPostFetchScreeningService = get_memory_post_fetch_screening_service()
    return service.get_metrics()


@router.post(
    "/policy",
    status_code=status.HTTP_200_OK,
    summary="Update memory screening policy",
)
def update_memory_screening_policy(
    request: MemoryScreeningPolicyUpdateRequest,
) -> dict[str, str]:
    """Dynamically reconfigure memory screening thresholds and scanner flags."""
    service: MemoryPostFetchScreeningService = get_memory_post_fetch_screening_service()
    service.update_policy(request)
    return {
        "status": "policy_updated",
        "detail": "Memory post-fetch screening policy reconfigured successfully",
    }
