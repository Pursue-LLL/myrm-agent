"""Unit tests for FinancialBoundaryService in server layer.

[POS]
Server unit tests verifying asset transaction evaluation, policy updates,
air-gapped credential protection, and confirmation card workflows.
"""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.financial_boundary import (
    AirGappedCredentialViolationError,
    SpendingCeilingPolicy,
)

from app.schemas.financial_boundary import (
    FinancialTransactionIntentDto,
    SpendingCeilingPolicyDto,
)
from app.services.security.financial_boundary_service import FinancialBoundaryService


def test_financial_boundary_service_micro_transaction() -> None:
    service = FinancialBoundaryService()

    intent = FinancialTransactionIntentDto(
        intent_id="intent_unit_01",
        task_id="task_auto_tx",
        action_type="transfer",
        asset_symbol="USDC",
        amount=3.0,
        estimated_usd_value=3.0,
        recipient_address="0x1234567890123456789012345678901234567890",
        justification="Automated daily fee settlement",
    )

    eval_res = service.evaluate_intent(intent)
    assert eval_res.permitted_autonomous_execution is True
    assert eval_res.requires_human_confirmation is False
    assert eval_res.circuit_breaker_triggered is False


def test_financial_boundary_service_card_escalation_and_approval() -> None:
    service = FinancialBoundaryService(
        SpendingCeilingPolicy(daily_ceiling_usd=100.0, single_transaction_ceiling_usd=5.0)
    )

    intent = FinancialTransactionIntentDto(
        intent_id="intent_unit_02",
        task_id="task_large_tx",
        action_type="swap",
        asset_symbol="ETH",
        amount=0.01,
        estimated_usd_value=25.0,
        recipient_address="0x2222222222222222222222222222222222222222",
        justification="Rebalancing liquidity pool position",
    )

    eval_res = service.evaluate_intent(intent)
    assert eval_res.permitted_autonomous_execution is False
    assert eval_res.requires_human_confirmation is True
    assert eval_res.confirmation_card_id is not None
    card_id = eval_res.confirmation_card_id

    # Check card retrieval
    card_dto = service.get_card(card_id)
    assert card_dto is not None
    assert card_dto.status == "pending"

    # Approve card
    approved_dto = service.approve_card(card_id)
    assert approved_dto.status == "approved"

    # Stats verify spend deduction
    stats = service.get_daily_spend_stats()
    assert stats.current_spend_usd >= 25.0


def test_financial_boundary_service_air_gap_violation() -> None:
    service = FinancialBoundaryService()

    intent_leaked = FinancialTransactionIntentDto(
        intent_id="intent_unit_leak",
        task_id="task_leak",
        action_type="transfer",
        asset_symbol="USDT",
        amount=1.0,
        estimated_usd_value=1.0,
        recipient_address="0x3333333333333333333333333333333333333333",
        justification="Sign using key 0x4c0883a69102937d6231471b5dbb6204fe5129617082792ae468d01a3f36088a directly",
    )

    with pytest.raises(AirGappedCredentialViolationError):
        service.evaluate_intent(intent_leaked)


def test_financial_boundary_service_policy_update() -> None:
    service = FinancialBoundaryService()

    new_policy = SpendingCeilingPolicyDto(
        daily_ceiling_usd=200.0,
        single_transaction_ceiling_usd=10.0,
        require_two_person_confirmation_above_usd=10.0,
        allowed_asset_symbols=["USDC", "SOL"],
    )
    updated = service.update_policy(new_policy)
    assert updated.daily_ceiling_usd == 200.0
    assert updated.single_transaction_ceiling_usd == 10.0
    assert "SOL" in updated.allowed_asset_symbols
