"""API router for zero-hallucination memory diagnostics and guarded search.

[POS]
app/api/memory/zero_hallucination.py
Exposes diagnostic endpoints for evaluating memory retrieval states and verifying
anti-hallucination guard instructions.

[INPUT]
- fastapi: APIRouter, Depends
- app.schemas.zero_hallucination: ZeroHallucinationQueryRequest, ZeroHallucinationQueryResponse, ZeroHallucinationHealthResponse
- app.services.memory.zero_hallucination: ZeroHallucinationMemoryService, get_zero_hallucination_service

[OUTPUT]
- router: FastAPI APIRouter mounted under /memory/diagnostics
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.zero_hallucination import (
    ZeroHallucinationHealthResponse,
    ZeroHallucinationQueryRequest,
    ZeroHallucinationQueryResponse,
)
from app.services.memory.zero_hallucination import (
    ZeroHallucinationMemoryService,
    get_zero_hallucination_service,
)

router = APIRouter(prefix="/diagnostics", tags=["memory-diagnostics"])


@router.post(
    "/query",
    response_model=ZeroHallucinationQueryResponse,
    summary="Query memory with strict zero-hallucination boundary evaluation",
)
def query_with_zero_hallucination(
    request: ZeroHallucinationQueryRequest,
    service: ZeroHallucinationMemoryService = Depends(get_zero_hallucination_service),
) -> ZeroHallucinationQueryResponse:
    """Evaluate memory retrieval against explicit state assertions and prompt bounds."""
    return service.execute_query(request)


@router.get(
    "/health",
    response_model=ZeroHallucinationHealthResponse,
    summary="Retrieve health and degradation status of memory subsystems",
)
def get_memory_subsystems_health(
    service: ZeroHallucinationMemoryService = Depends(get_zero_hallucination_service),
) -> ZeroHallucinationHealthResponse:
    """Report online status, observed latencies, and degradation flags across memory engines."""
    return service.check_health()
