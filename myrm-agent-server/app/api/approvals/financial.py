"""REST API for Mandatory Human Sign-Off Gate for Financial and External Outbound Actions.

[POS]
Provides endpoints for:
1. Creating financial or outbound drafts with revealed action surfaces and before-run plans.
2. Reviewing and querying pending sign-offs.
3. Submitting physical human approval/rejection decisions.
4. Binding post-execution delivery receipts to complete the Decision-to-Receipt chain.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Path, Query
from pydantic import BaseModel, Field

from app.schemas.local_action_audit import (
    ActionSurface,
    BeforeRunPlan,
    DeliveryReceipt,
    FinancialSignOffDraft,
)
from app.services.approvals.financial_gate import get_financial_sign_off_gate

router = APIRouter(prefix="/financial", tags=["approvals-financial"])


class CreateSignOffDraftRequest(BaseModel):
    """Payload to initiate a financial or irreversible outbound action draft."""

    agent_id: str = Field(..., description="Agent persona initiating the draft")
    action_surface: ActionSurface = Field(..., description="Transparent parameters and digest")
    plan: BeforeRunPlan = Field(..., description="Before-run risk analysis and execution steps")
    session_id: str | None = Field(None, description="Chat session ID")
    task_id: str | None = Field(None, description="Background task ID")


class SubmitSignOffDecisionRequest(BaseModel):
    """Payload for human operator sign-off decision."""

    operator_id: str = Field(..., description="Identifier of human reviewer approving or rejecting")
    decision: Literal["APPROVE", "REJECT"] = Field(..., description="Sign-off decision")
    rejection_reason: str | None = Field(None, description="Explanation if rejected")


class BindDeliveryReceiptRequest(BaseModel):
    """Payload to record post-execution external result."""

    external_reference_id: str | None = Field(None, description="External transaction ID, message ID, or order ref")
    delivery_status: Literal["DELIVERED", "SETTLED", "FAILED"] = Field(..., description="External execution outcome")
    response_data: str = Field(..., description="Raw response text or JSON for cryptographic digest hashing")


@router.post("/drafts", response_model=FinancialSignOffDraft)
async def create_sign_off_draft(payload: CreateSignOffDraftRequest) -> FinancialSignOffDraft:
    """Create a draft requiring physical human sign-off before actual execution."""
    gate = get_financial_sign_off_gate()
    return await gate.create_draft(
        agent_id=payload.agent_id,
        action_surface=payload.action_surface,
        plan=payload.plan,
        session_id=payload.session_id,
        task_id=payload.task_id,
    )


@router.get("/drafts", response_model=list[FinancialSignOffDraft])
async def list_sign_off_drafts(
    agent_id: str | None = Query(None, description="Filter by drafting agent"),
    status: str | None = Query(None, description="Filter by status (PENDING_SIGNOFF, APPROVED, EXECUTED, etc.)"),
) -> list[FinancialSignOffDraft]:
    """List financial/outbound sign-off drafts in reverse chronological order."""
    gate = get_financial_sign_off_gate()
    return gate.list_drafts(agent_id=agent_id, status=status)


@router.get("/drafts/{draft_id}", response_model=FinancialSignOffDraft)
async def get_sign_off_draft(
    draft_id: str = Path(..., description="Sign-off draft ID"),
) -> FinancialSignOffDraft:
    """Retrieve full details of a specific sign-off draft."""
    gate = get_financial_sign_off_gate()
    draft = gate.get_draft(draft_id)
    if not draft:
        raise HTTPException(status_code=404, detail=f"Draft {draft_id} not found")
    return draft


@router.post("/drafts/{draft_id}/signoff", response_model=FinancialSignOffDraft)
async def submit_sign_off_decision(
    payload: SubmitSignOffDecisionRequest,
    draft_id: str = Path(..., description="Sign-off draft ID"),
) -> FinancialSignOffDraft:
    """Submit human approval or rejection for the action draft."""
    gate = get_financial_sign_off_gate()
    try:
        return await gate.sign_off(
            draft_id=draft_id,
            operator_id=payload.operator_id,
            decision=payload.decision,
            rejection_reason=payload.rejection_reason,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc


@router.post("/drafts/{draft_id}/delivery-receipt", response_model=DeliveryReceipt)
async def bind_delivery_receipt(
    payload: BindDeliveryReceiptRequest,
    draft_id: str = Path(..., description="Sign-off draft ID"),
) -> DeliveryReceipt:
    """Bind post-execution delivery receipt to complete the Decision-to-Receipt chain."""
    gate = get_financial_sign_off_gate()
    try:
        return await gate.bind_delivery_receipt(
            draft_id=draft_id,
            external_reference_id=payload.external_reference_id,
            delivery_status=payload.delivery_status,
            response_data=payload.response_data,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
