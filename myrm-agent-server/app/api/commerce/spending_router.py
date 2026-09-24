"""Autonomous Commerce Spending Limit and Safe Payment API Endpoints.

[INPUT]
- fastapi::APIRouter, Query, HTTPException, status
- pydantic::BaseModel, Field
- app.commerce.budget_service::CommerceBudgetConfigDTO, get_commerce_budget_service
- app.schemas.responses::StandardSuccessResponse, create_success_response

[OUTPUT]
- GET /api/v1/commerce/spending/budget: Real-time budget metrics and active reservations
- PUT /api/v1/commerce/spending/budget: Update spending caps and allowed merchants
- POST /api/v1/commerce/spending/freeze: Emergency circuit breaker freeze/unfreeze
- POST /api/v1/commerce/spending/preauth: Request atomic pre-authorization voucher
- POST /api/v1/commerce/spending/commit: Finalize completed transaction with cryptographic receipt
- POST /api/v1/commerce/spending/release: Abort or refund reservation
- GET /api/v1/commerce/spending/ledger: Fetch tamper-evident audit ledger entries

[POS]
Server-level commerce security API in app/api/commerce/.
Provides safe, constrained micro-payment capabilities for autonomous agent operations.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status
from pydantic import BaseModel, Field

from app.commerce.budget_service import (
    CommerceBudgetConfigDTO,
    CommerceBudgetStatusDTO,
    PreAuthResultDTO,
    get_commerce_budget_service,
)
from app.commerce.spending_ledger import SpendingLedgerEntry
from app.schemas.responses import StandardSuccessResponse, create_success_response

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/commerce/spending", tags=["commerce-spending"])


class FreezeRequest(BaseModel):
    """Request payload to toggle emergency spending freeze."""

    freeze: bool = Field(description="True to freeze, False to unfreeze")


class PreAuthRequest(BaseModel):
    """Request payload for an agent attempting micro-payment pre-authorization."""

    merchant_domain: str = Field(description="Target merchant domain e.g. namesilo.com")
    amount_cents: int = Field(gt=0, description="Amount in integer USD Cents")
    session_id: str = Field(default="global", description="Agent session ID")
    task_id: str | None = Field(default=None, description="Optional task ID")
    idempotency_key: str = Field(default="", description="Optional idempotency key")


class CommitRequest(BaseModel):
    """Request payload to finalize an executed payment."""

    lease_id: str = Field(description="Reserved lease ID")
    idempotency_key: str = Field(default="", description="Idempotency key")


class ReleaseRequest(BaseModel):
    """Request payload to release an unspent reservation."""

    lease_id: str = Field(description="Reserved lease ID")


@router.get("/budget", response_model=StandardSuccessResponse[CommerceBudgetStatusDTO])
async def get_budget_status() -> StandardSuccessResponse[CommerceBudgetStatusDTO]:
    """Retrieve autonomous commerce spending status and current limits."""
    service = get_commerce_budget_service()
    status_dto = service.get_status()
    return create_success_response(status_dto)


@router.put("/budget", response_model=StandardSuccessResponse[CommerceBudgetStatusDTO])
async def update_budget_config(
    payload: CommerceBudgetConfigDTO,
) -> StandardSuccessResponse[CommerceBudgetStatusDTO]:
    """Update spending limits and merchant domain whitelist."""
    service = get_commerce_budget_service()
    updated_status = service.update_config(payload)
    return create_success_response(updated_status)


@router.post("/freeze", response_model=StandardSuccessResponse[CommerceBudgetStatusDTO])
async def set_emergency_freeze(
    payload: FreezeRequest,
) -> StandardSuccessResponse[CommerceBudgetStatusDTO]:
    """Emergency circuit breaker: freeze or unfreeze autonomous micro-payments."""
    service = get_commerce_budget_service()
    status_dto = service.set_freeze(payload.freeze)
    return create_success_response(status_dto)


@router.post("/preauth", response_model=StandardSuccessResponse[PreAuthResultDTO])
async def pre_authorize_spend(
    payload: PreAuthRequest,
) -> StandardSuccessResponse[PreAuthResultDTO]:
    """Request an atomic spend lease and signed voucher before executing payment."""
    service = get_commerce_budget_service()
    res = service.pre_authorize_spend(
        merchant_domain=payload.merchant_domain,
        amount_cents=payload.amount_cents,
        session_id=payload.session_id,
        task_id=payload.task_id,
        idempotency_key=payload.idempotency_key,
    )
    if not res.success:
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail={"code": res.code, "message": res.message},
        )
    return create_success_response(res)


@router.post("/commit", response_model=StandardSuccessResponse[dict[str, object]])
async def commit_spend(
    payload: CommitRequest,
) -> StandardSuccessResponse[dict[str, object]]:
    """Commit executed spend lease and record cryptographic receipt in ledger."""
    service = get_commerce_budget_service()
    res = service.commit_spend(
        lease_id=payload.lease_id,
        idempotency_key=payload.idempotency_key,
    )
    if not res.get("success"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=res,
        )
    return create_success_response(res)


@router.post("/release", response_model=StandardSuccessResponse[dict[str, bool]])
async def release_spend(
    payload: ReleaseRequest,
) -> StandardSuccessResponse[dict[str, bool]]:
    """Release a reserved spend lease if transaction aborted or failed."""
    service = get_commerce_budget_service()
    released = service.release_spend(payload.lease_id)
    return create_success_response({"released": released})


@router.get("/ledger", response_model=StandardSuccessResponse[list[SpendingLedgerEntry]])
async def get_spending_ledger(
    session_id: str | None = Query(default=None, description="Filter by session ID"),
    limit: int = Query(default=50, ge=1, le=200, description="Max records to return"),
) -> StandardSuccessResponse[list[SpendingLedgerEntry]]:
    """Fetch audit ledger entries for autonomous agent expenditures."""
    service = get_commerce_budget_service()
    entries = service.list_ledger_entries(session_id=session_id, limit=limit)
    return create_success_response(entries)
