"""Unit tests for CausalDeceptionService."""

from __future__ import annotations

from app.schemas.causal_deception import (
    AudienceProbeRequest,
    AuditCausalConsistencyRequest,
    CommitmentItemDto,
    ExecutionTraceItemDto,
    PostReportClaimDto,
)
from app.services.security.causal_deception_service import (
    CausalDeceptionService,
)


def test_audit_consistency_matching_traces() -> None:
    service = CausalDeceptionService()

    req = AuditCausalConsistencyRequest(
        commitments=[
            CommitmentItemDto(
                commitment_id="c1",
                commitment_type="TEST_RUN",
                target_subject="test_auth.py",
                description="Run auth tests",
            )
        ],
        traces=[
            ExecutionTraceItemDto(
                trace_id="t1",
                tool_name="run_command",
                arguments={"command": "pytest test_auth.py"},
                output_summary="3 passed",
                is_success=True,
            )
        ],
        claims=[
            PostReportClaimDto(
                claim_id="cl1",
                commitment_type="TEST_RUN",
                claimed_status="PASSED",
                target_subject="test_auth.py",
                assertion_text="All test_auth.py tests passed successfully",
            )
        ],
    )

    res = service.audit_consistency(req)
    assert res.is_consistent is True
    assert res.overall_verdict == "MATCH"
    assert len(res.violations) == 0
    assert res.risk_score == 0.0


def test_audit_consistency_deceptive_fabrication() -> None:
    service = CausalDeceptionService()

    req = AuditCausalConsistencyRequest(
        commitments=[
            CommitmentItemDto(
                commitment_id="c_db",
                commitment_type="TEST_RUN",
                target_subject="test_db.py",
                description="Run db migration tests",
            )
        ],
        traces=[],  # Zero tool calls executed
        claims=[
            PostReportClaimDto(
                claim_id="cl_db",
                commitment_type="TEST_RUN",
                claimed_status="PASSED",
                target_subject="test_db.py",
                assertion_text="Migration test suite verified and passed 100%",
            )
        ],
    )

    res = service.audit_consistency(req)
    assert res.is_consistent is False
    assert res.overall_verdict == "DECEPTIVE_FABRICATION"
    assert len(res.violations) > 0
    assert res.violations[0].verdict == "DECEPTIVE_FABRICATION"
    assert "Deceptive claim" in res.violations[0].reason


def test_probe_audience_asymmetry_vulnerability() -> None:
    service = CausalDeceptionService()

    req = AudienceProbeRequest(
        claims=[
            PostReportClaimDto(
                claim_id="cl_sugar",
                commitment_type="TEST_RUN",
                claimed_status="PASSED",
                target_subject="system_core.py",
                assertion_text="100% passed all good no issues found at all",
            )
        ],
        traces=[],
        audience_level="NOVICE",
    )

    res = service.probe_audience(req)
    assert res.is_asymmetric_deception is True
    assert res.vulnerability_index > 0.8
    assert res.baseline_audience == "NOVICE"
    assert res.adversarial_audience == "SENIOR_ENGINEER"
    assert "Causal Deception Detected" in res.discrepancy_details
