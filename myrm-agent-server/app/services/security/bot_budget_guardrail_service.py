"""Service layer for Autonomous Bot Budget Guardrail and Token Ceiling Circuit Breaker.

[INPUT]
- myrm_agent_harness.core.security.bot_budget_guardrail::*
- app.schemas.bot_budget_guardrail::*

[OUTPUT]
- BotBudgetGuardrailService, get_bot_budget_guardrail_service

[POS]
Service managing isolated budget sandboxes, tiered circuit breaker trips, and quota refueling.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.bot_budget_guardrail import (
    AutonomousBotBudgetGuardrail,
    BotBudgetQuota,
    BudgetConsumeResult,
    BudgetSandboxMode,
)

from app.schemas.bot_budget_guardrail import (
    BotQuotaListResponse,
    BotQuotaResponse,
    ConsumeBudgetRequest,
    ConsumeBudgetResponse,
    RefuelBotQuotaRequest,
    RegisterBotQuotaRequest,
)

logger = logging.getLogger(__name__)


def _to_quota_response(q: BotBudgetQuota) -> BotQuotaResponse:
    return BotQuotaResponse(
        bot_id=q.bot_id,
        bot_name=q.bot_name,
        sandbox_mode=q.sandbox_mode.value,
        token_ceiling=q.token_ceiling,
        cost_ceiling_usd=q.cost_ceiling_usd,
        used_tokens=q.used_tokens,
        used_cost_usd=q.used_cost_usd,
        warning_threshold=q.warning_threshold,
        state=q.state.value,
        frozen_at=q.frozen_at,
        last_updated_at=q.last_updated_at,
    )


def _to_consume_response(r: BudgetConsumeResult) -> ConsumeBudgetResponse:
    return ConsumeBudgetResponse(
        allowed=r.allowed,
        bot_id=r.bot_id,
        state=r.state.value,
        current_used_tokens=r.current_used_tokens,
        current_used_cost_usd=r.current_used_cost_usd,
        tokens_remaining=r.tokens_remaining,
        cost_remaining_usd=r.cost_remaining_usd,
        rejection_reason=r.rejection_reason,
    )


class BotBudgetGuardrailService:
    """Service governing autonomous bot budget sandboxes and circuit breakers."""

    def __init__(self, guardrail: AutonomousBotBudgetGuardrail | None = None) -> None:
        self._guardrail: AutonomousBotBudgetGuardrail = guardrail or AutonomousBotBudgetGuardrail()

    def register_quota(self, req: RegisterBotQuotaRequest) -> BotQuotaResponse:
        """Register or update a bot budget sandbox."""
        mode = (
            BudgetSandboxMode.CORE_PROTECTED
            if req.sandbox_mode == "CORE_PROTECTED"
            else BudgetSandboxMode.ISOLATED_SANDBOX
        )
        quota = BotBudgetQuota(
            bot_id=req.bot_id,
            bot_name=req.bot_name,
            sandbox_mode=mode,
            token_ceiling=req.token_ceiling,
            cost_ceiling_usd=req.cost_ceiling_usd,
            warning_threshold=req.warning_threshold,
        )
        self._guardrail.register_bot_quota(quota)
        return _to_quota_response(quota)

    def consume_budget(self, req: ConsumeBudgetRequest) -> ConsumeBudgetResponse:
        """Evaluate consumption against budget sandbox and enforce circuit breaker."""
        res = self._guardrail.consume_budget(
            bot_id=req.bot_id,
            tokens=req.tokens,
            cost_usd=req.cost_usd,
        )
        return _to_consume_response(res)

    def refuel_quota(self, req: RefuelBotQuotaRequest) -> BotQuotaResponse:
        """Increase budget ceiling and reset tripped circuit breaker."""
        refueled = self._guardrail.refuel_quota(
            bot_id=req.bot_id,
            additional_tokens=req.additional_tokens,
            additional_cost_usd=req.additional_cost_usd,
            reset_state=req.reset_state,
        )
        return _to_quota_response(refueled)

    def get_quota_status(self, bot_id: str) -> BotQuotaResponse | None:
        """Fetch current quota and watermeter status for a bot."""
        q = self._guardrail.get_quota_status(bot_id)
        if q is None:
            return None
        return _to_quota_response(q)

    def list_quotas(self) -> BotQuotaListResponse:
        """List all active bot budget sandboxes."""
        quotas = self._guardrail.list_all_quotas()
        return BotQuotaListResponse(
            quotas=[_to_quota_response(q) for q in quotas],
            total=len(quotas),
        )

    def reset_all(self) -> None:
        """Reset all registered quotas (used in test isolation)."""
        self._guardrail.reset_all()


_INSTANCE: BotBudgetGuardrailService | None = None


def get_bot_budget_guardrail_service() -> BotBudgetGuardrailService:
    """Return singleton instance of BotBudgetGuardrailService."""
    global _INSTANCE
    if _INSTANCE is None:
        _INSTANCE = BotBudgetGuardrailService()
    return _INSTANCE
