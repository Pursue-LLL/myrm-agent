# [POS]: app/api/memory/fact_supersession_router.py
# [INPUT]: app.schemas.fact_supersession, app.services.memory.fact_supersession_service
# [OUTPUT]: router (FastAPI APIRouter for Fact Supersession and Temporal Validity)

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, Query

from app.schemas.fact_supersession import (
    DialecticRecallResponseDTO,
    FactHistoryResponseDTO,
    QuarantineItemDTO,
    RegisterFactRequest,
    RegisterFactResponse,
    ResolveQuarantineRequest,
    TimeTravelRecallRequest,
)
from app.services.memory.fact_supersession_service import (
    FactSupersessionService,
    get_fact_supersession_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/supersession", tags=["Fact Supersession & Temporal Validity"])


@router.post(
    "/facts",
    response_model=RegisterFactResponse,
    summary="Register a fact with contradiction quarantine gate",
)
async def register_fact(
    request: RegisterFactRequest,
    service: Annotated[FactSupersessionService, Depends(get_fact_supersession_service)],
) -> RegisterFactResponse:
    """Ingest a fact assertion; automatically supersedes or quarantines upon contradiction."""
    return service.register_fact(request)


@router.post(
    "/recall",
    response_model=DialecticRecallResponseDTO,
    summary="Explainable recall with supersession lineage and time-travel",
)
async def recall_facts(
    request: TimeTravelRecallRequest,
    service: Annotated[FactSupersessionService, Depends(get_fact_supersession_service)],
) -> DialecticRecallResponseDTO:
    """Retrieve active or as-of historical facts projecting ancestral supersession lineage."""
    return service.recall(request)


@router.get(
    "/quarantine",
    response_model=list[QuarantineItemDTO],
    summary="List quarantined factual contradictions",
)
async def list_quarantine(
    service: Annotated[FactSupersessionService, Depends(get_fact_supersession_service)],
    status: str | None = Query(default="quarantined", description="Filter by quarantine status"),
) -> list[QuarantineItemDTO]:
    """Retrieve contradictory fact candidates waiting for human review."""
    return service.list_quarantine(status=status)


@router.post(
    "/quarantine/{quarantine_id}/resolve",
    response_model=RegisterFactResponse,
    summary="Resolve a quarantined contradiction (human review)",
)
async def resolve_quarantine(
    quarantine_id: str,
    request: ResolveQuarantineRequest,
    service: Annotated[FactSupersessionService, Depends(get_fact_supersession_service)],
) -> RegisterFactResponse:
    """Approve override to supersede the active fact, or reject the candidate."""
    return service.resolve_quarantine(quarantine_id, request)


@router.get(
    "/facts/{fact_id}/history",
    response_model=FactHistoryResponseDTO,
    summary="Get backward supersession history for a fact",
)
async def get_fact_history(
    fact_id: str,
    service: Annotated[FactSupersessionService, Depends(get_fact_supersession_service)],
) -> FactHistoryResponseDTO:
    """Retrieve all ancestor facts superseded leading to this fact."""
    return service.get_fact_history(fact_id)
