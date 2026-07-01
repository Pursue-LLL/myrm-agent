"""Budget enforcement service.

Loads budget policy from UserConfig, manages a process-scoped MultidimensionalBudgetGuard
singleton, and provides the guard to agent factory for injection.

[INPUT]
- myrm_agent_harness.utils.token_economics::BudgetChecker (POS: Budget guard protocol)
- myrm_agent_harness.utils.token_economics::MultidimensionalBudgetGuard (POS: Multi-dimensional budget guard)
- myrm_agent_harness.utils.token_economics::BudgetDimension (POS: Budget dimension config)
- app.database.models.chat::Message (POS: 消息域模型)
- app.database.models.config::UserConfig (POS: 用户配置域模型)
- app.services.event.app_event_bus::ServerEventBus (POS: In-process SSE event bus)

[OUTPUT]
- BudgetPolicy: Pydantic model for budget policy configuration
- get_budget_guard: Returns process-scoped BudgetChecker (or None if disabled)
- load_budget_policy: Loads policy from DB
- save_budget_policy: Persists policy to DB
- should_block_execution: Returns True if execution should be blocked
- reset_session_budget: Resets session counter for new conversations
- is_eco_mode_active: Returns True when budget pressure warrants eco mode (synchronous)

[POS]
Budget enforcement service. Bridges harness MultidimensionalBudgetGuard with server-side
persistence and SSE alerts. Supports per-session, daily, and per-call dimensions with
three-level progressive response.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date, datetime

from myrm_agent_harness.utils.token_economics.budget_guard import (
    BudgetChecker,
    BudgetStatus,
)
from myrm_agent_harness.utils.token_economics.multidim_budget import (
    BudgetDimension,
    MultidimensionalBudgetGuard,
)
from pydantic import BaseModel, Field
from sqlalchemy import and_, func, select

from app.database.models.chat import Message
from app.database.models.config import UserConfig
from app.platform_utils import get_session_factory
from app.platform_utils.deployment_capabilities import get_deployment_capabilities
from app.platform_utils.sandbox.entitlements.platform_budget_adapter import PlatformBudgetAdapter

logger = logging.getLogger(__name__)

BUDGET_CONFIG_KEY = "budget_policy"

_guard_instance: "_BudgetGuardWrapper | None" = None
_platform_guard: PlatformBudgetAdapter | None = None


class BudgetPolicy(BaseModel):
    """Budget policy configuration stored in UserConfig."""

    enabled: bool = False
    daily_limit_usd: float | None = Field(default=10.0, ge=0.01, le=10000.0)
    session_limit_usd: float | None = Field(default=5.0, ge=0.01, le=10000.0)
    per_call_limit_usd: float | None = Field(default=None, ge=0.01, le=1000.0)
    warning_threshold: float = Field(default=0.8, ge=0.1, le=1.0)
    finalization_reserve_pct: float = Field(default=0.15, ge=0.05, le=0.5)
    action_on_exceeded: str = Field(default="finalize", pattern=r"^(warn|block|finalize)$")


class _BudgetGuardWrapper:
    """Wraps MultidimensionalBudgetGuard with SSE alert emission."""

    def __init__(self, policy: BudgetPolicy, initial_daily_cost: float = 0.0) -> None:
        self._policy = policy

        per_session = (
            BudgetDimension(
                limit_usd=policy.session_limit_usd,
                warning_threshold=policy.warning_threshold,
            )
            if policy.session_limit_usd is not None
            else None
        )
        daily = (
            BudgetDimension(
                limit_usd=policy.daily_limit_usd,
                warning_threshold=policy.warning_threshold,
            )
            if policy.daily_limit_usd is not None
            else None
        )
        per_call = (
            BudgetDimension(
                limit_usd=policy.per_call_limit_usd,
                warning_threshold=policy.warning_threshold,
            )
            if policy.per_call_limit_usd is not None
            else None
        )

        self._guard = MultidimensionalBudgetGuard(
            per_session=per_session,
            daily=daily,
            per_call=per_call,
            finalization_reserve_pct=policy.finalization_reserve_pct,
            on_warning=self._emit_warning,
            on_finalization=self._emit_finalization,
            on_exceeded=self._emit_exceeded,
            on_update=self._emit_update,
            initial_daily_cost=initial_daily_cost,
        )

    def _emit_update(self, cost: float, limit: float, dimension: str) -> None:
        _emit_budget_sse("update", cost, limit, dimension)

    def _emit_warning(self, cost: float, limit: float, dimension: str) -> None:
        _emit_budget_sse("warning", cost, limit, dimension)

    def _emit_finalization(self, cost: float, limit: float, dimension: str) -> None:
        _emit_budget_sse("finalization", cost, limit, dimension)

    def _emit_exceeded(self, cost: float, limit: float, dimension: str) -> None:
        _emit_budget_sse("exceeded", cost, limit, dimension)

    @property
    def guard(self) -> MultidimensionalBudgetGuard:
        return self._guard

    @property
    def policy(self) -> BudgetPolicy:
        return self._policy


def _emit_budget_sse(status: str, cost: float, limit: float, dimension: str) -> None:
    """Emit a budget alert SSE event for frontend toast/badge."""
    try:
        from app.services.event.app_event_bus import AppEvent, AppEventType, get_event_bus

        pct = round((cost / limit) * 100, 1) if limit > 0 else 100.0

        event_type = AppEventType.BUDGET_UPDATED if status == "update" else AppEventType.BUDGET_ALERT

        get_event_bus().publish(
            AppEvent(
                event_type=event_type,
                data={
                    "subtype": ("budget_alert" if status != "update" else "budget_update"),
                    "status": status,
                    "dimension": dimension,
                    "today_cost": round(cost, 6),
                    "daily_limit": round(limit, 6),
                    "remaining": round(max(0.0, limit - cost), 6),
                    "pct": pct,
                    "eco_mode": status in ("warning", "finalization", "exceeded"),
                },
            )
        )
    except Exception as e:
        logger.warning("Failed to emit budget SSE alert: %s", e)


async def load_budget_policy() -> BudgetPolicy:
    """Load budget policy from DB. Returns default (disabled) if not configured."""
    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(UserConfig).where(UserConfig.config_key == BUDGET_CONFIG_KEY))
        row = result.scalar_one_or_none()
        if row is None:
            return BudgetPolicy()
        try:
            return BudgetPolicy.model_validate(row.config_value)
        except Exception:
            logger.warning("Invalid budget policy in DB, returning defaults")
            return BudgetPolicy()


async def save_budget_policy(policy: BudgetPolicy) -> None:
    """Persist budget policy to UserConfig and refresh the guard singleton."""
    global _guard_instance

    session_factory = get_session_factory()
    async with session_factory() as session:
        result = await session.execute(select(UserConfig).where(UserConfig.config_key == BUDGET_CONFIG_KEY))
        row = result.scalar_one_or_none()
        now_version = f"{int(datetime.now().timestamp() * 1000)}_0"

        if row is not None:
            row.config_value = policy.model_dump()  # type: ignore[assignment]
            row.version = now_version
        else:
            new_config = UserConfig(
                id=str(uuid.uuid4()),
                config_key=BUDGET_CONFIG_KEY,
                config_value=policy.model_dump(),  # type: ignore[assignment]
                version=now_version,
                last_device_id="server",
                is_encrypted=False,
            )
            session.add(new_config)
        await session.commit()

    if policy.enabled:
        if _guard_instance is not None:
            carry_daily = _guard_instance.guard.daily_cost
        else:
            carry_daily = await _query_today_cost()
        _guard_instance = _BudgetGuardWrapper(policy, initial_daily_cost=carry_daily)
    else:
        _guard_instance = None


async def _query_today_cost() -> float:
    """Sum costUsd from today's assistant messages to recover spend after process restart."""
    try:
        session_factory = get_session_factory()
        today_start = datetime.combine(date.today(), datetime.min.time())
        cost_expr = func.json_extract(Message.extra_data, "$.costUsd")
        async with session_factory() as session:
            result = await session.execute(
                select(func.coalesce(func.sum(cost_expr), 0.0)).where(
                    and_(
                        Message.role == "assistant",
                        Message.extra_data.isnot(None),
                        Message.created_at >= today_start,
                        cost_expr.isnot(None),
                    )
                )
            )
            total: float = float(result.scalar_one())
        return total
    except Exception as e:
        logger.warning("Failed to recover today's cost from DB, starting from $0: %s", e)
        return 0.0


