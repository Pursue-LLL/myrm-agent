"""[INPUT] RegisterRoleFailurePolicyRequest, ReportFailureEventRequest, session_id.
[OUTPUT] FailurePolicyService managing role failure policies, evaluations, and decision history.
[POS] Service layer for Per-Role Subagent Failure Restart & Redeploy Policy (Item 35).
"""

from __future__ import annotations

import logging
import threading
import uuid

from myrm_agent_harness.agent.sub_agents.failure_policy import (
    FailureAction,
    FailureEvent,
    FailureTriggerReason,
    PolicyEvaluationDecision,
    RoleFailurePolicy,
    RoleFailurePolicyEngine,
)

from app.schemas.failure_policy import (
    FailureActionEnum,
    FailureTriggerReasonEnum,
    PolicyEvaluationDecisionDTO,
    PolicyHistoryResponse,
    RegisterRoleFailurePolicyRequest,
    RoleFailurePolicyDTO,
    RolePolicyListResponse,
)

logger = logging.getLogger(__name__)


def _to_policy_dto(p: RoleFailurePolicy) -> RoleFailurePolicyDTO:
    return RoleFailurePolicyDTO(
        role_key=p.role_key,
        primary_action=FailureActionEnum(p.primary_action.value),
        allow_failure=p.allow_failure,
        max_retries=p.max_retries,
        fallback_action=FailureActionEnum(p.fallback_action.value),
        fresh_instructions_template=p.fresh_instructions_template,
        redeploy_model_tier_downgrade=p.redeploy_model_tier_downgrade,
    )


def _to_decision_dto(d: PolicyEvaluationDecision) -> PolicyEvaluationDecisionDTO:
    return PolicyEvaluationDecisionDTO(
        event_id=d.event_id,
        task_id=d.task_id,
        role_key=d.role_key,
        action=FailureActionEnum(d.action.value),
        attempt_number=d.attempt_number,
        max_retries=d.max_retries,
        rationale=d.rationale,
        redeploy_payload=dict(d.redeploy_payload),
        timestamp=d.timestamp,
    )


class FailurePolicyService:
    """Service coordinator managing per-role failure recovery policies and decisions."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._engines: dict[str, RoleFailurePolicyEngine] = {}

    def _get_engine(self, session_id: str) -> RoleFailurePolicyEngine:
        with self._lock:
            engine = self._engines.get(session_id)
            if not engine:
                engine = RoleFailurePolicyEngine()
                self._engines[session_id] = engine
            return engine

    def register_role_policy(
        self,
        session_id: str,
        req: RegisterRoleFailurePolicyRequest,
    ) -> RoleFailurePolicyDTO:
        """Register or update failure recovery policy for a specific role."""
        engine = self._get_engine(session_id)
        policy = RoleFailurePolicy(
            role_key=req.role_key,
            primary_action=FailureAction(req.primary_action.value),
            allow_failure=req.allow_failure,
            max_retries=req.max_retries,
            fallback_action=FailureAction(req.fallback_action.value),
            fresh_instructions_template=req.fresh_instructions_template,
            redeploy_model_tier_downgrade=req.redeploy_model_tier_downgrade,
        )
        engine.register_policy(policy)
        logger.info(
            "Registered failure policy for role '%s' in session '%s'",
            req.role_key,
            session_id,
        )
        return _to_policy_dto(policy)

    def get_role_policy(
        self,
        session_id: str,
        role_key: str,
    ) -> RoleFailurePolicyDTO:
        """Get active failure policy for a role."""
        engine = self._get_engine(session_id)
        policy = engine.get_policy(role_key)
        return _to_policy_dto(policy)

    def list_role_policies(
        self,
        session_id: str,
    ) -> RolePolicyListResponse:
        """List all declared failure policies in the session."""
        engine = self._get_engine(session_id)
        with engine._lock:
            policies = [_to_policy_dto(p) for p in engine._policies.values()]
        return RolePolicyListResponse(policies=policies, total_count=len(policies))

    def report_and_evaluate_failure(
        self,
        session_id: str,
        task_id: str,
        role_key: str,
        trigger_reason: FailureTriggerReasonEnum,
        error_message: str,
        event_id: str | None = None,
    ) -> PolicyEvaluationDecisionDTO:
        """Evaluate mid-task failure and determine autonomous recovery action."""
        engine = self._get_engine(session_id)
        evt = FailureEvent(
            event_id=event_id or f"fevt_{uuid.uuid4().hex[:10]}",
            task_id=task_id,
            role_key=role_key,
            trigger_reason=FailureTriggerReason(trigger_reason.value),
            error_message=error_message,
        )
        decision = engine.evaluate_failure(evt)
        return _to_decision_dto(decision)

    def get_decision_history(
        self,
        session_id: str,
        task_id: str | None = None,
        limit: int = 50,
    ) -> PolicyHistoryResponse:
        """Retrieve failure decision history timeline."""
        engine = self._get_engine(session_id)
        records = engine.get_history(task_id=task_id, limit=limit)
        dtos = [_to_decision_dto(r) for r in records]
        return PolicyHistoryResponse(history=dtos, total_count=len(dtos))

    def reset_task_retry_counter(
        self,
        session_id: str,
        task_id: str,
    ) -> None:
        """Reset retry attempt counter for a task upon manual intervention or resolution."""
        engine = self._get_engine(session_id)
        engine.reset_retry_count(task_id)

    def reset_session(self, session_id: str) -> None:
        """Purge all failure policies and decision state for a session."""
        with self._lock:
            engine = self._engines.pop(session_id, None)
            if engine:
                engine.clear()


# Global singleton instance
_failure_policy_service = FailurePolicyService()


def get_failure_policy_service() -> FailurePolicyService:
    """Get the singleton instance of FailurePolicyService."""
    return _failure_policy_service
