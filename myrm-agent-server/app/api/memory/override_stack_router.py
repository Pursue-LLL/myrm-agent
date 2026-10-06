"""
[POS] app/api/memory/override_stack_router.py
[INPUT] fastapi, app.schemas.memory_override_stack, app.services.memory.memory_override_stack_service
[OUTPUT] router

FastAPI router exposing endpoints for Playbook Dynamic User Override Stack and Ephemeral Bypass Gate.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_override_stack import (
    EvaluateOverrideStackRequestDTO,
    EvaluateOverrideStackResponseDTO,
)
from app.services.memory.memory_override_stack_service import (
    MemoryOverrideStackService,
    get_memory_override_stack_service,
)

router = APIRouter()


@router.post(
    "/override-stack/evaluate",
    response_model=EvaluateOverrideStackResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Evaluate turn prompt priority over candidate rules and apply ephemeral zero-mutation bypass",
)
def evaluate_override_stack(
    request: EvaluateOverrideStackRequestDTO,
    service: MemoryOverrideStackService = Depends(
        get_memory_override_stack_service
    ),
) -> EvaluateOverrideStackResponseDTO:
    """Enforce Level 1 user prompt primacy, detect acute contradictions, and return safe active rules."""
    return service.resolve_override_stack(request)
