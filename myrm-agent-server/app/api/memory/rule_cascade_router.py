"""router (FastAPI APIRouter for deterministic rule cascade and pre-filtering).

[POS]
app/api/memory/rule_cascade_router.py

[INPUT]
- app.schemas.rule_cascade, app.services.memory.rule_cascade_service

[OUTPUT]
- router (FastAPI APIRouter for deterministic rule cascade and pre-filtering)
"""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.rule_cascade import (
    CascadedRuleSetDTO,
    DeterministicRuleEntryDTO,
    PreFilteredEvidenceResponse,
    PreFilterEvidenceRequest,
    QueryCascadedRulesRequest,
    RegisterRuleRequest,
    RegisterRuleResponse,
)
from app.services.memory.rule_cascade_service import (
    RuleCascadeService,
    get_rule_cascade_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/rules", tags=["Deterministic Rule Cascade & Pre-Filter"])


@router.post(
    "/register",
    response_model=RegisterRuleResponse,
    summary="Register a deterministic engineering rule",
)
async def register_rule(
    request: RegisterRuleRequest,
    service: Annotated[RuleCascadeService, Depends(get_rule_cascade_service)],
) -> RegisterRuleResponse:
    """Register a deterministic engineering constraint across global, workspace, or directory scopes."""
    return service.register_rule(request)


@router.post(
    "/cascade",
    response_model=CascadedRuleSetDTO,
    summary="Resolve deterministic cascaded rules along a target path",
)
async def resolve_cascade(
    request: QueryCascadedRulesRequest,
    service: Annotated[RuleCascadeService, Depends(get_rule_cascade_service)],
) -> CascadedRuleSetDTO:
    """Resolve rules hierarchically along ancestor paths with child override semantics."""
    return service.resolve_cascade(request.target_path)


@router.post(
    "/pre-filter",
    response_model=PreFilteredEvidenceResponse,
    summary="Execute physical 5-dimensional pre-filtering",
)
async def pre_filter_evidence(
    request: PreFilterEvidenceRequest,
    service: Annotated[RuleCascadeService, Depends(get_rule_cascade_service)],
) -> PreFilteredEvidenceResponse:
    """Filter candidate evidence against physical 5D boundaries prior to recall."""
    return service.filter_evidence(request)


@router.get(
    "/list",
    response_model=list[DeterministicRuleEntryDTO],
    summary="List all registered deterministic rules",
)
async def list_rules(
    service: Annotated[RuleCascadeService, Depends(get_rule_cascade_service)],
) -> list[DeterministicRuleEntryDTO]:
    """Retrieve all active deterministic rules registered in the system."""
    return service.list_all_rules()
