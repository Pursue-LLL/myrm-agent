"""FastAPI router for Autonomous Financial Execution Safety Guard and Simulation Suite.

[INPUT]
- app.schemas.financial_safety_guard::TransactionIntentRequest, ApproveTransactionRequest
- app.services.security.financial_safety_guard_service::FinancialSafetyGuardService

[OUTPUT]
- router: APIRouter for financial execution safety guard endpoints

[POS]
Security API surface exposing autonomous financial safety guard, simulations, and approvals.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.financial_safety_guard import (
    ApproveTransactionRequest,
    BudgetConfigUpdateRequest,
    BudgetStatusResponse,
    TransactionIntentRequest,
    TransactionSecurityCardResponse,
)
from app.services.security.financial_safety_guard_service import (
    FinancialSafetyGuardService,
    get_financial_safety_guard_service,
)

router = APIRouter(prefix="/security/financial-safety", tags=["Security - Autonomous Financial Safety Guard"])


@router.post("/evaluate", response_model=TransactionSecurityCardResponse)
async def evaluate_transaction(
    payload: TransactionIntentRequest,
    service: FinancialSafetyGuardService = Depends(get_financial_safety_guard_service),
) -> TransactionSecurityCardResponse:
    """Evaluate pre-flight financial transaction intent through dry-run simulation and budget gates."""
    return service.evaluate_transaction(payload)


@router.post("/approve", response_model=TransactionSecurityCardResponse)
async def approve_transaction(
    payload: ApproveTransactionRequest,
    service: FinancialSafetyGuardService = Depends(get_financial_safety_guard_service),
) -> TransactionSecurityCardResponse:
    """Manually approve a pending transaction suspended for user confirmation."""
    card = service.approve_manually(payload.tx_id)
    if card is None:
        raise HTTPException(
            status_code=404,
            detail=f"Transaction with ID '{payload.tx_id}' not found in pending confirmation queue.",
        )
    return card


@router.get("/budget", response_model=BudgetStatusResponse)
async def get_budget_status(
    service: FinancialSafetyGuardService = Depends(get_financial_safety_guard_service),
) -> BudgetStatusResponse:
    """Retrieve current financial budget limits and daily spending status."""
    return service.get_budget_status()


@router.put("/budget", response_model=BudgetStatusResponse)
async def update_budget(
    payload: BudgetConfigUpdateRequest,
    service: FinancialSafetyGuardService = Depends(get_financial_safety_guard_service),
) -> BudgetStatusResponse:
    """Update financial expenditure budget limits and circuit breaker thresholds."""
    return service.update_budget(payload)


@router.post("/budget/reset", response_model=BudgetStatusResponse)
async def reset_daily_spent(
    service: FinancialSafetyGuardService = Depends(get_financial_safety_guard_service),
) -> BudgetStatusResponse:
    """Reset accumulated daily spending counter back to zero."""
    return service.reset_daily_spent()


@router.get("/history", response_model=list[TransactionSecurityCardResponse])
async def get_history(
    limit: int = Query(default=50, ge=1, le=500),
    service: FinancialSafetyGuardService = Depends(get_financial_safety_guard_service),
) -> list[TransactionSecurityCardResponse]:
    """Retrieve historical audit records of evaluated transaction security cards."""
    return service.get_history(limit=limit)
