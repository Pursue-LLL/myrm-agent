"""API endpoints for Scoped Time-Bounded Action Grants and Trust Budgets.

[INPUT]
FastAPI APIRouter, dependencies, action grant schemas, and action grant service.

[OUTPUT]
router: API endpoints exposing creation, evaluation, revocation, and cascading reclamation of action grants.

[POS]
Router for time-bounded action permission grants, evaluation token gates, and agent trust budget lifecycle.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.schemas.action_grants import (
    ActionGrantResponse,
    CascadeReclaimRequest,
    CascadeReclaimResponse,
    CreateActionGrantRequest,
    EvaluateActionGrantRequest,
    EvaluateActionGrantResponse,
    RecordApprovalRequest,
    RecordDemotionRequest,
    RevokeActionGrantRequest,
    TrustBudgetResponse,
)
from app.services.security.action_grant_service import (
    ActionGrantService,
    get_action_grant_service,
)

router = APIRouter(prefix="/grants", tags=["Action Grants & Trust Budget"])


@router.post(
    "/create",
    response_model=ActionGrantResponse,
    summary="Create a 4D scoped action grant for an agent",
)
def create_action_grant(
    payload: CreateActionGrantRequest,
    service: ActionGrantService = Depends(get_action_grant_service),
) -> ActionGrantResponse:
    """Issue a new scoped, time-bounded action grant to prevent approval fatigue."""
    record = service.create_grant(
        agent_id=payload.agent_id,
        service=payload.service,
        action=payload.action,
        transaction=payload.transaction,
        ttl_seconds=payload.ttl_seconds,
        max_uses=payload.max_uses,
    )
    return ActionGrantResponse(
        grant_id=record.grant_id,
        agent_id=record.agent_id,
        service=record.service,
        action=record.action,
        transaction=record.transaction,
        valid_from=record.valid_from,
        expires_at=record.expires_at,
        max_uses=record.max_uses,
        used_count=record.used_count,
        is_revoked=record.is_revoked,
        revocation_reason=record.revocation_reason,
        created_at=record.created_at,
    )


@router.post(
    "/evaluate",
    response_model=EvaluateActionGrantResponse,
    summary="Evaluate if agent action matches an active grant",
)
def evaluate_action_grant(
    payload: EvaluateActionGrantRequest,
    service: ActionGrantService = Depends(get_action_grant_service),
) -> EvaluateActionGrantResponse:
    """Evaluate candidate invocation against active grants."""
    eval_result, _ = service.evaluate_action(
        agent_id=payload.agent_id,
        service=payload.service,
        action=payload.action,
        transaction=payload.transaction,
    )
    return EvaluateActionGrantResponse(
        is_granted=eval_result.is_granted,
        status=eval_result.status,
        grant_id=eval_result.grant_id,
        reason=eval_result.reason,
    )


@router.get(
    "/active",
    response_model=list[ActionGrantResponse],
    summary="List active unrevoked and unexpired grants",
)
def list_active_grants(
    agent_id: str | None = Query(None, description="Filter by agent ID"),
    service_name: str | None = Query(
        None, alias="service", description="Filter by connector service"
    ),
    service: ActionGrantService = Depends(get_action_grant_service),
) -> list[ActionGrantResponse]:
    """Retrieve all active grants matching optional filters."""
    records = service.get_active_grants(agent_id=agent_id, service=service_name)
    return [
        ActionGrantResponse(
            grant_id=r.grant_id,
            agent_id=r.agent_id,
            service=r.service,
            action=r.action,
            transaction=r.transaction,
            valid_from=r.valid_from,
            expires_at=r.expires_at,
            max_uses=r.max_uses,
            used_count=r.used_count,
            is_revoked=r.is_revoked,
            revocation_reason=r.revocation_reason,
            created_at=r.created_at,
        )
        for r in records
    ]


@router.post(
    "/revoke",
    response_model=dict[str, bool],
    summary="Monotonically revoke an individual grant",
)
def revoke_action_grant(
    payload: RevokeActionGrantRequest,
    service: ActionGrantService = Depends(get_action_grant_service),
) -> dict[str, bool]:
    """Revoke grant permanently so it can never be reused."""
    success = service.revoke_grant(
        grant_id=payload.grant_id, reason=payload.reason
    )
    if not success:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="Grant not found or already revoked",
        )
    return {"success": True}


@router.post(
    "/cascade-reclaim",
    response_model=CascadeReclaimResponse,
    summary="Cascade reclaim grants by service or agent",
)
def cascade_reclaim_grants(
    payload: CascadeReclaimRequest,
    service: ActionGrantService = Depends(get_action_grant_service),
) -> CascadeReclaimResponse:
    """Cascade revoke all grants under a service connector or agent."""
    count = service.cascade_reclaim(
        service=payload.service,
        agent_id=payload.agent_id,
        reason=payload.reason,
    )
    return CascadeReclaimResponse(
        revoked_count=count,
        message=f"Cascade revoked {count} action grant(s).",
    )


@router.get(
    "/trust-budget",
    response_model=TrustBudgetResponse,
    summary="Query trust budget status for an agent and action",
)
def get_trust_budget_status(
    agent_id: str = Query(..., description="Agent ID"),
    service_name: str = Query(..., alias="service", description="Service name"),
    action: str = Query(..., description="Action verb"),
    service: ActionGrantService = Depends(get_action_grant_service),
) -> TrustBudgetResponse:
    """Get trust budget and auto-suggestion state."""
    budget = service.get_trust_budget(
        agent_id=agent_id, service=service_name, action=action
    )
    should_suggest = service.should_suggest_grant(
        agent_id=agent_id, service=service_name, action=action
    )
    return TrustBudgetResponse(
        agent_id=budget.agent_id,
        service=budget.service,
        action=budget.action,
        consecutive_approvals=budget.consecutive_approvals,
        is_locked_to_ask=budget.is_locked_to_ask,
        should_suggest_grant=should_suggest,
    )


@router.post(
    "/record-approval",
    response_model=TrustBudgetResponse,
    summary="Record successful uncorrected user approval",
)
def record_user_approval(
    payload: RecordApprovalRequest,
    service: ActionGrantService = Depends(get_action_grant_service),
) -> TrustBudgetResponse:
    """Increment consecutive approval count upon confirmed approval."""
    budget = service.record_approval(
        agent_id=payload.agent_id,
        service=payload.service,
        action=payload.action,
    )
    should_suggest = service.should_suggest_grant(
        agent_id=payload.agent_id,
        service=payload.service,
        action=payload.action,
    )
    return TrustBudgetResponse(
        agent_id=budget.agent_id,
        service=budget.service,
        action=budget.action,
        consecutive_approvals=budget.consecutive_approvals,
        is_locked_to_ask=budget.is_locked_to_ask,
        should_suggest_grant=should_suggest,
    )


@router.post(
    "/record-demotion",
    response_model=TrustBudgetResponse,
    summary="Record correction and immediately collapse trust budget to Ask mode",
)
def record_user_demotion(
    payload: RecordDemotionRequest,
    service: ActionGrantService = Depends(get_action_grant_service),
) -> TrustBudgetResponse:
    """Collapse trust budget to zero and lock back to Ask on correction/undo."""
    budget = service.record_demotion(
        agent_id=payload.agent_id,
        service=payload.service,
        action=payload.action,
        reason=payload.reason,
    )
    return TrustBudgetResponse(
        agent_id=budget.agent_id,
        service=budget.service,
        action=budget.action,
        consecutive_approvals=budget.consecutive_approvals,
        is_locked_to_ask=budget.is_locked_to_ask,
        should_suggest_grant=False,
    )
