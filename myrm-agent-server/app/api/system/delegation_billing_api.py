"""
[INPUT]: Delegation usage events, session ID, auth mode, and token consumption metrics.
[OUTPUT]: REST API endpoints for external delegation billing transparency, savings audits, and ledger summaries.
[POS]: myrm-agent/myrm-agent-server/app/api/system/delegation_billing_api.py
"""

from typing import Dict, List, Optional
from fastapi import APIRouter, Query
from pydantic import BaseModel, Field

from myrm_agent_harness.observability.delegation_billing import (
    DelegationAuthMode,
    DelegationBillingSummary,
    DelegationBillingTracker,
    DelegationUsageRecord,
)

router = APIRouter(prefix="/delegation-billing", tags=["delegation-billing"])

_default_tracker = DelegationBillingTracker()


def get_default_delegation_tracker() -> DelegationBillingTracker:
    return _default_tracker


# --- Request & Response Models ---


class RecordDelegationRequest(BaseModel):
    session_id: str = Field(..., description="Parent chat session ID")
    source: str = Field(..., description="Delegation source backend (e.g. delegate:claude, invoke_acp:codex)")
    input_tokens: int = Field(default=0, ge=0)
    output_tokens: int = Field(default=0, ge=0)
    auth_mode: str = Field(default="subscription", description="'subscription' or 'api_key'")
    cost_usd: Optional[float] = Field(default=None, ge=0.0)


class RecordDelegationResponse(BaseModel):
    record_id: str
    session_id: str
    source: str
    total_tokens: int
    auth_mode: str
    billable: bool
    estimated_savings_usd: float
    billed_cost_usd: float


# --- Endpoints ---


@router.post("/record", response_model=RecordDelegationResponse)
def record_delegation_usage(req: RecordDelegationRequest) -> RecordDelegationResponse:
    """Record an external agent delegation usage event, automatically calculating billing divergence and savings."""
    auth_enum = (
        DelegationAuthMode.SUBSCRIPTION
        if req.auth_mode.lower() in ("subscription", "sub")
        else DelegationAuthMode.API_KEY
    )
    tracker = get_default_delegation_tracker()
    rec: DelegationUsageRecord = tracker.record_delegation(
        session_id=req.session_id,
        source=req.source,
        input_tokens=req.input_tokens,
        output_tokens=req.output_tokens,
        auth_mode=auth_enum,
        custom_cost_usd=req.cost_usd,
    )
    return RecordDelegationResponse(
        record_id=rec.record_id,
        session_id=rec.session_id,
        source=rec.source,
        total_tokens=rec.total_tokens,
        auth_mode=rec.auth_mode.value,
        billable=rec.billable,
        estimated_savings_usd=rec.estimated_savings_usd,
        billed_cost_usd=rec.billed_cost_usd,
    )


@router.get("/summary")
def get_delegation_billing_summary() -> Dict[str, object]:
    """Retrieve transparent cross-session aggregation of subscription vs API key delegation usage."""
    tracker = get_default_delegation_tracker()
    summary: DelegationBillingSummary = tracker.get_summary()
    return summary.model_dump()


@router.get("/records")
def get_delegation_records(
    session_id: Optional[str] = Query(default=None, description="Optional session ID filter")
) -> List[Dict[str, object]]:
    """Retrieve individual audit records for verification."""
    tracker = get_default_delegation_tracker()
    records = tracker.get_records(session_id=session_id)
    return [r.model_dump() for r in records]


@router.post("/reset")
def reset_delegation_tracker() -> Dict[str, str]:
    """Reset delegation billing tracker state for isolated test execution."""
    tracker = get_default_delegation_tracker()
    tracker.reset()
    return {"status": "reset"}