async def get_budget_guard() -> BudgetChecker | None:
    """Return the process-scoped BudgetChecker instance (or None if disabled).

    Lazily loads from DB on first call. On first initialization, recovers today's
    accumulated cost from the Message table to survive process restarts.
    """
    global _guard_instance, _platform_guard

    if get_deployment_capabilities().uses_platform_budget:
        if _platform_guard is None:
            _platform_guard = PlatformBudgetAdapter()
        return _platform_guard if _platform_guard.is_configured else None

    if _guard_instance is not None:
        return _guard_instance.guard

    policy = await load_budget_policy()
    if not policy.enabled:
        return None

    initial_cost = await _query_today_cost()
    if initial_cost > 0:
        logger.info("Budget guard recovered today's cost from DB: $%.4f", initial_cost)
    _guard_instance = _BudgetGuardWrapper(policy, initial_daily_cost=initial_cost)
    return _guard_instance.guard


def get_budget_guard_sync() -> BudgetChecker | None:
    """Non-async accessor for contexts where the guard is already initialized."""
    if _guard_instance is not None:
        return _guard_instance.guard
    return None


_current_session_chat_id: str | None = None


def reset_session_budget(chat_id: str | None = None) -> None:
    """Reset session budget counter only when chat_id changes (new conversation).

    If chat_id is None, always resets (backward compat for headless/cron).
    """
    global _current_session_chat_id

    if chat_id is not None and chat_id == _current_session_chat_id:
        return

    _current_session_chat_id = chat_id
    if _guard_instance is not None:
        _guard_instance.guard.reset_session()


async def should_block_execution() -> bool:
    """Check if agent execution should be blocked due to budget exceeded + block policy.

    Returns True when budget is enabled, action_on_exceeded is 'block',
    and current spend has exceeded the limit.
    """
    if get_deployment_capabilities().uses_platform_budget:
        guard = await get_budget_guard()
        if guard is None:
            return True
        status = guard.check_budget(0.0)
        return status in (BudgetStatus.EXCEEDED, BudgetStatus.FINALIZATION)

    policy = await load_budget_policy()
    if not policy.enabled or policy.action_on_exceeded != "block":
        return False

    guard = await get_budget_guard()
    if guard is None:
        return False

    status = guard.check_budget(0.0)
    return status in (BudgetStatus.EXCEEDED, BudgetStatus.FINALIZATION)


def is_eco_mode_active() -> bool:
    """Check if eco mode should be active (budget at or above warning threshold).

    Synchronous check for use as budget_pressure_fn callback in context pipeline.
    Returns False when budget is disabled or guard is not initialized.
    """
    if _guard_instance is None:
        return False
    return _guard_instance.guard.check_budget(0.0) in (
        BudgetStatus.WARNING,
        BudgetStatus.FINALIZATION,
        BudgetStatus.EXCEEDED,
    )
