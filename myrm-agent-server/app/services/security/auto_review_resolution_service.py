"""
[POS] app/services/security/auto_review_resolution_service.py
[INPUT] myrm_agent_harness.core.security.auto_review_resolution, app.schemas.auto_review_resolution
[OUTPUT] AutoReviewResolutionService, get_auto_review_resolution_service

Thread-safe service managing structured denial diagnostics, four-way adaptive
resolution state machine, and pre-staged human handover execution cards.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import Optional

from myrm_agent_harness.core.security.auto_review_resolution import (
    AutoReviewResolutionFacade,
)
from myrm_agent_harness.core.security.auto_review_resolution import (
    DenialDiagnosticPayload as HarnessDiag,
)
from myrm_agent_harness.core.security.auto_review_resolution import (
    DenialReasonCodeEnum as HarnessCode,
)
from myrm_agent_harness.core.security.auto_review_resolution import (
    HandoverDeckPayload as HarnessDeck,
)
from myrm_agent_harness.core.security.auto_review_resolution import (
    ResolutionBranchEnum as HarnessBranch,
)
from myrm_agent_harness.core.security.auto_review_resolution import (
    ResolutionDecisionRecord as HarnessRecord,
)

from app.schemas.auto_review_resolution import (
    AutoReviewResolutionMetricsResponse,
    BranchEvaluationRequest,
    BranchEvaluationResponse,
    CommitResolutionRequest,
    DenialDiagnosticResponse,
    DenialReasonCodeEnum,
    HandoverDeckResponse,
    HandoverStatusEnum,
    ReportDenialRequest,
    ResolutionBranchEnum,
    ResolutionDecisionResponse,
    StageHandoverRequest,
)


class AutoReviewResolutionService:
    """Service wrapping denial diagnostics, 4-way adaptive resolution, and handover cards."""

    def __init__(self, max_isomorphic_attempts: int = 2) -> None:
        self._lock = threading.RLock()
        self._facade = AutoReviewResolutionFacade(
            max_isomorphic_attempts=max_isomorphic_attempts
        )

    def report_denial(self, req: ReportDenialRequest) -> DenialDiagnosticResponse:
        """Construct structured denial diagnostic and register in session state machine."""
        code = HarnessCode(req.reason_code.value)
        branch = (
            HarnessBranch(req.custom_suggested_branch.value)
            if req.custom_suggested_branch
            else None
        )

        with self._lock:
            diag = self._facade.report_and_register_denial(
                session_id=req.session_id,
                blocked_action=req.blocked_action,
                denial_reason=req.denial_reason,
                reason_code=code,
                policy_rule_id=req.policy_rule_id,
                context_data=req.context_data,
                custom_alternatives=req.custom_alternatives,
                custom_suggested_branch=branch,
            )
        return self._to_diagnostic_response(diag)

    def get_active_denial(self, session_id: str) -> DenialDiagnosticResponse | None:
        """Retrieve active pending denial diagnostic for a session."""
        with self._lock:
            diag = self._facade.get_active_denial(session_id)
        if diag is None:
            return None
        return self._to_diagnostic_response(diag)

    def evaluate_branch(self, req: BranchEvaluationRequest) -> BranchEvaluationResponse:
        """Evaluate agent's proposed resolution branch against isomorphic loop breaker."""
        proposed = HarnessBranch(req.proposed_branch.value)
        with self._lock:
            effective, explanation = self._facade.evaluate_branch(req.session_id, proposed)

        is_diverted = effective != proposed
        return BranchEvaluationResponse(
            effective_branch=ResolutionBranchEnum(effective.value),
            explanation=explanation,
            loop_breaker_triggered=is_diverted,
        )

    def stage_handover(self, req: StageHandoverRequest) -> HandoverDeckResponse:
        """Pre-stage an interactive human execution card."""
        with self._lock:
            deck = self._facade.stage_handover_deck(
                session_id=req.session_id,
                task_description=req.task_description,
                prepared_command=req.prepared_command,
                parameters=req.parameters,
                guidance_notes=req.guidance_notes,
            )
        return self._to_deck_response(deck)

    def get_handover(self, handover_id: str) -> HandoverDeckResponse | None:
        """Retrieve staged handover deck."""
        with self._lock:
            deck = self._facade.get_handover(handover_id)
        if deck is None:
            return None
        return self._to_deck_response(deck)

    def list_staged_handovers(
        self, session_id: str | None = None
    ) -> list[HandoverDeckResponse]:
        """List active staged handover cards."""
        with self._lock:
            decks = self._facade.list_staged_handovers(session_id)
        return [self._to_deck_response(d) for d in decks]

    def execute_handover(self, handover_id: str) -> HandoverDeckResponse | None:
        """Release and execute pre-staged handover action by human."""
        with self._lock:
            deck = self._facade.execute_handover(handover_id)
        if deck is None:
            return None
        return self._to_deck_response(deck)

    def dismiss_handover(self, handover_id: str) -> HandoverDeckResponse | None:
        """Dismiss or cancel staged handover action."""
        with self._lock:
            deck = self._facade.dismiss_handover(handover_id)
        if deck is None:
            return None
        return self._to_deck_response(deck)

    def commit_resolution(
        self, req: CommitResolutionRequest
    ) -> ResolutionDecisionResponse:
        """Record agent's final decision for current denial."""
        chosen = HarnessBranch(req.chosen_branch.value)
        with self._lock:
            record = self._facade.commit_resolution(
                session_id=req.session_id,
                chosen_branch=chosen,
                rationale=req.rationale,
                alternative_attempted=req.alternative_attempted,
                handover_id=req.handover_id,
            )
        return self._to_record_response(record)

    def get_resolution_history(
        self, session_id: str
    ) -> list[ResolutionDecisionResponse]:
        """Inspect audit trail of past resolution decisions in session."""
        with self._lock:
            history = self._facade.get_resolution_history(session_id)
        return [self._to_record_response(r) for r in history]

    def get_metrics(self) -> AutoReviewResolutionMetricsResponse:
        """Retrieve operational telemetry metrics."""
        with self._lock:
            m = self._facade.get_metrics()
        return AutoReviewResolutionMetricsResponse(
            total_denials_processed=m.total_denials_processed,
            branch_ask_user_count=m.branch_ask_user_count,
            branch_alternative_count=m.branch_alternative_count,
            branch_handover_count=m.branch_handover_count,
            branch_stop_count=m.branch_stop_count,
            handovers_executed_by_user=m.handovers_executed_by_user,
            handovers_dismissed_by_user=m.handovers_dismissed_by_user,
        )

    @staticmethod
    def _to_diagnostic_response(d: HarnessDiag) -> DenialDiagnosticResponse:
        return DenialDiagnosticResponse(
            diagnostic_id=d.diagnostic_id,
            blocked_action=d.blocked_action,
            denial_reason=d.denial_reason,
            reason_code=DenialReasonCodeEnum(d.reason_code.value),
            policy_rule_id=d.policy_rule_id,
            allowed_alternatives=list(d.allowed_alternatives),
            suggested_branch=ResolutionBranchEnum(d.suggested_branch.value),
            context_data=d.context_data,
            timestamp=d.timestamp,
        )

    @staticmethod
    def _to_deck_response(d: HarnessDeck) -> HandoverDeckResponse:
        return HandoverDeckResponse(
            handover_id=d.handover_id,
            session_id=d.session_id,
            task_description=d.task_description,
            prepared_command=d.prepared_command,
            parameters=d.parameters,
            guidance_notes=d.guidance_notes,
            created_at=d.created_at,
            status=HandoverStatusEnum(d.status.value),
            executed_at=d.executed_at,
        )

    @staticmethod
    def _to_record_response(r: HarnessRecord) -> ResolutionDecisionResponse:
        return ResolutionDecisionResponse(
            session_id=r.session_id,
            diagnostic_id=r.diagnostic_id,
            chosen_branch=ResolutionBranchEnum(r.chosen_branch.value),
            decision_rationale=r.decision_rationale,
            timestamp=r.timestamp,
            alternative_attempted=r.alternative_attempted,
            handover_id=r.handover_id,
        )


_SERVICE_INSTANCE: Optional[AutoReviewResolutionService] = None
_SERVICE_LOCK = threading.RLock()


def get_auto_review_resolution_service() -> AutoReviewResolutionService:
    """Get singleton instance of AutoReviewResolutionService."""
    global _SERVICE_INSTANCE
    with _SERVICE_LOCK:
        if _SERVICE_INSTANCE is None:
            _SERVICE_INSTANCE = AutoReviewResolutionService()
        return _SERVICE_INSTANCE
