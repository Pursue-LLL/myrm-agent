"""FastAPI router for Autonomous Bot Budget Guardrail and Token Ceiling Circuit Breaker.

[INPUT]
- RegisterBotQuotaRequest, ConsumeBudgetRequest, RefuelBotQuotaRequest payloads.

[OUTPUT]
- BotQuotaResponse, ConsumeBudgetResponse, BotQuotaListResponse.

[POS]
- app.api.security.bot_budget_guardrail_router
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Path, status

from app.schemas.bot_budget_guardrail import (
    BotQuotaListResponse,
    BotQuotaResponse,
    ConsumeBudgetRequest,
    ConsumeBudgetResponse,
    RefuelBotQuotaRequest,
    RegisterBotQuotaRequest,
)
from app.services.security.bot_budget_guardrail_service import (
    BotBudgetGuardrailService,
    get_bot_budget_guardrail_service,
)

router = APIRouter(
    prefix="/security/bot-budget-guardrail",
    tags=["Security - Autonomous Bot Budget & Token Ceiling Circuit Breaker"],
)


@router.post("/register", response_model=BotQuotaResponse)
async def register_bot_quota(
    payload: RegisterBotQuotaRequest,
    service: BotBudgetGuardrailService = Depends(get_bot_budget_guardrail_service),
) -> BotQuotaResponse:
    """Register or update an autonomous bot's isolated budget sandbox."""
    return service.register_quota(payload)


@router.post("/consume", response_model=ConsumeBudgetResponse)
async def consume_budget(
    payload: ConsumeBudgetRequest,
    service: BotBudgetGuardrailService = Depends(get_bot_budget_guardrail_service),
) -> ConsumeBudgetResponse:
    """Evaluate and deduct token and cost consumption, enforcing circuit breaker trips."""
    return service.consume_budget(payload)


@router.post("/refuel", response_model=BotQuotaResponse)
async def refuel_bot_quota(
    payload: RefuelBotQuotaRequest,
    service: BotBudgetGuardrailService = Depends(get_bot_budget_guardrail_service),
) -> BotQuotaResponse:
    """Refuel budget quota and optionally reset tripped circuit breaker."""
    try:
        return service.refuel_quota(payload)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc


@router.get("/status/{bot_id}", response_model=BotQuotaResponse)
async def get_bot_quota_status(
    bot_id: str = Path(..., min_length=1, max_length=64, description="Bot identifier"),
    service: BotBudgetGuardrailService = Depends(get_bot_budget_guardrail_service),
) -> BotQuotaResponse:
    """Fetch current live quota watermeter and circuit breaker status for a bot."""
    quota = service.get_quota_status(bot_id)
    if quota is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Bot '{bot_id}' not found in budget registry.",
        )
    return quota


@router.get("/list", response_model=BotQuotaListResponse)
async def list_all_bot_quotas(
    service: BotBudgetGuardrailService = Depends(get_bot_budget_guardrail_service),
) -> BotQuotaListResponse:
    """List all registered autonomous bot budget sandboxes."""
    return service.list_quotas()
