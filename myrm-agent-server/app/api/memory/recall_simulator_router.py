"""
[POS] app/api/memory/recall_simulator_router.py
[INPUT] app/schemas/memory_recall_simulator.py, app/services/memory/recall_simulator_service.py
[OUTPUT] router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_recall_simulator import (
    MemoryGovernanceUpdateRequest,
    MemoryGovernanceUpdateResponse,
    RecallSimulateRequest,
    RecallSimulateResponse,
)
from app.services.memory.recall_simulator_service import (
    RecallSimulatorService,
    get_recall_simulator_service,
)

router = APIRouter(prefix="/simulate-recall", tags=["memory_recall_simulator"])


@router.post(
    "",
    response_model=RecallSimulateResponse,
    status_code=status.HTTP_200_OK,
    summary="Simulate multi-channel memory recall and RRF fusion ranking",
)
def simulate_memory_recall(
    request: RecallSimulateRequest,
    service: RecallSimulatorService = Depends(get_recall_simulator_service),
) -> RecallSimulateResponse:
    """Evaluate test query against BM25, vector semantic, and causal gene channels."""
    return service.simulate_recall(request)


@router.post(
    "/govern",
    response_model=MemoryGovernanceUpdateResponse,
    status_code=status.HTTP_200_OK,
    summary="Perform in-place secondary governance adjustments on memory candidates",
)
def update_memory_governance(
    request: MemoryGovernanceUpdateRequest,
    service: RecallSimulatorService = Depends(get_recall_simulator_service),
) -> MemoryGovernanceUpdateResponse:
    """Adjust confidence weight, flip negative trap flag, or update status/merge duplicates."""
    return service.update_governance(request)
