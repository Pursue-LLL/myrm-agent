"""Budget policy API endpoints.

[INPUT]
- app.services.budget.enforcer (POS: Budget enforcement service)

[OUTPUT]
- GET /policy: Current budget policy
- PUT /policy: Update budget policy
- GET /status: Current day's budget usage status (multi-dimensional)

[POS]
Budget management API. Exposes policy CRUD and real-time spend status.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.errors import internal_error, validation_error
from app.core.utils.response_utils import success_response

router = APIRouter()
logger = logging.getLogger(__name__)


class BudgetPolicyRequest(BaseModel):
    enabled: bool = False
    daily_limit_usd: float | None = Field(default=10.0, ge=0.01, le=10000.0)
    session_limit_usd: float | None = Field(default=5.0, ge=0.01, le=10000.0)
    per_call_limit_usd: float | None = Field(default=None, ge=0.01, le=1000.0)
    warning_threshold: float = Field(default=0.8, ge=0.1, le=1.0)
    finalization_reserve_pct: float = Field(default=0.15, ge=0.05, le=0.5)
    action_on_exceeded: str = Field(default="finalize", pattern=r"^(warn|block|finalize)$")


@router.get("/policy")
async def get_budget_policy() -> JSONResponse:
    """Get current budget policy configuration."""
    try:
        from app.services.budget.enforcer import load_budget_policy

        policy = await load_budget_policy()
        return success_response(data=policy.model_dump())
    except Exception as e:
        raise internal_error(operation="Get budget policy", exception=e) from e


@router.put("/policy")
async def update_budget_policy(req: BudgetPolicyRequest) -> JSONResponse:
    """Update budget policy. Changes take effect immediately."""
    try:
        from app.services.budget.enforcer import BudgetPolicy, save_budget_policy

        policy = BudgetPolicy(
            enabled=req.enabled,
            daily_limit_usd=req.daily_limit_usd,
            session_limit_usd=req.session_limit_usd,
            per_call_limit_usd=req.per_call_limit_usd,
            warning_threshold=req.warning_threshold,
            finalization_reserve_pct=req.finalization_reserve_pct,
            action_on_exceeded=req.action_on_exceeded,
        )
        await save_budget_policy(policy)
        return success_response(data=policy.model_dump())
    except ValueError as e:
        raise validation_error(str(e)) from e
    except Exception as e:
        raise internal_error(operation="Update budget policy", exception=e) from e


@router.get("/status")
async def get_budget_status() -> JSONResponse:
    """Get current budget usage status with multi-dimensional info."""
    try:
        from app.services.budget.enforcer import get_budget_guard_sync, load_budget_policy

        policy = await load_budget_policy()
        if not policy.enabled:
            return success_response(
                data={
                    "enabled": False,
                    "daily_limit_usd": 0,
                    "session_limit_usd": 0,
                    "today_cost_usd": 0,
                    "session_cost_usd": 0,
                    "remaining_usd": 0,
                    "usage_pct": 0,
                    "status": "disabled",
                }
            )

        from myrm_agent_harness.utils.token_economics.multidim_budget import MultidimensionalBudgetGuard

        guard = get_budget_guard_sync()
        if guard is None:
            from app.services.budget.enforcer import get_budget_guard

            guard = await get_budget_guard()

        if guard is None or not isinstance(guard, MultidimensionalBudgetGuard):
            return success_response(
                data={
                    "enabled": True,
                    "daily_limit_usd": policy.daily_limit_usd or 0,
                    "session_limit_usd": policy.session_limit_usd or 0,
                    "today_cost_usd": 0,
                    "session_cost_usd": 0,
                    "remaining_usd": policy.daily_limit_usd or 0,
                    "usage_pct": 0,
                    "status": "ok",
                }
            )

        daily_cost = guard.daily_cost
        session_cost = guard.session_cost
        daily_limit = guard.daily_limit or 0.0
        session_limit = guard.per_session_limit or 0.0
        remaining = guard.get_remaining_budget() or 0.0

        active_limit = session_limit if session_limit > 0 else daily_limit
        active_cost = session_cost if session_limit > 0 else daily_cost
        usage_pct = (active_cost / active_limit * 100) if active_limit > 0 else 0.0

        budget_status = guard.check_budget(0.0)

        return success_response(
            data={
                "enabled": True,
                "daily_limit_usd": round(daily_limit, 2),
                "session_limit_usd": round(session_limit, 2),
                "today_cost_usd": round(daily_cost, 6),
                "session_cost_usd": round(session_cost, 6),
                "remaining_usd": round(remaining, 6),
                "usage_pct": round(usage_pct, 1),
                "status": budget_status.value,
            }
        )
    except Exception as e:
        raise internal_error(operation="Get budget status", exception=e) from e
