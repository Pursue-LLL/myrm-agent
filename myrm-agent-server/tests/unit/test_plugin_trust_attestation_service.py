"""Unit tests for PluginTrustAttestationService."""

from __future__ import annotations

import pytest

from app.schemas.plugin_trust_attestation import (
    IssueAttestationTokenRequest,
    SignPluginPackageRequest,
    ValidateOperationRequest,
    VerifyPluginPackageRequest,
)
from app.services.security.plugin_trust_attestation_service import (
    PluginTrustAttestationService,
    get_plugin_trust_attestation_service,
)


@pytest.fixture
def service() -> PluginTrustAttestationService:
    return PluginTrustAttestationService()


def test_singleton_getter() -> None:
    svc1 = get_plugin_trust_attestation_service()
    svc2 = get_plugin_trust_attestation_service()
    assert svc1 is svc2


def test_compute_files_digest(service: PluginTrustAttestationService) -> None:
    files = {"plugin.py": "print(1)", "meta.json": "{}"}
    digest = service.compute_files_digest(files)
    assert len(digest) == 64
    assert isinstance(digest, str)


def test_sign_and_verify_package_flow(service: PluginTrustAttestationService) -> None:
    sign_req = SignPluginPackageRequest(
        plugin_id="org.myrm.weather",
        version="1.0.0",
        payload_sha256="abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd",
        trust_tier="OFFICIAL_VERIFIED",
    )
    signed_pkg = service.sign_package(sign_req)
    assert signed_pkg.plugin_id == "org.myrm.weather"
    assert signed_pkg.trust_tier == "OFFICIAL_VERIFIED"
    assert signed_pkg.signature is not None

    # Valid verify
    verify_req = VerifyPluginPackageRequest(
        package=signed_pkg,
        actual_payload_sha256="abc1234567890abcdef1234567890abcdef1234567890abcdef1234567890abcd",
    )
    verify_res = service.verify_package(verify_req)
    assert verify_res.is_valid is True
    assert verify_res.trust_tier == "OFFICIAL_VERIFIED"
    assert verify_res.error_message is None

    # Tampered payload verify
    tampered_verify = VerifyPluginPackageRequest(
        package=signed_pkg,
        actual_payload_sha256="tampered_sha256_hash",
    )
    tampered_res = service.verify_package(tampered_verify)
    assert tampered_res.is_valid is False
    assert "Payload SHA-256 mismatch" in (tampered_res.error_message or "")


def test_issue_token_and_validate_operation(service: PluginTrustAttestationService) -> None:
    token_req = IssueAttestationTokenRequest(
        plugin_id="org.myrm.calc",
        version="1.0.0",
        network_domains=["api.math.org"],
        file_access_scope="WORKSPACE_ONLY",
        allow_shell_exec=False,
        validity_seconds=1200,
    )
    token = service.issue_token(token_req)
    assert token.plugin_id == "org.myrm.calc"
    assert token.allow_shell is False

    # Valid domain operation
    valid_op = ValidateOperationRequest(
        token=token,
        target_domain="api.math.org",
        requires_shell=False,
    )
    valid_res = service.validate_operation(valid_op)
    assert valid_res.allowed is True

    # Unauthorized domain operation
    invalid_domain_op = ValidateOperationRequest(
        token=token,
        target_domain="unauthorized.bad.org",
        requires_shell=False,
    )
    invalid_domain_res = service.validate_operation(invalid_domain_op)
    assert invalid_domain_res.allowed is False

    # Unauthorized shell operation
    invalid_shell_op = ValidateOperationRequest(
        token=token,
        target_domain="api.math.org",
        requires_shell=True,
    )
    invalid_shell_res = service.validate_operation(invalid_shell_op)
    assert invalid_shell_res.allowed is False
