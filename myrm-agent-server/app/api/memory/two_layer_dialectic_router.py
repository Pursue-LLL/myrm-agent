# [POS]: app/api/memory/two_layer_dialectic_router.py
# [INPUT]: app.schemas.two_layer_dialectic, app.services.memory.two_layer_dialectic_service
# [OUTPUT]: router (FastAPI APIRouter for Two-Layer Dialectic Suite)

"""FastAPI router for Two-Layer Context Injection & Multi-Pass Dialectic Reconciliation (Item 112)."""

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
