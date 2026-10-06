"""
[POS] app/api/memory/crystallization_router.py
[INPUT] fastapi, app.schemas.memory_crystallization, app.services.memory.memory_crystallization_service
[OUTPUT] router

FastAPI router exposing endpoints for Procedural Memory Crystallization Lifecycle and Self-Correction Governor.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.memory_crystallization import (
    CrystallizedRuleMetricsDTO,
    EvaluateFormationRequestDTO,
    EvaluateFormationResponseDTO,
    FilterFacetsRequestDTO,
    FilterFacetsResponseDTO,
    RecordFeedbackRequestDTO,
    RecordFeedbackResponseDTO,
)
from app.services.memory.memory_crystallization_service import (
    MemoryCrystallizationService,
    get_memory_crystallization_service,
)

router = APIRouter()


@router.post(
    "/crystallization/evaluate-formation",
    response_model=EvaluateFormationResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Evaluate formation-stage two-factor importance gate (confidence x severity >= 0.70)",
)
def evaluate_formation_gate(
    request: EvaluateFormationRequestDTO,
    service: MemoryCrystallizationService = Depends(get_memory_crystallization_service),
) -> EvaluateFormationResponseDTO:
    """Evaluate two-factor importance to filter trivial dialogue noise from entering the procedural ruleset."""
    return service.evaluate_formation_gate(request)


@router.post(
    "/crystallization/filter-facets",
    response_model=FilterFacetsResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Filter candidate rules by active operational domain facets",
)
def filter_by_facets(
    request: FilterFacetsRequestDTO,
    service: MemoryCrystallizationService = Depends(get_memory_crystallization_service),
) -> FilterFacetsResponseDTO:
    """Filter and rank active rules by operational domain facets, categorically excluding retired rules."""
    return service.filter_by_facets(request)


@router.post(
    "/crystallization/record-feedback",
    response_model=RecordFeedbackResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Record execution outcome feedback, apply repeat error penalty, and evolve lifecycle state",
)
def record_execution_feedback(
    request: RecordFeedbackRequestDTO,
    service: MemoryCrystallizationService = Depends(get_memory_crystallization_service),
) -> RecordFeedbackResponseDTO:
    """Process execution outcome, apply same-session repeat error penalty, and trigger dynamic degradation or retirement."""
    return service.record_execution_feedback(request)


@router.get(
    "/crystallization/rules/{rule_id}/metrics",
    response_model=CrystallizedRuleMetricsDTO,
    status_code=status.HTTP_200_OK,
    summary="Fetch current telemetry and lifecycle status for a crystallized rule",
)
def get_rule_metrics(
    rule_id: str,
    service: MemoryCrystallizationService = Depends(get_memory_crystallization_service),
) -> CrystallizedRuleMetricsDTO:
    """Retrieve operational telemetry, empirical win rate, and lifecycle state for a given rule."""
    metrics = service.get_rule_metrics(rule_id)
    if metrics is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Crystallized rule '{rule_id}' not found.",
        )
    return metrics
