"""Four-Tier Progressive Spend Control and Soft Quota Intervention Endpoints.

[INPUT]
- app.services.budget.spend_control_service::get_spend_control_engine

[OUTPUT]
- GET /spend-control/decision
- POST /spend-control/confirm-soft-gate
- POST /spend-control/approve-pause
- GET /spend-control/fleet-deck
- POST /spend-control/record-fleet-spend

[POS]
Progressive spend control and soft quota intervention API extension router.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.core.utils.errors import internal_error, validation_error
from app.core.utils.response_utils import success_response
from app.services.budget.spend_control_service import get_spend_control_engine

router = APIRouter()
logger = logging.getLogger(__name__)


class SoftGateConfirmRequest(BaseModel):
    session_id: str
    bypass_token: str


class Tier4ApprovalRequest(BaseModel):
    session_id: str
    approval_token: str


class FleetSpendRecordRequest(BaseModel):
    dimension: str
    identifier: str
    spend_usd: float
    quota_usd: float
    active_sessions: int = 1


@router.get("/decision")
async def get_spend_intervention_decision(
    current_spend_usd: float,
    quota_limit_usd: float,
    session_id: str | None = None,
) -> JSONResponse:
    """Evaluate progressive intervention tier without disruptive hard stoppage."""
    try:
        engine = get_spend_control_engine()
        decision = engine.evaluate(
            current_spend_usd=current_spend_usd,
            quota_limit_usd=quota_limit_usd,
            session_id=session_id,
        )
        return success_response(
            data={
                "tier": decision.tier.value,
                "action": decision.action.value,
                "currentSpendUsd": decision.current_spend_usd,
                "quotaLimitUsd": decision.quota_limit_usd,
                "spendRatio": decision.spend_ratio,
                "message": decision.message,
                "downgradeModelId": decision.downgrade_model_id,
                "bypassToken": decision.bypass_token,
                "approvalToken": decision.approval_token,
                "isBlocked": decision.is_blocked,
                "decisionId": decision.decision_id,
                "createdAt": decision.created_at,
            }
        )
    except Exception as e:
        raise internal_error(operation="Evaluate spend intervention", exception=e) from e


@router.post("/confirm-soft-gate")
async def confirm_soft_gate(req: SoftGateConfirmRequest) -> JSONResponse:
    """Developer self-confirmation to release Tier 2 soft spend gate."""
    try:
        engine = get_spend_control_engine()
        success = engine.confirm_soft_gate(req.session_id, req.bypass_token)
        if not success:
            raise validation_error("Invalid session or bypass token")
        return success_response(data={"confirmed": True, "sessionId": req.session_id})
    except Exception as e:
        raise internal_error(operation="Confirm soft spend gate", exception=e) from e


@router.post("/approve-pause")
async def approve_tier4_pause(req: Tier4ApprovalRequest) -> JSONResponse:
    """Executive administrator approval override for Tier 4 critical pause."""
    try:
        engine = get_spend_control_engine()
        success = engine.approve_tier4_pause(req.session_id, req.approval_token)
        if not success:
            raise validation_error("Invalid session or approval token")
        return success_response(data={"approved": True, "sessionId": req.session_id})
    except Exception as e:
        raise internal_error(operation="Approve Tier 4 spend pause", exception=e) from e


@router.get("/fleet-deck")
async def get_fleet_quota_deck(dimension: str | None = None) -> JSONResponse:
    """Retrieve multi-dimensional quota and spend attribution deck."""
    try:
        engine = get_spend_control_engine()
        items = engine.get_fleet_quota_deck(dimension=dimension)
        return success_response(
            data={
                "items": [
                    {
                        "dimension": it.dimension,
                        "identifier": it.identifier,
                        "spendUsd": it.spend_usd,
                        "allocatedQuotaUsd": it.allocated_quota_usd,
                        "utilizationPct": it.utilization_pct,
                        "tier": it.tier.value,
                        "activeSessions": it.active_sessions,
                        "updatedAt": it.updated_at,
                    }
                    for it in items
                ]
            }
        )
    except Exception as e:
        raise internal_error(operation="Get fleet quota deck", exception=e) from e


@router.post("/record-fleet-spend")
async def record_fleet_spend(req: FleetSpendRecordRequest) -> JSONResponse:
    """Record multi-dimensional spend attribution for an agent, member, or task type."""
    try:
        engine = get_spend_control_engine()
        item = engine.record_fleet_spend(
            dimension=req.dimension,
            identifier=req.identifier,
            spend_usd=req.spend_usd,
            quota_usd=req.quota_usd,
            active_sessions=req.active_sessions,
        )
        return success_response(
            data={
                "dimension": item.dimension,
                "identifier": item.identifier,
                "spendUsd": item.spend_usd,
                "allocatedQuotaUsd": item.allocated_quota_usd,
                "utilizationPct": item.utilization_pct,
                "tier": item.tier.value,
                "activeSessions": item.active_sessions,
                "updatedAt": item.updated_at,
            }
        )
    except Exception as e:
        raise internal_error(operation="Record fleet spend attribution", exception=e) from e
