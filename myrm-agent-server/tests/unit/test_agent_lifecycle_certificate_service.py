"""
[POS] tests/unit/test_agent_lifecycle_certificate_service.py
[INPUT] app.schemas.agent_lifecycle_certificate, app.services.security.agent_lifecycle_certificate_service
[OUTPUT] unit tests

Tests for AgentLifecycleCertificateService.
Strict typing applied: No `Any` types allowed.
"""

import time

from app.schemas.agent_lifecycle_certificate import (
    CertificateHealthStatusEnum,
    CertificateStatusEnum,
    EmergencyRevocationRequest,
    MintAgentCertificateRequest,
    PreflightVerificationRequest,
    RevocationReasonEnum,
)
from app.services.security.agent_lifecycle_certificate_service import (
    AgentLifecycleCertificateService,
)


def _make_mint_request(agent_id: str = "agent-fin-001") -> MintAgentCertificateRequest:
    return MintAgentCertificateRequest(
        agent_id=agent_id,
        subject_dn=f"CN={agent_id}, O=Enterprise, C=CN",
        validity_days=90,
        attributes={"security_clearance": "HIGH"},
    )


def test_service_mint_and_get_certificate() -> None:
    service = AgentLifecycleCertificateService()
    req = _make_mint_request("agent-sec-101")
    cert = service.mint_certificate(req)

    assert cert.agent_id == "agent-sec-101"
    assert cert.status == CertificateStatusEnum.ACTIVE
    assert len(cert.fingerprint_sha256) == 64
    assert len(cert.signature_hex) == 64
    assert cert.serial_number.startswith("SN-")

    retrieved = service.get_certificate(cert.cert_id)
    assert retrieved is not None
    assert retrieved.cert_id == cert.cert_id


def test_service_verify_preflight_valid_and_missing() -> None:
    service = AgentLifecycleCertificateService()
    req = _make_mint_request("agent-ops-202")
    cert = service.mint_certificate(req)

    # Valid preflight
    verify_req = PreflightVerificationRequest(cert_id=cert.cert_id)
    verdict = service.verify_preflight(verify_req)
    assert verdict.is_allowed is True
    assert verdict.status == CertificateStatusEnum.ACTIVE
    assert verdict.signature_valid is True
    assert verdict.not_expired is True
    assert verdict.not_revoked is True
    assert verdict.issuer_trusted is True

    # Missing preflight
    missing_req = PreflightVerificationRequest(cert_id="non-existent-cert")
    missing_verdict = service.verify_preflight(missing_req)
    assert missing_verdict.is_allowed is False


def test_service_emergency_revoke_and_crl() -> None:
    service = AgentLifecycleCertificateService()
    req = _make_mint_request("agent-rogue-303")
    cert = service.mint_certificate(req)

    # Verify initially passes
    assert service.verify_preflight(PreflightVerificationRequest(cert_id=cert.cert_id)).is_allowed is True

    # Revoke
    revoke_req = EmergencyRevocationRequest(
        cert_id=cert.cert_id,
        reason=RevocationReasonEnum.MALICIOUS_BACKDOOR_DETECTED,
        revoked_by="sec-admin-bob",
    )
    rec = service.emergency_revoke(revoke_req)
    assert rec is not None
    assert rec.cert_id == cert.cert_id
    assert rec.reason == RevocationReasonEnum.MALICIOUS_BACKDOOR_DETECTED

    # Verify blocked after revocation
    blocked_verdict = service.verify_preflight(PreflightVerificationRequest(cert_id=cert.cert_id))
    assert blocked_verdict.is_allowed is False
    assert blocked_verdict.status == CertificateStatusEnum.REVOKED
    assert blocked_verdict.not_revoked is False

    # Check CRL snapshot
    crl = service.get_crl_snapshot()
    assert crl.total_revoked >= 1
    assert any(r.cert_id == cert.cert_id for r in crl.records)


def test_service_health_dashboard() -> None:
    service = AgentLifecycleCertificateService()
    _cert1 = service.mint_certificate(_make_mint_request("agent-h1"))
    cert2 = service.mint_certificate(_make_mint_request("agent-h2"))

    # Revoke cert2
    service.emergency_revoke(
        EmergencyRevocationRequest(
            cert_id=cert2.cert_id,
            reason=RevocationReasonEnum.KEY_COMPROMISE,
        )
    )

    dashboard = service.get_health_dashboard(current_time=time.time())
    assert dashboard.total_certificates == 2
    assert dashboard.healthy_count == 1
    assert dashboard.revoked_count == 1

    revoked_summary = next(s for s in dashboard.summaries if s.cert_id == cert2.cert_id)
    assert revoked_summary.health_status == CertificateHealthStatusEnum.REVOKED
    assert revoked_summary.is_revoked is True
