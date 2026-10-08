# [POS]: app/api/memory/auto_memory_consolidation_router.py
# [INPUT]: fastapi, app.schemas.auto_memory_consolidation, app.services.memory.auto_memory_consolidation_service
# [OUTPUT]: router (FastAPI APIRouter for Idle & Budget Gated Auto-Memory Engine Suite)

"""FastAPI router for Idle & Budget Gated Auto-Memory Consolidation Suite (Item 123)."""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, status

from app.schemas.auto_memory_consolidation import (
    AutoMemoryGatingConfigDTO,
    ConsolidateSessionRequest,
    ConsolidateSessionResponse,
    EvaluateGatingRequest,
    EvaluateGatingResponse,
    UpdateGatingConfigRequest,
)
from app.services.memory.auto_memory_consolidation_service import (
    AutoMemoryConsolidationService,
    get_auto_memory_consolidation_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/auto-consolidation",
    tags=["memory-auto-consolidation"],
)


@router.get(
    "/config",
    response_model=AutoMemoryGatingConfigDTO,
    summary="Get active auto-consolidation gating configuration",
)
async def get_gating_config(
    service: AutoMemoryConsolidationService = Depends(get_auto_memory_consolidation_service),
) -> AutoMemoryGatingConfigDTO:
    """Return currently active idle timeout and dual gate threshold configuration."""
    return service.get_config()


@router.put(
    "/config",
    response_model=AutoMemoryGatingConfigDTO,
    summary="Update auto-consolidation gating configuration",
)
async def update_gating_config(
    payload: UpdateGatingConfigRequest,
    service: AutoMemoryConsolidationService = Depends(get_auto_memory_consolidation_service),
) -> AutoMemoryGatingConfigDTO:
    """Modify threshold parameters for idle timeout and token budget gates."""
    return service.update_config(payload.config)


@router.post(
    "/evaluate-gate",
    response_model=EvaluateGatingResponse,
    summary="Audit session admission gates without state mutation",
)
async def evaluate_gating(
    payload: EvaluateGatingRequest,
    service: AutoMemoryConsolidationService = Depends(get_auto_memory_consolidation_service),
) -> EvaluateGatingResponse:
    """Inspect whether a conversation session clears turn, info-density, and budget gates."""
    return service.evaluate_gating(payload)


@router.post(
    "/consolidate",
    response_model=ConsolidateSessionResponse,
    status_code=status.HTTP_200_OK,
    summary="Execute gated auto-consolidation for a session",
)
async def consolidate_session(
    payload: ConsolidateSessionRequest,
    service: AutoMemoryConsolidationService = Depends(get_auto_memory_consolidation_service),
) -> ConsolidateSessionResponse:
    """Trigger background distillation and distill a six-dimensional memory artifact."""
    return service.consolidate(payload)
