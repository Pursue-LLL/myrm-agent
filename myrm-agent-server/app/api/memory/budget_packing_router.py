# [POS]: app/api/memory/budget_packing_router.py
# [INPUT]: app.schemas.budget_packing, app.services.memory.budget_packing_service
# [OUTPUT]: router (FastAPI APIRouter for Budget Greedy Marginal Value Recall Packing Suite)

"""FastAPI router for Budget Greedy Marginal Value Recall Packing Suite (Item 122)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.budget_packing import (
    BilledTokenBudgetDTO,
    InspectMarginalRequest,
    InspectMarginalResponseItem,
    PackedRecallResultDTO,
    PackRecallRequest,
)
from app.services.memory.budget_packing_service import (
    BudgetPackingService,
    get_budget_packing_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/budget-packing", tags=["Budget Recall Packing"])


@router.post(
    "/pack",
    response_model=PackedRecallResultDTO,
    summary="Execute budget-governed greedy knapsack recall packing",
)
async def pack_recall_candidates(
    request: PackRecallRequest,
    service: Annotated[BudgetPackingService, Depends(get_budget_packing_service)],
) -> PackedRecallResultDTO:
    """Pack candidate memories maximizing marginal utility density within token budget."""
    return service.pack_candidates(
        candidates=request.candidates,
        budget=request.budget,
        enable_knapsack=request.enable_knapsack,
    )


@router.post(
    "/inspect-marginal",
    response_model=list[InspectMarginalResponseItem],
    summary="Inspect marginal value and redundancy degradation for candidates",
)
async def inspect_marginal_values(
    request: InspectMarginalRequest,
    service: Annotated[BudgetPackingService, Depends(get_budget_packing_service)],
) -> list[InspectMarginalResponseItem]:
    """Inspect incremental marginal utility decay and diversity penalties."""
    return service.inspect_marginal_values(
        candidates=request.candidates,
        budget=request.budget,
    )


@router.get(
    "/default-budget",
    response_model=BilledTokenBudgetDTO,
    summary="Get recommended default token budget configuration",
)
async def get_default_budget(
    service: Annotated[BudgetPackingService, Depends(get_budget_packing_service)],
) -> BilledTokenBudgetDTO:
    """Return platform default token budget and diversity penalty hyper-parameters."""
    return service.get_default_budget()
