"""
[POS] app/api/security/agentic_commerce_router.py
[INPUT] app.schemas.agentic_commerce, app.services.security.agentic_commerce_service
[OUTPUT] router

FastAPI router for Autonomous Agent Commerce Protocol & Zero-Knowledge Financial Vault Suite.
Exposes endpoints for payment intent generation, multi-tier spend guardrails, HITL ticket approvals,
and ledger settlements.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.agentic_commerce import (
    BudgetStatusResponse,
    CommerceMetricsResponse,
    ConfirmHITLRequest,
    ConfirmHITLResponse,
    CreatePaymentIntentRequest,
    CreatePaymentIntentResponse,
    DenyHITLRequest,
    DenyHITLResponse,
    PaymentIntentSchema,
    SettlementReceiptSchema,
    SettleTransactionRequest,
    UpdateBudgetPolicyRequest,
)
from app.services.security.agentic_commerce_service import (
    AgenticCommerceService,
    get_agentic_commerce_service,
)

router = APIRouter(
    prefix="/agentic-commerce",
    tags=["Autonomous Agent Commerce & Zero-Knowledge Financial Vault"],
)


@router.post(
    "/intents",
    response_model=CreatePaymentIntentResponse,
    status_code=status.HTTP_200_OK,
    summary="Create structured payment intent and evaluate against budget guardrail",
)
def create_payment_intent(
    request: CreatePaymentIntentRequest,
    service: AgenticCommerceService = Depends(get_agentic_commerce_service),
) -> CreatePaymentIntentResponse:
    """Evaluate payment intent against daily hard caps and auto-approval thresholds."""
    return service.create_payment_intent(request)


@router.post(
    "/hitl/confirm",
    response_model=ConfirmHITLResponse,
    status_code=status.HTTP_200_OK,
    summary="User operator confirms pending HITL transaction and mints single-use token",
)
def confirm_hitl(
    request: ConfirmHITLRequest,
    service: AgenticCommerceService = Depends(get_agentic_commerce_service),
) -> ConfirmHITLResponse:
    """Authorize pending intent and issue ephemeral token from zero-knowledge vault."""
    try:
        return service.confirm_hitl(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending HITL intent '{request.intent_id}' not found.",
        ) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to confirm HITL intent: {err}",
        ) from err


@router.post(
    "/hitl/deny",
    response_model=DenyHITLResponse,
    status_code=status.HTTP_200_OK,
    summary="User operator denies and cancels pending HITL transaction intent",
)
def deny_hitl(
    request: DenyHITLRequest,
    service: AgenticCommerceService = Depends(get_agentic_commerce_service),
) -> DenyHITLResponse:
    """Explicitly reject pending HITL payment intent."""
    try:
        return service.deny_hitl(request)
    except KeyError as err:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Pending HITL intent '{request.intent_id}' not found.",
        ) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Failed to deny HITL intent: {err}",
        ) from err


@router.get(
    "/hitl/pending",
    response_model=list[PaymentIntentSchema],
    summary="List all transaction intents currently pending human operator approval",
)
def list_pending_hitl(
    service: AgenticCommerceService = Depends(get_agentic_commerce_service),
) -> list[PaymentIntentSchema]:
    """Retrieve all queued HITL intents."""
    return service.list_pending_hitl_intents()


@router.post(
    "/settle",
    response_model=SettlementReceiptSchema,
    status_code=status.HTTP_200_OK,
    summary="Settle transaction using single-use ephemeral payment token",
)
def settle_transaction(
    request: SettleTransactionRequest,
    service: AgenticCommerceService = Depends(get_agentic_commerce_service),
) -> SettlementReceiptSchema:
    """Validate token against zero-knowledge vault, consume token, and write ledger receipt."""
    try:
        return service.settle_transaction(request)
    except ValueError as err:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Settlement failed validation: {err}",
        ) from err
    except Exception as err:
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Settlement execution error: {err}",
        ) from err


@router.get(
    "/budget",
    response_model=BudgetStatusResponse,
    summary="Get current daily budget allowance and cumulative spend status",
)
def get_budget_status(
    service: AgenticCommerceService = Depends(get_agentic_commerce_service),
) -> BudgetStatusResponse:
    """Inspect daily budget limits, cumulative spend, and remaining quota."""
    return service.get_budget_status()


@router.put(
    "/budget",
    response_model=BudgetStatusResponse,
    status_code=status.HTTP_200_OK,
    summary="Update financial budget policies and approval thresholds",
)
def update_budget_policy(
    request: UpdateBudgetPolicyRequest,
    service: AgenticCommerceService = Depends(get_agentic_commerce_service),
) -> BudgetStatusResponse:
    """Reconfigure daily hard cap, max transaction, and auto-approval thresholds."""
    return service.update_budget_policy(request)


@router.get(
    "/metrics",
    response_model=CommerceMetricsResponse,
    summary="Get cumulative operational metrics for commerce operations",
)
def get_metrics(
    service: AgenticCommerceService = Depends(get_agentic_commerce_service),
) -> CommerceMetricsResponse:
    """Return metrics counter on intents, approvals, denials, tokens, and spend."""
    return service.get_metrics()
