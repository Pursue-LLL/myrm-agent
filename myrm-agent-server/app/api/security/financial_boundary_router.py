"""API router for Autonomous Bot Asset Security Boundary and Wallet Credential Air-Gap Guard.

[INPUT]
- FinancialTransactionIntentDto, SpendingCeilingPolicyDto, card_id

[OUTPUT]
- JSON endpoints for transaction proposal evaluation, spending policy administration,
  headroom metrics, and two-person confirmation cards.

[POS]
- Server routing layer under `/api/security/financial-boundary`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status
from myrm_agent_harness.core.security.financial_boundary import (
    AirGappedCredentialViolationError,
    FinancialActionBoundaryError,
)

from app.schemas.financial_boundary import (
    DailySpendStatsDto,
    FinancialConfirmationCardDto,
    FinancialTransactionIntentDto,
    SpendingCeilingPolicyDto,
    TransactionEvaluationResponse,
)
from app.services.security.financial_boundary_service import get_financial_boundary_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/financial-boundary", tags=["security-financial-boundary"])


@router.post(
    "/evaluate-intent",
    response_model=TransactionEvaluationResponse,
    summary="Evaluate an asset transaction proposal against security boundaries",
)
def evaluate_intent(intent: FinancialTransactionIntentDto) -> TransactionEvaluationResponse:
    """Check air-gapping, asset whitelist, single-transaction threshold, and daily circuit breaker."""
    service = get_financial_boundary_service()
    try:
        return service.evaluate_intent(intent)
    except AirGappedCredentialViolationError as exc:
        logger.warning("Air-gapped credential violation blocked: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
    except FinancialActionBoundaryError as exc:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail=str(exc),
        ) from exc


@router.get(
    "/policy",
    response_model=SpendingCeilingPolicyDto,
    summary="Get current spending ceiling policy",
)
def get_policy() -> SpendingCeilingPolicyDto:
    """Retrieve active thresholds for autonomous spending and confirmation cards."""
    service = get_financial_boundary_service()
    return service.get_policy()


@router.post(
    "/policy",
    response_model=SpendingCeilingPolicyDto,
    summary="Update spending ceiling policy",
)
def update_policy(policy: SpendingCeilingPolicyDto) -> SpendingCeilingPolicyDto:
    """Update thresholds and whitelisted asset symbols."""
    service = get_financial_boundary_service()
    return service.update_policy(policy)


@router.get(
    "/stats",
    response_model=DailySpendStatsDto,
    summary="Get current daily expenditure metrics and remaining headroom",
)
def get_daily_spend_stats() -> DailySpendStatsDto:
    """Get today's total spend and headroom before the daily circuit breaker trips."""
    service = get_financial_boundary_service()
    return service.get_daily_spend_stats()


@router.get(
    "/confirmation-cards",
    response_model=list[FinancialConfirmationCardDto],
    summary="List interactive asset confirmation cards",
)
def list_confirmation_cards(
    status_filter: str | None = Query(None, alias="status"),
) -> list[FinancialConfirmationCardDto]:
    """List confirmation cards, optionally filtered by status (pending, approved, rejected)."""
    service = get_financial_boundary_service()
    return service.list_cards(status_filter)


@router.post(
    "/confirmation-cards/{card_id}/approve",
    response_model=FinancialConfirmationCardDto,
    summary="Approve an asset confirmation card",
)
def approve_confirmation_card(card_id: str) -> FinancialConfirmationCardDto:
    """Provide human second-party authorization and deduct amount from daily budget."""
    service = get_financial_boundary_service()
    try:
        return service.approve_card(card_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/confirmation-cards/{card_id}/reject",
    response_model=FinancialConfirmationCardDto,
    summary="Reject an asset confirmation card",
)
def reject_confirmation_card(card_id: str) -> FinancialConfirmationCardDto:
    """Reject and revoke authorization for a proposed asset movement."""
    service = get_financial_boundary_service()
    try:
        return service.reject_card(card_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
