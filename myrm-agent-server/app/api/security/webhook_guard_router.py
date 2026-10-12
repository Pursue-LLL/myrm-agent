"""API router for Untrusted Webhook Prompt Injection Defense and Toolset Demotion.

[INPUT]
- FilterToolsetRequest, EvaluateExecutionRequest, card_id

[OUTPUT]
- JSON endpoints for dynamic toolset filtering, execution evaluation, and admin approval cards.

[POS]
- Server routing layer under `/api/security/webhook-guard`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.webhook_guard import (
    AdminApprovalCardDto,
    EvaluateExecutionRequest,
    EvaluateExecutionResponse,
    FilterToolsetRequest,
    FilterToolsetResponse,
)
from app.services.security.webhook_guard_service import get_webhook_guard_service

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/webhook-guard", tags=["security-webhook-guard"])


@router.post(
    "/filter-toolset",
    response_model=FilterToolsetResponse,
    summary="Filter candidate tools dynamically based on origin taint",
)
def filter_toolset(request: FilterToolsetRequest) -> FilterToolsetResponse:
    """Mask out dangerous execution tools if request or session origin is untrusted."""
    service = get_webhook_guard_service()
    return service.filter_toolset(request)


@router.post(
    "/evaluate-execution",
    response_model=EvaluateExecutionResponse,
    summary="Evaluate if a tool execution is permitted or escalate to admin approval card",
)
def evaluate_execution(request: EvaluateExecutionRequest) -> EvaluateExecutionResponse:
    """Check tool invocation constraints and generate an admin escalation card if dangerous."""
    service = get_webhook_guard_service()
    return service.evaluate_execution(request)


@router.get(
    "/approval-cards",
    response_model=list[AdminApprovalCardDto],
    summary="List all interactive admin approval cards",
)
def list_approval_cards(status_filter: str | None = Query(None, alias="status")) -> list[AdminApprovalCardDto]:
    """List approval cards, optionally filtered by status (pending, approved, rejected, expired)."""
    service = get_webhook_guard_service()
    try:
        return service.list_cards(status_filter)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/approval-cards/{card_id}/approve",
    response_model=AdminApprovalCardDto,
    summary="Approve an interactive admin escalation card",
)
def approve_card(card_id: str) -> AdminApprovalCardDto:
    """Authorize a blocked tool execution for the tainted session."""
    service = get_webhook_guard_service()
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
    "/approval-cards/{card_id}/reject",
    response_model=AdminApprovalCardDto,
    summary="Reject and cancel an interactive admin escalation card",
)
def reject_card(card_id: str) -> AdminApprovalCardDto:
    """Permanently deny authorization for a blocked tool execution."""
    service = get_webhook_guard_service()
    try:
        return service.reject_card(card_id)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
