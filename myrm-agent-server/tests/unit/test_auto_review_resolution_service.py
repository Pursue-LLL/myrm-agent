"""
[POS] tests/unit/test_auto_review_resolution_service.py
[INPUT] app.services.security.auto_review_resolution_service, app.schemas.auto_review_resolution
[OUTPUT] Unit tests for AutoReviewResolutionService

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from app.schemas.auto_review_resolution import (
    BranchEvaluationRequest,
    CommitResolutionRequest,
    DenialReasonCodeEnum,
    HandoverStatusEnum,
    ReportDenialRequest,
    ResolutionBranchEnum,
    StageHandoverRequest,
)
from app.services.security.auto_review_resolution_service import (
    AutoReviewResolutionService,
)


def test_service_report_and_get_denial() -> None:
    """Test reporting auto-review denial and retrieving active pending diagnostic."""
    service = AutoReviewResolutionService()
    session_id = "sess-svc-01"

    req = ReportDenialRequest(
        session_id=session_id,
        blocked_action="delete_database_cluster",
        denial_reason="Direct deletion of DB cluster is blocked by high-risk guardrail.",
        reason_code=DenialReasonCodeEnum.HIGH_RISK_ACTION,
        policy_rule_id="RULE-DB-CRIT",
        context_data={"cluster": "prod-db-1"},
    )
    diag = service.report_denial(req)
    assert diag.blocked_action == "delete_database_cluster"
    assert diag.reason_code == DenialReasonCodeEnum.HIGH_RISK_ACTION
    assert diag.suggested_branch == ResolutionBranchEnum.HANDOVER_TO_USER

    # Get active denial
    active = service.get_active_denial(session_id)
    assert active is not None
    assert active.diagnostic_id == diag.diagnostic_id


def test_service_evaluate_branch_and_loop_breaker() -> None:
    """Test branch evaluation and loop breaker diversion after repetitive failures."""
    service = AutoReviewResolutionService(max_isomorphic_attempts=2)
    session_id = "sess-loop-svc"

    req = ReportDenialRequest(
        session_id=session_id,
        blocked_action="modify_system_auth",
        denial_reason="Unauthorized pam configuration modification.",
        reason_code=DenialReasonCodeEnum.UNAUTHORIZED_PATH,
        policy_rule_id="RULE-PAM-01",
    )

    # 1. First block: TRY_ALTERNATIVE allowed
    service.report_denial(req)
    res1 = service.evaluate_branch(
        BranchEvaluationRequest(session_id=session_id, proposed_branch=ResolutionBranchEnum.TRY_ALTERNATIVE)
    )
    assert res1.effective_branch == ResolutionBranchEnum.TRY_ALTERNATIVE
    assert res1.loop_breaker_triggered is False

    # 2. Second block
    service.report_denial(req)
    res2 = service.evaluate_branch(
        BranchEvaluationRequest(session_id=session_id, proposed_branch=ResolutionBranchEnum.TRY_ALTERNATIVE)
    )
    assert res2.effective_branch == ResolutionBranchEnum.TRY_ALTERNATIVE
    assert res2.loop_breaker_triggered is False

    # 3. Third block: threshold exceeded -> loop breaker forces HANDOVER_TO_USER
    service.report_denial(req)
    res3 = service.evaluate_branch(
        BranchEvaluationRequest(session_id=session_id, proposed_branch=ResolutionBranchEnum.TRY_ALTERNATIVE)
    )
    assert res3.effective_branch == ResolutionBranchEnum.HANDOVER_TO_USER
    assert res3.loop_breaker_triggered is True


def test_service_handover_deck_flow() -> None:
    """Test staging, listing, executing, and dismissing human handover cards."""
    service = AutoReviewResolutionService()
    session_id = "sess-deck-svc"

    # Stage card
    deck = service.stage_handover(
        StageHandoverRequest(
            session_id=session_id,
            task_description="Apply Kubernetes ingress rule",
            prepared_command="kubectl apply -f ingress.yaml",
            parameters={"namespace": "prod"},
            guidance_notes="Verify SSL certificate ingress beforehand.",
        )
    )
    assert deck.status == HandoverStatusEnum.STAGED

    # List staged
    staged = service.list_staged_handovers(session_id)
    assert len(staged) == 1
    assert staged[0].handover_id == deck.handover_id

    # Execute card
    exec_deck = service.execute_handover(deck.handover_id)
    assert exec_deck is not None
    assert exec_deck.status == HandoverStatusEnum.EXECUTED_BY_USER
    assert exec_deck.executed_at is not None

    # Staged list now empty
    assert len(service.list_staged_handovers(session_id)) == 0


def test_service_commit_resolution_and_metrics() -> None:
    """Test committing resolution decisions, history retrieval, and telemetry metrics."""
    service = AutoReviewResolutionService()
    session_id = "sess-rec-svc"

    # Report denial first
    service.report_denial(
        ReportDenialRequest(
            session_id=session_id,
            blocked_action="git_push_release",
            denial_reason="Protected release tag write prohibited.",
            reason_code=DenialReasonCodeEnum.POLICY_VIOLATION,
            policy_rule_id="RULE-TAG-01",
        )
    )

    # Commit decision
    rec = service.commit_resolution(
        CommitResolutionRequest(
            session_id=session_id,
            chosen_branch=ResolutionBranchEnum.ASK_USER,
            rationale="Prompting user for release tag elevation.",
        )
    )
    assert rec.chosen_branch == ResolutionBranchEnum.ASK_USER

    # History
    hist = service.get_resolution_history(session_id)
    assert len(hist) == 1
    assert hist[0].chosen_branch == ResolutionBranchEnum.ASK_USER

    # Active denial slot cleared
    assert service.get_active_denial(session_id) is None

    # Metrics
    metrics = service.get_metrics()
    assert metrics.total_denials_processed == 1
    assert metrics.branch_ask_user_count == 1
