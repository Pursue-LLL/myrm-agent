"""Service layer for Autonomous Financial Execution Safety Guard and Simulation Suite.

[INPUT]
- myrm_agent_harness.core.security.financial_safety_guard::FinancialSafetyGuard, FinancialBudgetConfig
- app.schemas.financial_safety_guard::TransactionIntentRequest, ApproveTransactionRequest

[OUTPUT]
- FinancialSafetyGuardService, get_financial_safety_guard_service

[POS]
Business service managing autonomous financial execution safety guard, simulations, and approvals.
"""

from __future__ import annotations

import logging

from myrm_agent_harness.core.security.financial_safety_guard import (
    FinancialBudgetConfig,
    FinancialSafetyGuard,
    TransactionIntent,
    TransactionSecurityCard,
    TransactionSimulationResult,
)

from app.schemas.financial_safety_guard import (
    BudgetConfigUpdateRequest,
    BudgetStatusResponse,
    SimulationResultResponse,
    TransactionIntentRequest,
    TransactionSecurityCardResponse,
)

logger = logging.getLogger(__name__)


def _to_intent_request(intent: TransactionIntent) -> TransactionIntentRequest:
    return TransactionIntentRequest(
        tx_id=intent.tx_id,
        source_account=intent.source_account,
        target_contract_or_recipient=intent.target_contract_or_recipient,
        asset_symbol=intent.asset_symbol,
        amount=intent.amount,
        amount_usd=intent.amount_usd,
        slippage_tolerance_bps=intent.slippage_tolerance_bps,
        max_fee_limit=intent.max_fee_limit,
        payload_digest=intent.payload_digest,
    )


def _to_simulation_response(sim: TransactionSimulationResult) -> SimulationResultResponse:
    return SimulationResultResponse(
        is_simulated=sim.is_simulated,
        estimated_gas_or_fee=sim.estimated_gas_or_fee,
        estimated_slippage_bps=sim.estimated_slippage_bps,
        max_loss_usd=sim.max_loss_usd,
        risk_score=sim.risk_score,
        simulation_notes=sim.simulation_notes,
    )


def _to_card_response(card: TransactionSecurityCard) -> TransactionSecurityCardResponse:
    return TransactionSecurityCardResponse(
        tx_id=card.tx_id,
        decision=card.decision.value,
        risk_tier=card.risk_tier.value,
        intent=_to_intent_request(card.intent),
        simulation=_to_simulation_response(card.simulation),
        daily_spent_usd=card.daily_spent_usd,
        remaining_daily_budget_usd=card.remaining_daily_budget_usd,
        requires_manual_approval=card.requires_manual_approval,
        rejection_reason=card.rejection_reason,
        created_at=card.created_at,
    )


class FinancialSafetyGuardService:
    """Manages transaction simulation, strict budget governance, and circuit breaker policies."""

    def __init__(self, guard: FinancialSafetyGuard | None = None) -> None:
        self._guard = guard or FinancialSafetyGuard()

    @property
    def guard(self) -> FinancialSafetyGuard:
        return self._guard

    def evaluate_transaction(self, req: TransactionIntentRequest) -> TransactionSecurityCardResponse:
        """Run pre-flight dry-run simulation and evaluate financial safety criteria."""
        intent = TransactionIntent(
            tx_id=req.tx_id,
            source_account=req.source_account,
            target_contract_or_recipient=req.target_contract_or_recipient,
            asset_symbol=req.asset_symbol,
            amount=req.amount,
            amount_usd=req.amount_usd,
            slippage_tolerance_bps=req.slippage_tolerance_bps,
            max_fee_limit=req.max_fee_limit,
            payload_digest=req.payload_digest,
        )
        card = self._guard.evaluate_transaction(intent)
        logger.info(
            "Evaluated transaction %s: decision=%s, risk=%s, amount_usd=$%.2f",
            card.tx_id,
            card.decision.value,
            card.risk_tier.value,
            card.intent.amount_usd,
        )
        return _to_card_response(card)

    def approve_manually(self, tx_id: str) -> TransactionSecurityCardResponse | None:
        """Authorize a transaction that was held for manual confirmation."""
        approved = self._guard.approve_manually(tx_id)
        if approved is None:
            return None
        logger.info("Manually approved transaction %s, accumulated daily spend: $%.2f", tx_id, approved.daily_spent_usd)
        return _to_card_response(approved)

    def get_budget_status(self) -> BudgetStatusResponse:
        """Retrieve current limits, daily expenditure, and threshold configurations."""
        cfg = self._guard.config
        spent = self._guard.daily_spent_usd
        remaining = max(0.0, cfg.daily_limit_usd - spent)
        return BudgetStatusResponse(
            single_tx_limit_usd=cfg.single_tx_limit_usd,
            daily_limit_usd=cfg.daily_limit_usd,
            daily_spent_usd=spent,
            remaining_daily_budget_usd=remaining,
            max_allowed_slippage_bps=cfg.max_allowed_slippage_bps,
            critical_risk_score_threshold=cfg.critical_risk_score_threshold,
        )

    def update_budget(self, req: BudgetConfigUpdateRequest) -> BudgetStatusResponse:
        """Update transaction spending and circuit breaker thresholds."""
        current = self._guard.config
        new_config = FinancialBudgetConfig(
            single_tx_limit_usd=(
                req.single_tx_limit_usd
                if req.single_tx_limit_usd is not None
                else current.single_tx_limit_usd
            ),
            daily_limit_usd=(
                req.daily_limit_usd
                if req.daily_limit_usd is not None
                else current.daily_limit_usd
            ),
            max_allowed_slippage_bps=(
                req.max_allowed_slippage_bps
                if req.max_allowed_slippage_bps is not None
                else current.max_allowed_slippage_bps
            ),
            critical_risk_score_threshold=(
                req.critical_risk_score_threshold
                if req.critical_risk_score_threshold is not None
                else current.critical_risk_score_threshold
            ),
        )
        self._guard.update_config(new_config)
        return self.get_budget_status()

    def reset_daily_spent(self) -> BudgetStatusResponse:
        """Reset the daily expenditure accumulator counter."""
        self._guard.reset_daily_spent()
        return self.get_budget_status()

    def get_history(self, limit: int = 50) -> list[TransactionSecurityCardResponse]:
        """Fetch audit dossier history of evaluated transaction cards."""
        cards = self._guard.get_history(limit=limit)
        return [_to_card_response(c) for c in cards]


_service_instance: FinancialSafetyGuardService | None = None


def get_financial_safety_guard_service() -> FinancialSafetyGuardService:
    """Singleton provider for FinancialSafetyGuardService."""
    global _service_instance
    if _service_instance is None:
        _service_instance = FinancialSafetyGuardService()
    return _service_instance
