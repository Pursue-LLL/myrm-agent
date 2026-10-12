"""Service for Autonomous Bot Asset Security Boundary and Wallet Credential Air-Gap Guard.

[INPUT]
- FinancialTransactionIntentDto, SpendingCeilingPolicyDto, card_id

[OUTPUT]
- TransactionEvaluationResponse, FinancialConfirmationCardDto, DailySpendStatsDto

[POS]
- Server security service. Wraps harness financial_boundary subsystem for REST API endpoints.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone

from myrm_agent_harness.core.security.financial_boundary import (
    FinancialActionBoundaryGuard,
    FinancialActionType,
    FinancialConfirmationCard,
    FinancialTransactionIntent,
    SpendingCeilingPolicy,
)

from app.schemas.financial_boundary import (
    DailySpendStatsDto,
    FinancialConfirmationCardDto,
    FinancialTransactionIntentDto,
    SpendingCeilingPolicyDto,
    TransactionEvaluationResponse,
)


class FinancialBoundaryService:
    """Singleton service managing asset boundaries, spending ceilings, and confirmation cards."""

    def __init__(self, policy: SpendingCeilingPolicy | None = None) -> None:
        self._guard = FinancialActionBoundaryGuard(policy)
        self._lock = threading.Lock()

    @staticmethod
    def _convert_card_to_dto(card: FinancialConfirmationCard) -> FinancialConfirmationCardDto:
        """Convert domain FinancialConfirmationCard model to DTO."""
        intent_dto = FinancialTransactionIntentDto(
            intent_id=card.intent.intent_id,
            task_id=card.intent.task_id,
            action_type=card.intent.action_type.value,
            asset_symbol=card.intent.asset_symbol,
            amount=card.intent.amount,
            estimated_usd_value=card.intent.estimated_usd_value,
            recipient_address=card.intent.recipient_address,
            justification=card.intent.justification,
        )
        return FinancialConfirmationCardDto(
            card_id=card.card_id,
            intent=intent_dto,
            status=card.status,
            created_at=card.created_at,
            expires_at=card.expires_at,
        )

    def evaluate_intent(self, intent_dto: FinancialTransactionIntentDto) -> TransactionEvaluationResponse:
        """Evaluate asset transaction intent against air-gapping and spending ceilings."""
        action_type = FinancialActionType(intent_dto.action_type)
        domain_intent = FinancialTransactionIntent(
            intent_id=intent_dto.intent_id,
            task_id=intent_dto.task_id,
            action_type=action_type,
            asset_symbol=intent_dto.asset_symbol,
            amount=intent_dto.amount,
            estimated_usd_value=intent_dto.estimated_usd_value,
            recipient_address=intent_dto.recipient_address,
            justification=intent_dto.justification,
        )

        res = self._guard.evaluate_intent(domain_intent)

        return TransactionEvaluationResponse(
            intent_id=res.intent_id,
            permitted_autonomous_execution=res.permitted_autonomous_execution,
            requires_human_confirmation=res.requires_human_confirmation,
            circuit_breaker_triggered=res.circuit_breaker_triggered,
            current_daily_spend_usd=res.current_daily_spend_usd,
            remaining_daily_limit_usd=res.remaining_daily_limit_usd,
            reason=res.reason,
            confirmation_card_id=res.confirmation_card_id,
        )

    def get_policy(self) -> SpendingCeilingPolicyDto:
        """Get active spending ceiling policy."""
        p = self._guard.policy
        return SpendingCeilingPolicyDto(
            daily_ceiling_usd=p.daily_ceiling_usd,
            single_transaction_ceiling_usd=p.single_transaction_ceiling_usd,
            require_two_person_confirmation_above_usd=p.require_two_person_confirmation_above_usd,
            allowed_asset_symbols=sorted(p.allowed_asset_symbols),
        )

    def update_policy(self, policy_dto: SpendingCeilingPolicyDto) -> SpendingCeilingPolicyDto:
        """Update active spending ceiling policy."""
        with self._lock:
            new_policy = SpendingCeilingPolicy(
                daily_ceiling_usd=policy_dto.daily_ceiling_usd,
                single_transaction_ceiling_usd=policy_dto.single_transaction_ceiling_usd,
                require_two_person_confirmation_above_usd=policy_dto.require_two_person_confirmation_above_usd,
                allowed_asset_symbols=frozenset(policy_dto.allowed_asset_symbols),
            )
            self._guard = FinancialActionBoundaryGuard(new_policy)
        return self.get_policy()

    def get_daily_spend_stats(self) -> DailySpendStatsDto:
        """Get current day expenditure and headroom."""
        today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
        current_spend = self._guard.get_current_daily_spend(today)
        remaining = self._guard.get_remaining_daily_limit(today)
        return DailySpendStatsDto(
            date_key=today,
            current_spend_usd=current_spend,
            remaining_limit_usd=remaining,
            daily_ceiling_usd=self._guard.policy.daily_ceiling_usd,
        )

    def approve_card(self, card_id: str) -> FinancialConfirmationCardDto:
        """Approve an asset confirmation card."""
        card = self._guard.approve_card(card_id)
        return self._convert_card_to_dto(card)

    def reject_card(self, card_id: str) -> FinancialConfirmationCardDto:
        """Reject an asset confirmation card."""
        card = self._guard.reject_card(card_id)
        return self._convert_card_to_dto(card)

    def get_card(self, card_id: str) -> FinancialConfirmationCardDto | None:
        """Retrieve confirmation card by ID."""
        card = self._guard.get_card(card_id)
        if not card:
            return None
        return self._convert_card_to_dto(card)

    def list_cards(self, status: str | None = None) -> list[FinancialConfirmationCardDto]:
        """List confirmation cards."""
        cards = self._guard.list_cards(status)
        return [self._convert_card_to_dto(c) for c in cards]


_service_lock = threading.Lock()
_global_financial_boundary_service: FinancialBoundaryService | None = None


def get_financial_boundary_service() -> FinancialBoundaryService:
    """Retrieve or initialize global FinancialBoundaryService singleton."""
    global _global_financial_boundary_service
    if _global_financial_boundary_service is None:
        with _service_lock:
            if _global_financial_boundary_service is None:
                _global_financial_boundary_service = FinancialBoundaryService()
    return _global_financial_boundary_service
