"""Unit tests for FinancialSafetyGuardService."""

from __future__ import annotations

import pytest
from myrm_agent_harness.core.security.financial_safety_guard import (
    FinancialBudgetConfig,
    FinancialSafetyGuard,
)

from app.schemas.financial_safety_guard import (
    BudgetConfigUpdateRequest,
    TransactionIntentRequest,
)
from app.services.security.financial_safety_guard_service import (
    FinancialSafetyGuardService,
)


@pytest.fixture
def service() -> FinancialSafetyGuardService:
    config = FinancialBudgetConfig(
        single_tx_limit_usd=50.0,
        daily_limit_usd=200.0,
        max_allowed_slippage_bps=100,  # 1.0%
        critical_risk_score_threshold=80,
    )
    guard = FinancialSafetyGuard(config=config)
    return FinancialSafetyGuardService(guard=guard)


def test_evaluate_auto_approved(service: FinancialSafetyGuardService) -> None:
    req = TransactionIntentRequest(
        tx_id="tx_server_01",
        source_account="0xuser1",
        target_contract_or_recipient="0xdex_swap",
        asset_symbol="USDT",
        amount=25.0,
        amount_usd=25.0,
        slippage_tolerance_bps=30,
        max_fee_limit=1.5,
    )
    resp = service.evaluate_transaction(req)

    assert resp.decision == "APPROVE"
    assert resp.risk_tier in ("LOW", "MEDIUM")
    assert resp.requires_manual_approval is False
    assert resp.daily_spent_usd == 25.0
    assert resp.remaining_daily_budget_usd == 175.0


def test_evaluate_requires_manual_approval_and_approve(
    service: FinancialSafetyGuardService,
) -> None:
    req = TransactionIntentRequest(
        tx_id="tx_server_02",
        source_account="0xuser1",
        target_contract_or_recipient="0xdex_swap",
        asset_symbol="USDT",
        amount=80.0,  # exceeds single limit 50.0
        amount_usd=80.0,
        slippage_tolerance_bps=30,
        max_fee_limit=2.0,
    )
    resp = service.evaluate_transaction(req)

    assert resp.decision == "ASK_CONFIRMATION"
    assert resp.requires_manual_approval is True
    assert "exceeds auto-approval limit" in (resp.rejection_reason or "")

    # Before manual approval: daily spent not committed
    budget_before = service.get_budget_status()
    assert budget_before.daily_spent_usd == 0.0

    # Execute manual approval
    approved = service.approve_manually("tx_server_02")
    assert approved is not None
    assert approved.decision == "APPROVE"
    assert approved.daily_spent_usd == 80.0

    # Non-existent approval returns None
    assert service.approve_manually("tx_non_existent") is None


def test_evaluate_slippage_breaker_rejection(service: FinancialSafetyGuardService) -> None:
    req = TransactionIntentRequest(
        tx_id="tx_server_03",
        source_account="0xuser1",
        target_contract_or_recipient="0xdex_swap",
        asset_symbol="WBTC",
        amount=3000.0,
        amount_usd=3000.0,  # high volume triggers slippage > 100 bps
        slippage_tolerance_bps=200,
        max_fee_limit=5.0,
    )
    resp = service.evaluate_transaction(req)

    assert resp.decision == "REJECT_BREAKER"
    assert "circuit breaker triggered" in (resp.rejection_reason or "")


def test_budget_config_update_and_reset(service: FinancialSafetyGuardService) -> None:
    update_req = BudgetConfigUpdateRequest(
        single_tx_limit_usd=150.0,
        daily_limit_usd=1000.0,
        max_allowed_slippage_bps=200,
    )
    updated = service.update_budget(update_req)

    assert updated.single_tx_limit_usd == 150.0
    assert updated.daily_limit_usd == 1000.0
    assert updated.max_allowed_slippage_bps == 200

    # Execute a small transaction
    service.evaluate_transaction(
        TransactionIntentRequest(
            tx_id="tx_server_04",
            source_account="0xuser1",
            target_contract_or_recipient="0xvault",
            asset_symbol="DAI",
            amount=50.0,
            amount_usd=50.0,
        )
    )
    assert service.get_budget_status().daily_spent_usd == 50.0

    # Reset
    reset_resp = service.reset_daily_spent()
    assert reset_resp.daily_spent_usd == 0.0
    assert reset_resp.remaining_daily_budget_usd == 1000.0


def test_history_audit_cards(service: FinancialSafetyGuardService) -> None:
    service.evaluate_transaction(
        TransactionIntentRequest(
            tx_id="tx_hist_01",
            source_account="0xuser1",
            target_contract_or_recipient="0xvault",
            asset_symbol="ETH",
            amount=1.0,
            amount_usd=10.0,
        )
    )
    history = service.get_history(limit=5)
    assert len(history) >= 1
    assert history[-1].tx_id == "tx_hist_01"
