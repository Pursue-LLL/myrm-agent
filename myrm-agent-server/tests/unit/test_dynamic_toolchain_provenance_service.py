"""
Unit tests for DynamicToolchainProvenanceService.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import hashlib
import hmac

from app.schemas.dynamic_toolchain_provenance import (
    CheckPermissionRequest,
    EvaluateAndInstallSkillRequest,
    ManagePublisherRequest,
    SandboxConfinementPolicyResponse,
    ScanASTOnlyRequest,
    SkillProvenanceManifestSchema,
    VerifyProvenanceOnlyRequest,
)
from app.services.security.dynamic_toolchain_provenance_service import (
    DynamicToolchainProvenanceService,
)


def _generate_sig(publisher_id: str, sha256_hex: str) -> str:
    salt = b"myrm-provenance-anchor-salt"
    msg = f"{publisher_id}:{sha256_hex}".encode()
    return "sig_v1_" + hmac.new(salt, msg, hashlib.sha256).hexdigest()


def test_service_evaluate_and_install_approved() -> None:
    service = DynamicToolchainProvenanceService()
    code = "def greet(name: str) -> str:\n    return f'Hello, {name}'\n"
    sha = hashlib.sha256(code.encode()).hexdigest()
    sig = _generate_sig("myrm-official", sha)

    req = EvaluateAndInstallSkillRequest(
        source_code=code,
        manifest=SkillProvenanceManifestSchema(
            skill_id="greeter",
            version="1.0.0",
            publisher_id="myrm-official",
            source_sha256=sha,
            signature=sig,
            declared_domains=["api.example.com"],
            declared_paths=["/workspace/logs"],
            declared_env_keys=["GREET_PREFIX"],
        ),
    )

    decision = service.evaluate_and_install_skill(req)
    assert decision.is_installation_approved is True
    assert decision.is_provenance_valid is True
    assert decision.is_ast_clean is True
    assert decision.confinement_policy is not None
    assert decision.confinement_policy.skill_id == "greeter"
    assert "/workspace/logs" in decision.confinement_policy.allowed_paths

    metrics = service.get_metrics()
    assert metrics.installations_approved_total == 1
    assert metrics.confinements_issued_total == 1


def test_service_evaluate_and_install_blocked_by_ast() -> None:
    service = DynamicToolchainProvenanceService()
    bad_code = "import os\ndef exploit():\n    os.system('cat /etc/passwd')\n"
    sha = hashlib.sha256(bad_code.encode()).hexdigest()
    sig = _generate_sig("myrm-official", sha)

    req = EvaluateAndInstallSkillRequest(
        source_code=bad_code,
        manifest=SkillProvenanceManifestSchema(
            skill_id="bad-agent",
            version="1.0.0",
            publisher_id="myrm-official",
            source_sha256=sha,
            signature=sig,
        ),
    )

    decision = service.evaluate_and_install_skill(req)
    assert decision.is_installation_approved is False
    assert decision.is_ast_clean is False
    assert len(decision.ast_findings) >= 1
    assert decision.confinement_policy is None

    metrics = service.get_metrics()
    assert metrics.installations_blocked_total == 1
    assert metrics.ast_violations_detected_total >= 1


def test_service_verify_provenance_only() -> None:
    service = DynamicToolchainProvenanceService()
    code = "x = 42\n"
    sha = hashlib.sha256(code.encode()).hexdigest()
    sig = _generate_sig("myrm-official", sha)

    req = VerifyProvenanceOnlyRequest(
        source_code=code,
        manifest=SkillProvenanceManifestSchema(
            skill_id="simple-const",
            version="1.0.0",
            publisher_id="myrm-official",
            source_sha256=sha,
            signature=sig,
        ),
    )

    res = service.verify_provenance_only(req)
    assert res.provenance_status == "VERIFIED"


def test_service_scan_ast_only() -> None:
    service = DynamicToolchainProvenanceService()
    code_eval = "res = eval('2 + 2')\n"
    res = service.scan_ast_only(ScanASTOnlyRequest(source_code=code_eval, skill_id="eval-tool"))
    assert res.is_clean is False
    assert any(f.violation_type == "DANGEROUS_EXEC" for f in res.findings)


def test_service_publisher_management() -> None:
    service = DynamicToolchainProvenanceService()
    assert service.register_trusted_publisher(ManagePublisherRequest(publisher_id="acme-corp")) is True
    assert service.revoke_trusted_publisher(ManagePublisherRequest(publisher_id="acme-corp")) is True


def test_service_check_permission() -> None:
    service = DynamicToolchainProvenanceService()
    policy = SandboxConfinementPolicyResponse(
        policy_id="confine-123",
        skill_id="test-skill",
        allowed_domains=["api.github.com"],
        allowed_paths=["/workspace/cache"],
        allowed_env_keys=["API_TIMEOUT"],
        is_confined=True,
        created_at=1000.0,
    )

    # Network check
    net_res = service.check_permission(
        CheckPermissionRequest(policy=policy, target_type="network", target_value="api.github.com")
    )
    assert net_res.permitted is True

    # Path check
    path_res = service.check_permission(
        CheckPermissionRequest(policy=policy, target_type="path", target_value="/etc/passwd")
    )
    assert path_res.permitted is False

    # Env check
    env_res = service.check_permission(
        CheckPermissionRequest(policy=policy, target_type="env", target_value="API_TIMEOUT")
    )
    assert env_res.permitted is True
