"""
[POS] app/api/memory/dialectic.py
[INPUT] fastapi, app.schemas.memory_dialectic, app.services.memory.memory_dialectic_service
[OUTPUT] router

FastAPI router exposing endpoints for Dialectic Profile Reasoning and Adaptive Context Cadence Engine.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.memory_dialectic import (
    DialecticCadenceStatusResponseDTO,
    DialecticEphemeralMindDTO,
    DialecticProcessTurnRequestDTO,
    DialecticReasoningResponseDTO,
)
from app.services.memory.memory_dialectic_service import (
    MemoryDialecticService,
    get_memory_dialectic_service,
)

router = APIRouter()


@router.post(
    "/dialectic/turns/process",
    response_model=DialecticReasoningResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Process an interaction turn with dialectic reasoning and cadence throttling",
)
def process_interaction_turn(
    request: DialecticProcessTurnRequestDTO,
    service: MemoryDialecticService = Depends(get_memory_dialectic_service),
) -> DialecticReasoningResponseDTO:
    """Evaluate turn interaction, infer implicit goals and resistance points, governed by cadence throttling."""
    return service.process_turn(request)


@router.get(
    "/dialectic/cadence/status/{conversation_id}",
    response_model=DialecticCadenceStatusResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Retrieve live cadence governor telemetry and heat state for a conversation",
)
def get_cadence_status(
    conversation_id: str,
    service: MemoryDialecticService = Depends(get_memory_dialectic_service),
) -> DialecticCadenceStatusResponseDTO:
    """Retrieve cadence status, heat classification, and upcoming extraction eligibility."""
    return service.get_cadence_status(conversation_id)


@router.get(
    "/dialectic/mind/{conversation_id}",
    response_model=DialecticEphemeralMindDTO,
    status_code=status.HTTP_200_OK,
    summary="Retrieve the active ephemeral mind cognition snapshot for a conversation",
)
def get_ephemeral_mind(
    conversation_id: str,
    service: MemoryDialecticService = Depends(get_memory_dialectic_service),
) -> DialecticEphemeralMindDTO:
    """Retrieve the latest ephemeral mind snapshot. Returns 404 if not yet generated."""
    mind = service.get_ephemeral_mind(conversation_id)
    if mind is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"No active ephemeral mind found for conversation '{conversation_id}'",
        )
    return mind


@router.delete(
    "/dialectic/cadence/{conversation_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Reset cadence governor state for a conversation session",
)
def reset_cadence_session(
    conversation_id: str,
    service: MemoryDialecticService = Depends(get_memory_dialectic_service),
) -> None:
    """Reset the cadence state machine for a specific conversation session."""
    service.reset_session(conversation_id)
