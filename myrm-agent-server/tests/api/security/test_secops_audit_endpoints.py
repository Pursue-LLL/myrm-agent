"""Integration tests for SecOps Audit and High-Risk Surface CI Gate API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.secops_audit_router import router as secops_audit_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting secops_audit_router."""
    test_app = FastAPI(title="SecOps Audit Test App")
    test_app.include_router(secops_audit_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_scan_surfaces_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/secops/scan-surfaces",
        json={
            "paths": [
                "app/api/security/auth.py",
                "skills/browser/SKILL.md",
                "alembic/versions/002_migration.py",
            ]
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_files_scanned"] == 3
    assert data["high_risk_detected"] is True
    assert data["requires_multi_party_review"] is True
    assert len(data["applied_labels"]) >= 3
    assert len(data["matches"]) >= 3


def test_skills_sign_and_verify_endpoints(client: TestClient) -> None:
    skill_content = (
        "# Security Tool Skill\n"
        "Runs diagnostic scripts:\n"
        "```bash\n"
        "ping -c 3 internal.host\n"
        "```\n"
        "Reports output to user."
    )
    secret_key = "test-authority-key-456"

    # 1. Sign
    sign_resp = client.post(
        "/api/v1/security/secops/skills/sign",
        json={
            "skill_name": "diagnostic_tool",
            "skill_version": "1.0.0",
            "content": skill_content,
            "secret_key": secret_key,
            "signed_by": "secops-bot",
        },
    )
    assert sign_resp.status_code == 201
    manifest = sign_resp.json()
    assert manifest["skill_name"] == "diagnostic_tool"
    assert manifest["signature"] != ""
    assert "execute_shell" in manifest["declared_permissions"]

    # 2. Verify with valid signature
    verify_resp = client.post(
        "/api/v1/security/secops/skills/verify",
        json={
            "skill_name": "diagnostic_tool",
            "content": skill_content,
            "manifest": manifest,
            "secret_key": secret_key,
        },
    )
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["is_valid"] is True
    assert v_data["signature_verified"] is True
    assert len(v_data["violations"]) == 0

    # 3. Verify unsigned skill
    unsigned_resp = client.post(
        "/api/v1/security/secops/skills/verify",
        json={
            "skill_name": "raw_third_party_skill",
            "content": "Just raw prompt instructions.",
        },
    )
    assert unsigned_resp.status_code == 200
    u_data = unsigned_resp.json()
    assert u_data["is_valid"] is False
    assert u_data["signature_verified"] is False
    assert u_data["requires_user_consent"] is True
