"""Unit tests for SandboxZeroLeakagePiiService."""

from __future__ import annotations

import pytest

from app.schemas.sandbox_zero_leakage_pii import (
    AuditOperatorRequest,
    IssueAttestationRequest,
    ScanPiiRequest,
    SignProfileRequest,
    VerifyAttestationRequest,
    VerifyProfileRequest,
)
from app.services.security.sandbox_zero_leakage_pii_service import (
    SandboxZeroLeakagePiiService,
    get_sandbox_zero_leakage_pii_service,
)


@pytest.fixture
def service() -> SandboxZeroLeakagePiiService:
    return SandboxZeroLeakagePiiService()


def test_singleton_getter() -> None:
    svc1 = get_sandbox_zero_leakage_pii_service()
    svc2 = get_sandbox_zero_leakage_pii_service()
    assert svc1 is svc2


def test_attestation_issue_and_verify_flow(service: SandboxZeroLeakagePiiService) -> None:
    issue_req = IssueAttestationRequest(
        tenant_id="tenant-usr-100",
        container_id="cnt-isolated-4455",
        dedicated_volume_path="/mnt/volumes/user-100",
        dedicated_database_lock="lock-token-abc",
    )
    proof_resp = service.issue_attestation(issue_req)
    assert proof_resp.tenant_id == "tenant-usr-100"
    assert len(proof_resp.attestation_signature) == 64

    # Valid verify
    verify_resp = service.verify_attestation(VerifyAttestationRequest(proof=proof_resp))
    assert verify_resp.is_valid is True
    assert "single-tenant container isolation is intact" in verify_resp.reason


def test_scan_pii_child_and_financial(service: SandboxZeroLeakagePiiService) -> None:
    req = ScanPiiRequest(
        text="My daughter Chloe loves math. Please bill card 4532-1111-2222-3333 at 456 Oak Avenue."
    )
    res = service.scan_pii(req)
    assert res.contains_child_privacy_violation is True
    assert "Chloe" not in res.sanitized_text
    assert "4532-1111-2222-3333" not in res.sanitized_text
    assert "[CHILD_NAME_REDACTED]" in res.sanitized_text
    assert "[FINANCIAL_CARD_REDACTED]" in res.sanitized_text
    assert res.redaction_count >= 2


def test_audit_operator_transparent_vs_blackbox(service: SandboxZeroLeakagePiiService) -> None:
    # 1. Transparent Nous
    t_req = AuditOperatorRequest(
        operator_name="Nous Research",
        base_model_id="Hermes-3-Llama-3.1",
        data_jurisdiction="local",
        is_codebase_public=True,
    )
    t_res = service.audit_operator(t_req)
    assert t_res.tier == "VERIFIED_TRANSPARENT"
    assert t_res.overall_score >= 0.85

    # 2. Blackbox proxy
    b_req = AuditOperatorRequest(
        operator_name="Unknown Shell",
        base_model_id="custom-ai",
        data_jurisdiction="unknown",
        is_codebase_public=False,
    )
    b_res = service.audit_operator(b_req)
    assert b_res.tier == "UNTRUSTED_BLACKBOX"
    assert len(b_res.warnings) >= 3


def test_sign_and_verify_profile_flow(service: SandboxZeroLeakagePiiService) -> None:
    system_prompt = "You are a secure assistant with zero data retention."
    sign_req = SignProfileRequest(
        profile_id="agent-official-1",
        author="Nous",
        model_id="Hermes-3",
        system_prompt=system_prompt,
        is_official=True,
    )
    signed_profile = service.sign_profile(sign_req)
    assert signed_profile.is_official_verified is True

    # Valid verify
    v_req = VerifyProfileRequest(
        profile=signed_profile,
        actual_system_prompt=system_prompt,
    )
    v_res = service.verify_profile(v_req)
    assert v_res.is_valid is True

    # Tampered prompt verify
    tampered_req = VerifyProfileRequest(
        profile=signed_profile,
        actual_system_prompt="Tampered instructions that spy on users.",
    )
    t_res = service.verify_profile(tampered_req)
    assert t_res.is_valid is False
