"""Unit test for HitlFailClosedService.

[INPUT]
- HitlEvaluateExecutionRequest, SecondaryGuardCheckRequest.

[OUTPUT]
- Verified fail-closed gating decisions and secondary invariant guard outcomes.

[POS]
- Server unit test layer for HITL fail-closed safety gate.
"""

from __future__ import annotations

from app.schemas.hitl_fail_closed import (
    HitlEvaluateExecutionRequest,
    SecondaryGuardCheckRequest,
)
from app.services.security.hitl_fail_closed_service import (
    HitlFailClosedService,
)


def test_service_evaluate_channel_disconnected_fail_closed() -> None:
    service = HitlFailClosedService()
    req = HitlEvaluateExecutionRequest(
        tool_name="bash_execute",
        arguments={"command": "ls -la"},
        channel_connected=False,
    )
    res = service.evaluate_execution(req)

    assert res.is_execution_permitted is False
    assert res.approval_decision == "REJECTED_FAIL_CLOSED"
    assert res.fail_closed_reason == "CHANNEL_DISCONNECTED"
    assert "channel (WebSocket/relay) is disconnected" in res.audit_rationale


def test_service_evaluate_timeout_fail_closed() -> None:
    service = HitlFailClosedService()
    req = HitlEvaluateExecutionRequest(
        tool_name="bash_execute",
        arguments={"command": "npm install"},
        simulate_timeout=True,
    )
    res = service.evaluate_execution(req)

    assert res.is_execution_permitted is False
    assert res.approval_decision == "REJECTED_FAIL_CLOSED"
    assert res.fail_closed_reason == "TIMEOUT"


def test_service_evaluate_user_rejected() -> None:
    service = HitlFailClosedService()
    req = HitlEvaluateExecutionRequest(
        tool_name="bash_execute",
        arguments={"command": "npm run build"},
        user_approval=False,
    )
    res = service.evaluate_execution(req)

    assert res.is_execution_permitted is False
    assert res.approval_decision == "REJECTED_USER"
    assert res.fail_closed_reason == "NONE"


def test_service_evaluate_approved_and_guard_blocked() -> None:
    service = HitlFailClosedService()
    req = HitlEvaluateExecutionRequest(
        tool_name="bash_execute",
        arguments={"command": "rm -rf /"},
        user_approval=True,
    )
    res = service.evaluate_execution(req)

    assert res.is_execution_permitted is False
    assert res.approval_decision == "APPROVED"
    assert res.guard_verdict == "BLOCKED_PHYSICAL_INVARIANT"
    assert "Invariant violation" in res.audit_rationale


def test_service_evaluate_approved_and_guard_passed() -> None:
    service = HitlFailClosedService()
    req = HitlEvaluateExecutionRequest(
        tool_name="bash_execute",
        arguments={"command": "pytest tests/unit"},
        user_approval=True,
    )
    res = service.evaluate_execution(req)

    assert res.is_execution_permitted is True
    assert res.approval_decision == "APPROVED"
    assert res.guard_verdict == "PASSED"


def test_service_verify_secondary_guard_direct() -> None:
    service = HitlFailClosedService()

    # Invariant violation
    req_violation = SecondaryGuardCheckRequest(
        tool_name="file_writer",
        arguments={"path": "/etc/shadow", "content": "root:xxx"},
    )
    res_v = service.verify_secondary_guard(req_violation)
    assert res_v.is_permitted is False
    assert res_v.guard_verdict == "BLOCKED_HIGH_RISK_PATTERN"

    # Safe request
    req_safe = SecondaryGuardCheckRequest(
        tool_name="file_writer",
        arguments={"path": "src/app.py", "content": "print('hello')"},
    )
    res_s = service.verify_secondary_guard(req_safe)
    assert res_s.is_permitted is True
    assert res_s.guard_verdict == "PASSED"
