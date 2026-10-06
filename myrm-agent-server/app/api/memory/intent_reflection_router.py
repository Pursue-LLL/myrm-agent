"""
[POS] app/api/memory/intent_reflection_router.py
[INPUT] fastapi, app.schemas.memory_intent_reflection, app.services.memory.memory_intent_reflection_service
[OUTPUT] router

FastAPI router exposing endpoints for Lightweight Reflection Intent Filter and Playbook Activation Probe.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_intent_reflection import (
    ClassifyIntentRequestDTO,
    ClassifyIntentResponseDTO,
    EvaluateActivationRequestDTO,
    EvaluateActivationResponseDTO,
)
from app.services.memory.memory_intent_reflection_service import (
    MemoryIntentReflectionService,
    get_memory_intent_reflection_service,
)

router = APIRouter()


@router.post(
    "/intent-reflection/classify",
    response_model=ClassifyIntentResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Classify query into tiered operational intent levels (Tier 0-3)",
)
def classify_intent(
    request: ClassifyIntentRequestDTO,
    service: MemoryIntentReflectionService = Depends(
        get_memory_intent_reflection_service
    ),
) -> ClassifyIntentResponseDTO:
    """Classify user query into operational intent tier and suggested facets."""
    return service.classify_intent(request)


@router.post(
    "/intent-reflection/evaluate-activation",
    response_model=EvaluateActivationResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Evaluate playbook activation and determine retrieval bypass gating",
)
def evaluate_activation(
    request: EvaluateActivationRequestDTO,
    service: MemoryIntentReflectionService = Depends(
        get_memory_intent_reflection_service
    ),
) -> EvaluateActivationResponseDTO:
    """Filter candidate playbooks and determine if vector retrieval should be bypassed."""
    return service.evaluate_activation(request)
