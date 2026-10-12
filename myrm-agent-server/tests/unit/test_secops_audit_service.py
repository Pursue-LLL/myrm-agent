"""Unit tests for SecOpsAuditService in server layer.

[POS]
Server unit tests verifying path surface classification, GitHub PR labeling recommendations,
multi-party review requirements, and Skill manifest signing & verification.
"""

from __future__ import annotations

from app.schemas.secops_audit import (
    ScanSurfacesRequest,
    SignSkillManifestRequest,
    VerifySkillRequest,
)
from app.services.security.secops_audit_service import SecOpsAuditService


def test_secops_audit_service_scan_surfaces() -> None:
    service = SecOpsAuditService()

    # Mix of critical surfaces
    request = ScanSurfacesRequest(
        paths=[
            "app/api/auth/jwt.py",
            "skills/code_generator/SKILL.md",
            "frontend/components/Button.tsx",
        ]
    )

    response = service.scan_surfaces(request)
    assert response.total_files_scanned == 3
    assert response.high_risk_detected is True
    assert response.requires_multi_party_review is True
    assert len(response.applied_labels) >= 2
    assert any("sec:auth-change" in lbl for lbl in response.applied_labels)
    assert any("agent:skill-mutation" in lbl for lbl in response.applied_labels)

    # Benign paths
    benign_req = ScanSurfacesRequest(paths=["docs/overview.md", "README.md"])
    benign_res = service.scan_surfaces(benign_req)
    assert benign_res.high_risk_detected is False
    assert benign_res.requires_multi_party_review is False
    assert len(benign_res.applied_labels) == 0


def test_secops_audit_service_sign_and_verify_skill() -> None:
    service = SecOpsAuditService()
    secret = "hmac-secret-test-key-2026"

    skill_content = (
        "# Docker Container Manager\n"
        "Allows agent to run bash docker commands and call external APIs:\n"
        "```bash\n"
        "docker build -t app .\n"
        "```\n"
        "Connects to https://registry.hub.docker.com"
    )

    # 1. Sign
    sign_req = SignSkillManifestRequest(
        skill_name="docker_mgr",
        skill_version="1.0.0",
        content=skill_content,
        secret_key=secret,
        signed_by="devops-sec",
    )
    manifest_dto = service.sign_skill_manifest(sign_req)
    assert manifest_dto.skill_name == "docker_mgr"
    assert "execute_shell" in manifest_dto.declared_permissions
    assert "network_egress" in manifest_dto.declared_permissions

    # 2. Verify valid
    verify_req = VerifySkillRequest(
        skill_name="docker_mgr",
        content=skill_content,
        manifest=manifest_dto,
        secret_key=secret,
    )
    verify_res = service.verify_skill(verify_req)
    assert verify_res.is_valid is True
    assert verify_res.signature_verified is True
    assert len(verify_res.unapproved_permissions) == 0
    # Dangerous permissions trigger user consent requirement
    assert verify_res.requires_user_consent is True

    # 3. Verify tampered
    tampered_content = skill_content + "\nAlso run `cat /etc/passwd`"
    tampered_req = VerifySkillRequest(
        skill_name="docker_mgr",
        content=tampered_content,
        manifest=manifest_dto,
        secret_key=secret,
    )
    tampered_res = service.verify_skill(tampered_req)
    assert tampered_res.is_valid is False
    assert any("Content hash mismatch" in v for v in tampered_res.violations)
