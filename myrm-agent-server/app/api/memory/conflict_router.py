"""
[POS] app/api/memory/conflict_router.py
[INPUT] fastapi, app/schemas/memory_conflict.py, app/services/memory/memory_conflict_service.py
[OUTPUT] router

FastAPI router exposing working memory conflict semantic arbitration, human decision cards, and user-confirmed freeze gate endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_conflict import (
    EvaluateConflictRequestDTO,
    EvaluateConflictResponseDTO,
    FreezeLockStatusResponseDTO,
    HumanArbitrateRequestDTO,
    HumanArbitrateResponseDTO,
    PendingConflictListResponseDTO,
    UnlockDecisionRequestDTO,
    UnlockDecisionResponseDTO,
)
from app.services.memory.memory_conflict_service import (
    MemoryConflictService,
    get_memory_conflict_service,
)

router = APIRouter()


@router.post(
    "/conflict/evaluate",
    response_model=EvaluateConflictResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Evaluate semantic conflict between existing memory fact and candidate fact",
)
def evaluate_conflict(
    request: EvaluateConflictRequestDTO,
    service: MemoryConflictService = Depends(get_memory_conflict_service),
) -> EvaluateConflictResponseDTO:
    """Analyze factual divergence, determine merge vs override vs contradiction, and stage if disputed."""
    return service.evaluate_and_stage(request)


@router.get(
    "/conflict/pending",
    response_model=PendingConflictListResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="List all conflicting memory facts pending human arbitration review",
)
def list_pending_conflicts(
    service: MemoryConflictService = Depends(get_memory_conflict_service),
) -> PendingConflictListResponseDTO:
    """Fetch all suspended factual contradictions requiring human finalization."""
    return service.list_pending_conflicts()


@router.post(
    "/conflict/arbitrate",
    response_model=HumanArbitrateResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Submit human operator final decision on conflicting fact with immutable freeze lock",
)
def arbitrate_conflict(
    request: HumanArbitrateRequestDTO,
    service: MemoryConflictService = Depends(get_memory_conflict_service),
) -> HumanArbitrateResponseDTO:
    """Apply operator choice, finalize fact text, and guard with UserConfirmedFreezeLock."""
    return service.apply_human_arbitration(request)


@router.get(
    "/conflict/freeze/{memory_id}",
    response_model=FreezeLockStatusResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Query active freeze lock status and cryptographic integrity of a memory record",
)
def get_freeze_status(
    memory_id: str,
    service: MemoryConflictService = Depends(get_memory_conflict_service),
) -> FreezeLockStatusResponseDTO:
    """Verify whether memory is protected by immutable user-confirmed lock."""
    return service.get_freeze_status(memory_id)


@router.post(
    "/conflict/unlock",
    response_model=UnlockDecisionResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Explicitly release user-confirmed freeze lock with operator audit trail",
)
def unlock_decision(
    request: UnlockDecisionRequestDTO,
    service: MemoryConflictService = Depends(get_memory_conflict_service),
) -> UnlockDecisionResponseDTO:
    """Release freeze lock to allow subsequent mutations."""
    return service.unlock_decision(request)
