"""Budget policy API endpoints.

[INPUT]
- app.services.budget.enforcer (POS: Budget enforcement service)
- app.services.budget.channel_budget (POS: Per-channel budget enforcement)

[OUTPUT]
- GET /policy: Current budget policy
- PUT /policy: Update budget policy
- GET /status: Current day's budget usage status (multi-dimensional)
- GET /channels: All channel budget policies and statuses
- PUT /channels/{channel_key}: Create/update a channel budget policy
- DELETE /channels/{channel_key}: Remove a channel budget policy
- GET /channels/{channel_key}/audit: Audit log for a channel's spending

[POS]
Budget management API. Exposes global and per-channel policy CRUD, real-time spend status,
and channel audit attribution queries.
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


# --- Per-channel budget endpoints ---


class ChannelBudgetPolicyRequest(BaseModel):
    daily_limit_usd: float = Field(default=2.0, ge=0.01, le=10000.0)
    warning_threshold: float = Field(default=0.8, ge=0.1, le=1.0)
    enabled: bool = True
    label: str = ""


@router.get("/channels")
async def get_channel_budgets() -> JSONResponse:
    """Get all channel budget policies and current statuses."""
    try:
        from app.services.budget.channel_budget import (
            get_channel_budget_registry,
            load_channel_budget_policies,
        )

        config = await load_channel_budget_policies()
        registry = get_channel_budget_registry()
        statuses = registry.get_all_statuses()
        return success_response(
            data={
                "policies": [p.model_dump() for p in config.policies],
                "statuses": statuses,
            }
        )
    except Exception as e:
        raise internal_error(operation="Get channel budgets", exception=e) from e


@router.put("/channels/{channel_key:path}")
async def update_channel_budget(channel_key: str, req: ChannelBudgetPolicyRequest) -> JSONResponse:
    """Create or update a channel budget policy."""
    try:
        from app.services.budget.channel_budget import (
            ChannelBudgetPolicy,
            save_channel_budget_policy,
        )

        policy = ChannelBudgetPolicy(
            channel_key=channel_key,
            daily_limit_usd=req.daily_limit_usd,
            warning_threshold=req.warning_threshold,
            enabled=req.enabled,
            label=req.label,
        )
        await save_channel_budget_policy(policy)
        return success_response(data=policy.model_dump())
    except ValueError as e:
        raise validation_error(str(e)) from e
    except Exception as e:
        raise internal_error(operation="Update channel budget", exception=e) from e


@router.delete("/channels/{channel_key:path}")
async def delete_channel_budget(channel_key: str) -> JSONResponse:
    """Remove a channel budget policy."""
    try:
        from app.services.budget.channel_budget import delete_channel_budget_policy

        deleted = await delete_channel_budget_policy(channel_key)
    except Exception as e:
        raise internal_error(operation="Delete channel budget", exception=e) from e
    if not deleted:
        raise validation_error(f"Channel budget policy not found: {channel_key}")
    return success_response(data={"deleted": channel_key})


@router.get("/channels/{channel_key:path}/audit")
async def get_channel_audit(channel_key: str, days: int = 7) -> JSONResponse:
    """Get spending audit for a channel grouped by sender."""
    try:
        from datetime import date, datetime, timedelta

        from sqlalchemy import and_, func, select

        from app.database.models.chat import Chat, Message
        from app.platform_utils import get_session_factory

        session_factory = get_session_factory()
        since = datetime.combine(date.today() - timedelta(days=days), datetime.min.time())
        cost_expr = func.json_extract(Message.extra_data, "$.costUsd")
        sender_expr = func.json_extract(Message.extra_data, "$.channelSenderId")

        async with session_factory() as session:
            result = await session.execute(
                select(
                    sender_expr.label("sender_id"),
                    func.count(Message.id).label("message_count"),
                    func.coalesce(func.sum(cost_expr), 0.0).label("total_cost"),
                )
                .join(Chat, Message.chat_id == Chat.id)
                .where(
                    and_(
                        Chat.channel_session_key.like(f"{channel_key}%"),
                        Message.role == "assistant",
                        Message.extra_data.isnot(None),
                        Message.created_at >= since,
                        cost_expr.isnot(None),
                    )
                )
                .group_by(sender_expr)
                .order_by(func.sum(cost_expr).desc())
            )
            rows = result.all()

        audit_entries = [
            {
                "sender_id": row.sender_id or "unknown",
                "message_count": row.message_count,
                "total_cost_usd": round(float(row.total_cost), 6),
            }
            for row in rows
        ]

        return success_response(
            data={
                "channel_key": channel_key,
                "period_days": days,
                "entries": audit_entries,
                "total_cost_usd": round(sum(e["total_cost_usd"] for e in audit_entries), 6),
            }
        )
    except Exception as e:
        raise internal_error(operation="Get channel audit", exception=e) from e
