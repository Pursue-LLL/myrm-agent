"""API endpoints for Three-Tier Stacked Policy Governance and Downgrade Gate.

[INPUT]
- app.schemas.stacked_policy_governance::EvaluatePolicyRequest, InjectSessionRuleRequest
- app.services.security.stacked_policy_governance_service::StackedPolicyGovernanceService

[OUTPUT]
- router: APIRouter for stacked policy governance and downgrade gate

[POS]
Security API surface exposing multi-tier stacked policy evaluation and downgrade status.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from myrm_agent_harness.core.security.stacked_policy_governance import (
    PolicyRule,
)

from app.schemas.stacked_policy_governance import (
    AskCardSchema,
    DowngradeGateStatusResponse,
    EvaluatePolicyRequest,
    EvaluatePolicyResponse,
    InjectSessionRuleRequest,
    RecordUsageAndDowngradeCheckRequest,
)
from app.services.security.stacked_policy_governance_service import (
    StackedPolicyGovernanceService,
    get_stacked_policy_governance_service,
)

router = APIRouter(
    prefix="/stacked-policies",
    tags=["Stacked Policy Governance & Downgrade Gate"],
)


@router.post(
    "/evaluate",
    response_model=EvaluatePolicyResponse,
    summary="Evaluate operation against Session -> Agent -> Server stacked tiers",
)
def evaluate_stacked_policy(
    payload: EvaluatePolicyRequest,
    service: StackedPolicyGovernanceService = Depends(
        get_stacked_policy_governance_service
    ),
) -> EvaluatePolicyResponse:
    """Evaluate candidate operation with short-circuiting across policy tiers."""
    eval_res = service.evaluate(
        phase=payload.phase,
        target=payload.target,
        session_id=payload.session_id,
        agent_id=payload.agent_id,
    )
    card_schema: AskCardSchema | None = None
    if eval_res.ask_card:
        card_schema = AskCardSchema(
            prompt_title=eval_res.ask_card.prompt_title,
            target_operation=eval_res.ask_card.target_operation,
            risk_level=eval_res.ask_card.risk_level,
            recommended_action=eval_res.ask_card.recommended_action,
            context_summary=eval_res.ask_card.context_summary,
        )

    return EvaluatePolicyResponse(
        decision=eval_res.decision,
        matched_tier=eval_res.matched_tier,
        matched_rule=eval_res.matched_rule,
        reason=eval_res.reason,
        requires_approval=eval_res.requires_approval,
        ask_card=card_schema,
    )


@router.post(
    "/inject-session-rule",
    response_model=dict[str, str],
    summary="Dynamically inject user-specified session tier policy rule",
)
def inject_session_policy_rule(
    payload: InjectSessionRuleRequest,
    service: StackedPolicyGovernanceService = Depends(
        get_stacked_policy_governance_service
    ),
) -> dict[str, str]:
    """Inject dynamic session rule taking highest evaluation priority."""
    rule = PolicyRule(
        tier="session",
        name=payload.name,
        phase=payload.phase,
        action=payload.action,
        target_pattern=payload.target_pattern,
        reason=payload.reason,
        session_id=payload.session_id,
    )
    service.add_session_rule(rule)
    return {
        "status": "injected",
        "session_id": payload.session_id,
        "rule_name": payload.name,
    }


@router.post(
    "/record-usage",
    response_model=DowngradeGateStatusResponse,
    summary="Record session consumption and check Tokenomics Downgrade Gate",
)
def record_usage_and_check_gate(
    payload: RecordUsageAndDowngradeCheckRequest,
    service: StackedPolicyGovernanceService = Depends(
        get_stacked_policy_governance_service
    ),
) -> DowngradeGateStatusResponse:
    """Track token/cost delta and evaluate graceful model fallback."""
    status = service.record_usage_and_check(
        session_id=payload.session_id,
        additional_tokens=payload.additional_tokens,
        additional_cost=payload.additional_cost,
    )
    return DowngradeGateStatusResponse(
        session_id=payload.session_id,
        is_downgraded=status.is_downgraded,
        is_hard_blocked=status.is_hard_blocked,
        active_model=status.active_model,
        total_tokens=status.total_tokens,
        total_cost=status.total_cost,
        message=status.message,
    )


@router.get(
    "/downgrade-status",
    response_model=DowngradeGateStatusResponse,
    summary="Get current downgrade gate status for session",
)
def get_session_downgrade_status(
    session_id: str = Query(..., description="Session identifier"),
    service: StackedPolicyGovernanceService = Depends(
        get_stacked_policy_governance_service
    ),
) -> DowngradeGateStatusResponse:
    """Query active model assignment and threshold state for a session."""
    status = service.get_downgrade_status(session_id)
    return DowngradeGateStatusResponse(
        session_id=session_id,
        is_downgraded=status.is_downgraded,
        is_hard_blocked=status.is_hard_blocked,
        active_model=status.active_model,
        total_tokens=status.total_tokens,
        total_cost=status.total_cost,
        message=status.message,
    )


@router.post(
    "/clear-session",
    response_model=dict[str, str],
    summary="Clear dynamic session rules and reset budget counters",
)
def clear_session_policies_and_budget(
    session_id: str = Query(..., description="Session identifier"),
    service: StackedPolicyGovernanceService = Depends(
        get_stacked_policy_governance_service
    ),
) -> dict[str, str]:
    """Clean up rules and counters when session concludes."""
    service.clear_session_rules(session_id)
    service.reset_session_budget(session_id)
    return {
        "status": "cleared",
        "session_id": session_id,
    }
