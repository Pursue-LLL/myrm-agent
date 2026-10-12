"""Service layer for HITL Approval Fail-Closed Safety Gate & Invariant Secondary Guard.

[INPUT]
- HitlEvaluateExecutionRequest, SecondaryGuardCheckRequest DTOs.

[OUTPUT]
- HitlExecutionVerdictDto, SecondaryGuardCheckDto.

[POS]
- Server service wrapping harness HitlApprovalPipeline and NonBypassableSecondaryGuard.
"""

from __future__ import annotations

from collections.abc import Callable

from myrm_agent_harness.core.security.hitl_fail_closed.pipeline import (
    HitlApprovalPipeline,
)
from myrm_agent_harness.core.security.hitl_fail_closed.secondary_guard import (
    NonBypassableSecondaryGuard,
)
from myrm_agent_harness.core.security.hitl_fail_closed.types import (
    SecondaryGuardVerdict,
)

from app.schemas.hitl_fail_closed import (
    HitlEvaluateExecutionRequest,
    HitlExecutionVerdictDto,
    SecondaryGuardCheckDto,
    SecondaryGuardCheckRequest,
)


class HitlFailClosedService:
    """Evaluates human approvals with fail-closed guarantees and secondary invariant guards."""

    def __init__(self, pipeline: HitlApprovalPipeline | None = None) -> None:
        self._pipeline = pipeline or HitlApprovalPipeline()

    def evaluate_execution(
        self, request: HitlEvaluateExecutionRequest
    ) -> HitlExecutionVerdictDto:
        """Evaluate tool execution request through two-phase fail-closed gating."""
        approver_cb: Callable[[], bool] | None = None

        if request.simulate_timeout:
            def _timeout_cb() -> bool:
                raise TimeoutError("Approval communication timed out waiting for human operator.")

            approver_cb = _timeout_cb
        elif request.user_approval is not None:
            user_decision = request.user_approval

            def _decision_cb() -> bool:
                return user_decision

            approver_cb = _decision_cb

        verdict = self._pipeline.evaluate_execution(
            tool_name=request.tool_name,
            arguments=request.arguments,
            approver_callback=approver_cb,
            channel_connected=request.channel_connected,
            is_service_available=request.is_service_available,
        )

        return HitlExecutionVerdictDto(
            tool_name=verdict.tool_name,
            arguments=verdict.arguments,
            approval_decision=verdict.approval_decision.value,
            fail_closed_reason=verdict.fail_closed_reason.value,
            guard_verdict=verdict.guard_verdict.value,
            is_execution_permitted=verdict.is_execution_permitted,
            audit_id=verdict.audit_id,
            audit_rationale=verdict.audit_rationale,
        )

    def verify_secondary_guard(
        self, request: SecondaryGuardCheckRequest
    ) -> SecondaryGuardCheckDto:
        """Inspect non-bypassable secondary invariant guards directly."""
        verdict, rationale = NonBypassableSecondaryGuard.evaluate(
            tool_name=request.tool_name, arguments=request.arguments
        )
        is_permitted = verdict == SecondaryGuardVerdict.PASSED

        return SecondaryGuardCheckDto(
            tool_name=request.tool_name,
            guard_verdict=verdict.value,
            rationale=rationale,
            is_permitted=is_permitted,
        )


_default_service: HitlFailClosedService | None = None


def get_hitl_fail_closed_service() -> HitlFailClosedService:
    """Singleton provider for HitlFailClosedService."""
    global _default_service
    if _default_service is None:
        _default_service = HitlFailClosedService()
    return _default_service
