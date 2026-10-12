"""Unit tests for ChangeGuardService.

[INPUT]
- EvaluateChangesRequest payloads.

[OUTPUT]
- Verified behavior of ChangeGuardService layer.

[POS]
- Server unit test layer for ChangeGuard review decision lanes and evidence hardening (#191).
"""

from __future__ import annotations

from app.schemas.change_guard import (
    ChangeGuardExceptionDto,
    EvaluateChangesRequest,
    EvaluateChangesResponse,
    EvidenceRecordDto,
    HardenedFindingDto,
)
from app.services.security.change_guard_service import ChangeGuardService


def test_service_evaluate_clean_changes() -> None:
    service = ChangeGuardService()
    req = EvaluateChangesRequest(findings=[])
    res: EvaluateChangesResponse = service.evaluate_changes(req)

    assert res.overall_outcome == "pass"
    assert res.lane_a.outcome == "pass"
    assert res.lane_b.outcome == "pass"
    assert len(res.lane_a.findings) == 0
    assert len(res.lane_b.findings) == 0
    assert res.highest_change_class == "NO_CHANGE"


def test_service_evaluate_lane_a_block_vs_lane_b_review() -> None:
    service = ChangeGuardService()
    finding_a = HardenedFindingDto(
        finding_id="F-001",
        rule_id="ENV_SECRET_EXPOSURE",
        category="security",
        target_object="config.yaml",
        change_class="HIGH_RISK_CHANGE",
        provenance_class="detected",
        gateability="deterministic",
        evidence=EvidenceRecordDto(
            evidence_type="static-config",
            source_file="config.yaml",
            description="Leaked token",
        ),
        message="Plaintext secret found",
    )
    finding_b = HardenedFindingDto(
        finding_id="F-002",
        rule_id="GOV_AUTONOMY",
        category="governance",
        target_object="workflow.yaml",
        change_class="LOW_CHANGE",
        provenance_class="declared",
        gateability="review-only",
        evidence=EvidenceRecordDto(
            evidence_type="static-config",
            source_file="workflow.yaml",
            description="Autonomous flag enabled",
        ),
        message="Review needed for autonomous mode",
    )

    req = EvaluateChangesRequest(findings=[finding_a, finding_b])
    res = service.evaluate_changes(req)

    assert res.overall_outcome == "block"
    assert res.lane_a.outcome == "block"
    assert len(res.lane_a.findings) == 1
    assert res.lane_b.outcome == "review-required"
    assert len(res.lane_b.findings) == 1
    assert len(res.lane_b.unresolved_questions) == 1


def test_service_review_floor_enforcement() -> None:
    service = ChangeGuardService()
    prompt_finding = HardenedFindingDto(
        finding_id="F-003",
        rule_id="PROMPT_SYSTEM_CHANGE",
        category="prompt",
        target_object="agent/prompts.py",
        change_class="LOW_CHANGE",
        provenance_class="detected",
        gateability="review-only",
        evidence=EvidenceRecordDto(
            evidence_type="diff-inspection",
            source_file="agent/prompts.py",
            description="Prompt altered",
        ),
        message="System prompt instructions modified",
    )

    req = EvaluateChangesRequest(
        findings=[prompt_finding],
        enforce_definition_review_floor=True,
    )
    res = service.evaluate_changes(req)

    assert res.overall_outcome == "review-required"
    assert res.lane_b.outcome == "review-required"
    assert len(res.lane_b.unresolved_questions) >= 1


def test_service_material_change_authority_gate() -> None:
    service = ChangeGuardService()
    finding = HardenedFindingDto(
        finding_id="F-004",
        rule_id="TOOL_SUBPROCESS_ADD",
        category="capabilities",
        target_object="tools/exec.py",
        change_class="MATERIAL_CHANGE",
        provenance_class="detected",
        gateability="deterministic",
        evidence=EvidenceRecordDto(
            evidence_type="diff-inspection",
            source_file="tools/exec.py",
            description="Subprocess added",
        ),
        message="Subprocess capability added",
    )

    req = EvaluateChangesRequest(
        findings=[finding],
        fail_on_authority_change="MATERIAL_CHANGE",
    )
    res = service.evaluate_changes(req)

    assert res.overall_outcome == "block"
    assert res.lane_a.outcome == "block"


def test_service_file_backed_exceptions_lifecycle() -> None:
    service = ChangeGuardService()
    finding = HardenedFindingDto(
        finding_id="F-005",
        rule_id="ENV_SECRET_EXPOSURE",
        category="security",
        target_object="dev.env",
        change_class="HIGH_RISK_CHANGE",
        provenance_class="detected",
        gateability="deterministic",
        evidence=EvidenceRecordDto(
            evidence_type="static-config",
            source_file="dev.env",
            description="Local token",
        ),
        message="Secret in dev env",
    )
    exc = ChangeGuardExceptionDto(
        exception_id="EXC-100",
        finding_or_rule_id="ENV_SECRET_EXPOSURE",
        scope="dev.env",
        risk_owner="lead@sec.org",
        rationale="Dev sandbox token",
        compensating_controls="Isolated VPC",
        expires_at="2026-12-31T00:00:00Z",
    )

    # Valid exception suppresses finding
    req_valid = EvaluateChangesRequest(
        findings=[finding],
        exceptions=[exc],
        current_time_iso="2026-06-01T00:00:00Z",
    )
    res_valid = service.evaluate_changes(req_valid)
    assert res_valid.overall_outcome == "pass"
    assert "EXC-100" in res_valid.applied_exceptions

    # Expired exception cannot suppress finding
    req_expired = EvaluateChangesRequest(
        findings=[finding],
        exceptions=[exc],
        current_time_iso="2027-01-01T00:00:00Z",
    )
    res_expired = service.evaluate_changes(req_expired)
    assert res_expired.overall_outcome == "block"
    assert "EXC-100" in res_expired.stale_or_expired_exceptions


def test_service_config_summary() -> None:
    service = ChangeGuardService()
    summary = service.get_config_summary()
    assert "MATERIAL_CHANGE" in summary.supported_change_classes
    assert "static-config" in summary.supported_evidence_types
    assert "PROMPT_" in summary.definition_prefixes
