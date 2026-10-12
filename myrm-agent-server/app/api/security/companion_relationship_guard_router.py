"""API router for Companion Relationship Safety Guard.

[INPUT]
- EvaluateCompanionInteractionRequest.

[OUTPUT]
- EvaluateCompanionInteractionResponse, CompanionContractSummaryResponse.

[POS]
- Security router mounted under /security/companion-relationship-guard.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.companion_relationship_guard import (
    CompanionContractSummaryResponse,
    EvaluateCompanionInteractionRequest,
    EvaluateCompanionInteractionResponse,
)
from app.services.security.companion_relationship_guard_service import (
    CompanionRelationshipGuardService,
    get_companion_relationship_guard_service,
)

router = APIRouter(
    prefix="/companion-relationship-guard", tags=["companion-relationship-guard"]
)


@router.post("/evaluate", response_model=EvaluateCompanionInteractionResponse)
async def evaluate_companion_interaction(
    request: EvaluateCompanionInteractionRequest,
    service: CompanionRelationshipGuardService = Depends(
        get_companion_relationship_guard_service
    ),
) -> EvaluateCompanionInteractionResponse:
    """Evaluate candidate assistant response against companion decorum and anti-exploitation boundaries."""
    return service.evaluate_interaction(request)


@router.get("/contract", response_model=CompanionContractSummaryResponse)
async def get_companion_contract_summary(
    service: CompanionRelationshipGuardService = Depends(
        get_companion_relationship_guard_service
    ),
) -> CompanionContractSummaryResponse:
    """Retrieve established companion decorum boundaries and compliance redlines."""
    return service.get_contract_summary()
