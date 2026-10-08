"""FastAPI router for Experience Compounding and Knowledge Condensation API.

[POS]
Exposes REST endpoints for experience addition, logarithmic reinforcement,
semantic Golden Rule synthesis, rule rollback, context annealing, and stats.

[INPUT]
- fastapi (APIRouter, Depends, status)
- app.schemas.experience_compounding (AddExperienceItemRequest, AnnealingResponseDTO,
  CompoundedExperienceItemDTO, CondensationResponseDTO, DecondenseRuleRequest,
  ExperienceCompoundingStatsResponse, GoldenRuleDTO, ReinforceExperienceRequest)
- app.services.memory.experience_compounding.provider (
  ExperienceCompoundingServiceProvider, get_experience_compounding_service)

[OUTPUT]
- router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.experience_compounding import (
    AddExperienceItemRequest,
    AnnealingResponseDTO,
    CompoundedExperienceItemDTO,
    CondensationResponseDTO,
    DecondenseRuleRequest,
    ExperienceCompoundingStatsResponse,
    GoldenRuleDTO,
    ReinforceExperienceRequest,
)
from app.services.memory.experience_compounding.provider import (
    ExperienceCompoundingServiceProvider,
    get_experience_compounding_service,
)

router = APIRouter(prefix="/compounding", tags=["memory-compounding"])


@router.post(
    "/item",
    response_model=CompoundedExperienceItemDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Register a new experience observation or preference fragment",
)
async def add_experience_item(
    request: AddExperienceItemRequest,
    service: ExperienceCompoundingServiceProvider = Depends(
        get_experience_compounding_service
    ),
) -> CompoundedExperienceItemDTO:
    """Register experience fragment into hot active memory pool."""
    return service.add_experience(request)


@router.post(
    "/reinforce",
    status_code=status.HTTP_200_OK,
    summary="Record verification and apply bounded logarithmic compounding weight growth",
)
async def reinforce_experience(
    request: ReinforceExperienceRequest,
    service: ExperienceCompoundingServiceProvider = Depends(
        get_experience_compounding_service
    ),
) -> dict[str, float | str]:
    """Reinforce experience adoption count and dynamically extend half-life."""
    new_weight = service.reinforce(request)
    return {"status": "reinforced", "item_id": request.item_id, "new_weight": new_weight}


@router.post(
    "/condense",
    response_model=CondensationResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Cluster fragmented notes and synthesize higher-order Golden Rules with lineage",
)
async def condense_knowledge(
    service: ExperienceCompoundingServiceProvider = Depends(
        get_experience_compounding_service
    ),
) -> CondensationResponseDTO:
    """Trigger semantic condensation, archive source fragments, and output Golden Rules."""
    return service.condense()


@router.post(
    "/decondense",
    response_model=list[CompoundedExperienceItemDTO],
    status_code=status.HTTP_200_OK,
    summary="Roll back a Golden Rule and reactivate its archived source fragments",
)
async def decondense_rule(
    request: DecondenseRuleRequest,
    service: ExperienceCompoundingServiceProvider = Depends(
        get_experience_compounding_service
    ),
) -> list[CompoundedExperienceItemDTO]:
    """Reverse Golden Rule synthesis and revive source fragments to active state."""
    return service.decondense(request)


@router.post(
    "/anneal",
    response_model=AnnealingResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Apply exponential annealing decay and demote obsolete contexts to cold storage",
)
async def run_annealing(
    service: ExperienceCompoundingServiceProvider = Depends(
        get_experience_compounding_service
    ),
) -> AnnealingResponseDTO:
    """Decay inactive contexts while exempting active lease protected items."""
    return service.anneal()


@router.get(
    "/rules",
    response_model=list[GoldenRuleDTO],
    status_code=status.HTTP_200_OK,
    summary="List all active Golden Rules",
)
async def list_golden_rules(
    service: ExperienceCompoundingServiceProvider = Depends(
        get_experience_compounding_service
    ),
) -> list[GoldenRuleDTO]:
    """Retrieve synthesized Golden Rules."""
    return service.list_rules()


@router.get(
    "/active",
    response_model=list[CompoundedExperienceItemDTO],
    status_code=status.HTTP_200_OK,
    summary="List all hot active experience fragments",
)
async def list_active_items(
    service: ExperienceCompoundingServiceProvider = Depends(
        get_experience_compounding_service
    ),
) -> list[CompoundedExperienceItemDTO]:
    """Retrieve un-condensed active experience items."""
    return service.list_active()


@router.get(
    "/stats",
    response_model=ExperienceCompoundingStatsResponse,
    status_code=status.HTTP_200_OK,
    summary="Get operational metrics across compounding, condensation, and cold storage",
)
async def get_stats(
    service: ExperienceCompoundingServiceProvider = Depends(
        get_experience_compounding_service
    ),
) -> ExperienceCompoundingStatsResponse:
    """Retrieve system operational telemetry counters."""
    return service.get_stats()
