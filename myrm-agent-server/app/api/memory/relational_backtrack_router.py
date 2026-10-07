# [POS]: app/api/memory/relational_backtrack_router.py
# [INPUT]: app.schemas.relational_backtrack, app.services.memory.relational_backtrack_service
# [OUTPUT]: router (FastAPI APIRouter for relational backtrace and cross-session entity backtracking)

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.relational_backtrack import (
    RecordTripletRequest,
    RecordTripletResponse,
    RelationalBacktrackQueryRequest,
    RelationalBacktrackResponseDTO,
    TemporalRelationTripletDTO,
)
from app.services.memory.relational_backtrack_service import (
    RelationalBacktrackService,
    get_relational_backtrack_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/backtrack", tags=["Temporal Relational Anchor & Backtracking"])


@router.post(
    "/record",
    response_model=RecordTripletResponse,
    summary="Record a temporal relation triplet",
)
async def record_triplet(
    request: RecordTripletRequest,
    service: Annotated[RelationalBacktrackService, Depends(get_relational_backtrack_service)],
) -> RecordTripletResponse:
    """Register a structured entity-action-temporal triplet with verifiable evidence quote."""
    return service.record_triplet(request)


@router.post(
    "/query",
    response_model=RelationalBacktrackResponseDTO,
    summary="Query cross-session relational backtrack",
)
async def query_backtrack(
    request: RelationalBacktrackQueryRequest,
    service: Annotated[RelationalBacktrackService, Depends(get_relational_backtrack_service)],
) -> RelationalBacktrackResponseDTO:
    """Execute cross-session relational backtracking for a given action cue (e.g. 打边炉 -> 李总)."""
    return service.query_backtrack(request)


@router.get(
    "/list",
    response_model=list[TemporalRelationTripletDTO],
    summary="List all registered temporal relation triplets",
)
async def list_triplets(
    service: Annotated[RelationalBacktrackService, Depends(get_relational_backtrack_service)],
) -> list[TemporalRelationTripletDTO]:
    """Retrieve all active temporal relation triplets in chronological descending order."""
    return service.list_all_triplets()
