"""REST endpoints of two-layer context injection and multi-pass dialectic reconciliation.

[INPUT]
- app.schemas.two_layer_dialectic::AssembleInjectionRequest, BaseContextPayloadDTO, DialecticConflictCandidateDTO, DialecticInspectRequest, DialecticReconcileRequest, DialecticReconciliationResultDTO, TwoLayerContextInjectionResultDTO (POS: API contracts of two-layer context injection and dialectic reconciliation, shared by its router and service.)
- app.services.memory.two_layer_dialectic_service::TwoLayerDialecticService, get_two_layer_dialectic_service (POS: Service behind the two-layer dialectic API: hands requests to the harness injector and multi-pass reconciler, keeps one injector (and so one per-session base-context cache and cadence state) for the process, and converts the harness results to DTOs.)

[OUTPUT]
- router: POST /two-layer-dialectic/inspect, /reconcile and /assemble, GET /two-layer-dialectic/cache/{session_id} and POST /two-layer-dialectic/reset/{session_id}

[POS]
HTTP layer of the two-layer dialectic API: inspects statements for conflicts, reconciles them, assembles the two context layers and
reads or resets a session's cached base context and cadence counters.
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException

from app.schemas.two_layer_dialectic import (
    AssembleInjectionRequest,
    BaseContextPayloadDTO,
    DialecticConflictCandidateDTO,
    DialecticInspectRequest,
    DialecticReconcileRequest,
    DialecticReconciliationResultDTO,
    TwoLayerContextInjectionResultDTO,
)
from app.services.memory.two_layer_dialectic_service import (
    TwoLayerDialecticService,
    get_two_layer_dialectic_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/two-layer-dialectic", tags=["Two-Layer Dialectic"])


@router.post(
    "/inspect",
    response_model=list[DialecticConflictCandidateDTO],
    summary="Scan memory statements for mutual exclusivity",
)
async def inspect_conflicts(
    request: DialecticInspectRequest,
    service: Annotated[TwoLayerDialecticService, Depends(get_two_layer_dialectic_service)],
) -> list[DialecticConflictCandidateDTO]:
    """Pass 0 inspection of candidate statements to detect opposing assertions."""
    return service.inspect_conflicts(request.statements, cutoff=request.cutoff)


@router.post(
    "/reconcile",
    response_model=list[DialecticReconciliationResultDTO],
    summary="Execute multi-pass dialectic resolution over statements",
)
async def reconcile_conflicts(
    request: DialecticReconcileRequest,
    service: Annotated[TwoLayerDialecticService, Depends(get_two_layer_dialectic_service)],
) -> list[DialecticReconciliationResultDTO]:
    """Execute dialectic inspection, synthesis, and reconciliation to produce authoritative resolution."""
    return service.reconcile_conflicts(request.statements, depth=request.depth)


@router.post(
    "/assemble",
    response_model=TwoLayerContextInjectionResultDTO,
    summary="Assemble cadence-governed dual-layer injection payload",
)
async def assemble_injection(
    request: AssembleInjectionRequest,
    service: Annotated[TwoLayerDialecticService, Depends(get_two_layer_dialectic_service)],
) -> TwoLayerContextInjectionResultDTO:
    """Compose Layer 1 (cache-safe base context) and Layer 2 (tail dialectic reconciliation) blocks."""
    return service.assemble_injection(request)


@router.get(
    "/cache/{session_id}",
    response_model=BaseContextPayloadDTO,
    summary="Get cached Layer 1 base context payload",
)
async def get_base_cache(
    session_id: str,
    service: Annotated[TwoLayerDialecticService, Depends(get_two_layer_dialectic_service)],
) -> BaseContextPayloadDTO:
    """Retrieve existing cached base context for session, or return 404 if not found."""
    cached = service.get_base_context_cache(session_id)
    if cached is None:
        raise HTTPException(status_code=404, detail=f"No cached base context found for session '{session_id}'")
    return cached


@router.post(
    "/reset/{session_id}",
    response_model=dict[str, bool],
    summary="Reset cadence and base context cache for session",
)
async def reset_session_cadence(
    session_id: str,
    service: Annotated[TwoLayerDialecticService, Depends(get_two_layer_dialectic_service)],
) -> dict[str, bool]:
    """Evict cadence counters and cached base context for a session."""
    success = service.reset_session_cadence(session_id)
    return {"ok": success}
