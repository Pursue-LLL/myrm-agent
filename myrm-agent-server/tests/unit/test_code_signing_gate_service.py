"""
[POS] tests/unit/test_code_signing_gate_service.py
[INPUT] app.schemas.code_signing_gate, app.services.security.code_signing_gate_service
[OUTPUT] unit tests

Unit tests for CodeSigningGateService.
Strict typing applied: No `Any` types allowed.
"""

import time

from myrm_agent_harness.core.security.code_signing_gate import CodeSignatureVerifier

from app.schemas.code_signing_gate import (
    DeveloperCertificateSchema,
    PackageSignRequest,
    PackageVerificationVerdictEnum,
    PackageVerifyRequest,
    SupplyChainTrustPolicyEnum,
    TrustPolicyUpdateRequest,
)
from app.services.security.code_signing_gate_service import (
    CodeSigningGateService,
)


def test_service_sign_and_verify_package() -> None:
    service = CodeSigningGateService()
    priv_pem, pub_pem = CodeSignatureVerifier.generate_keypair()
    now = time.time()

    cert = DeveloperCertificateSchema(
        developer_id="dev-service-01",
        developer_name="Trust Lab Engineer",
        org_dn="CN=Dev,O=TrustLab,C=CN",
        issuer_ca="GuizhouCA",
        cert_serial="CERT-SRV-1001",
        valid_until=now + 86400.0,
        public_key_pem=pub_pem,
        is_internal_enterprise=True,
    )

    files = {
        "SKILL.md": "# Production Safe Skill",
        "handler.py": "def main(): return 'ok'",
    }

    # 1. Sign package
    sign_req = PackageSignRequest(
        package_id="pkg-srv-01",
        package_name="safe-bot",
        version="1.0.0",
        files=files,
        private_key_pem=priv_pem,
        cert_info=cert,
    )
    signed_pkg = service.sign_package(sign_req)
    assert signed_pkg.package_id == "pkg-srv-01"
    assert len(signed_pkg.manifest_entries) == 2
    assert len(signed_pkg.signature_b64) > 0

    # 2. Verify legitimate package
    verify_req = PackageVerifyRequest(
        package=signed_pkg,
        actual_files=files,
    )
    verify_res = service.verify_package(verify_req)
    assert verify_res.is_allowed is True
    assert verify_res.verdict == PackageVerificationVerdictEnum.VERIFIED
    assert verify_res.verified_developer == "Trust Lab Engineer"
    assert verify_res.is_enterprise_verified is True

    # 3. Detect file tampering
    tampered_files = dict(files)
    tampered_files["handler.py"] = "def main(): import os; os.system('malicious')"
    verify_tampered_req = PackageVerifyRequest(
        package=signed_pkg,
        actual_files=tampered_files,
    )
    verify_tampered_res = service.verify_package(verify_tampered_req)
    assert verify_tampered_res.is_allowed is False
    assert verify_tampered_res.verdict == PackageVerificationVerdictEnum.TAMPERED_MANIFEST_DIGEST


def test_service_trust_policy_and_revocation() -> None:
    service = CodeSigningGateService()
    priv_pem, pub_pem = CodeSignatureVerifier.generate_keypair()
    now = time.time()

    cert_ext = DeveloperCertificateSchema(
        developer_id="dev-srv-ext",
        developer_name="External Contributor",
        org_dn="CN=External,O=OpenCommunity,C=US",
        issuer_ca="DigiCert",
        cert_serial="CERT-EXT-5555",
        valid_until=now + 86400.0,
        public_key_pem=pub_pem,
        is_internal_enterprise=False,
    )

    files = {"SKILL.md": "# Community Tool"}
    sign_req = PackageSignRequest(
        package_id="pkg-ext-01",
        package_name="ext-tool",
        version="0.5.0",
        files=files,
        private_key_pem=priv_pem,
        cert_info=cert_ext,
    )
    signed_pkg = service.sign_package(sign_req)

    # 1. Default VERIFIED_CA_ONLY allows trusted external CA
    verify_res1 = service.verify_package(PackageVerifyRequest(package=signed_pkg, actual_files=files))
    assert verify_res1.is_allowed is True
    assert verify_res1.verdict == PackageVerificationVerdictEnum.VERIFIED

    # 2. Change policy to STRICT_ENTERPRISE_ONLY
    pol_resp = service.set_policy(
        TrustPolicyUpdateRequest(policy=SupplyChainTrustPolicyEnum.STRICT_ENTERPRISE_ONLY)
    )
    assert pol_resp.active_policy == SupplyChainTrustPolicyEnum.STRICT_ENTERPRISE_ONLY
    assert service.get_policy().active_policy == SupplyChainTrustPolicyEnum.STRICT_ENTERPRISE_ONLY

    # 3. External package rejected under STRICT_ENTERPRISE_ONLY
    verify_res2 = service.verify_package(PackageVerifyRequest(package=signed_pkg, actual_files=files))
    assert verify_res2.is_allowed is False
    assert verify_res2.verdict == PackageVerificationVerdictEnum.POLICY_REJECTED

    # 4. Revert to VERIFIED_CA_ONLY and test certificate revocation
    service.set_policy(TrustPolicyUpdateRequest(policy=SupplyChainTrustPolicyEnum.VERIFIED_CA_ONLY))
    service.revoke_certificate("CERT-EXT-5555")

    verify_res3 = service.verify_package(PackageVerifyRequest(package=signed_pkg, actual_files=files))
    assert verify_res3.is_allowed is False
    assert verify_res3.verdict == PackageVerificationVerdictEnum.REVOKED_CERTIFICATE

    # 5. Metrics inspection
    metrics = service.get_metrics()
    assert metrics.total_verifications >= 3
    assert metrics.verified_count >= 1
    assert metrics.blocked_untrusted_count >= 1
