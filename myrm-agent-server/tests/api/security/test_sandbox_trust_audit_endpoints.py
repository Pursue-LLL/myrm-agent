"""API endpoint tests for Sandbox Trust Transparency and Security Isolation Audit Card."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.sandbox_trust_audit_router import (
    router as sandbox_trust_audit_router,
)
from app.services.security.sandbox_trust_audit_service import (
    SandboxTrustAuditService,
    get_sandbox_trust_audit_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = SandboxTrustAuditService()
    app = FastAPI()
    app.include_router(sandbox_trust_audit_router, prefix="/api/v1/security")
    app.dependency_overrides[get_sandbox_trust_audit_service] = lambda: test_service
    return TestClient(app)


def test_audit_endpoint(client: TestClient) -> None:
    # 1. Clean audit scan
    resp_clean = client.post(
        "/api/v1/security/sandbox-trust-audit/audit",
        json={
            "environment_id": "env_api_clean",
            "isolation_level": "cloud_dedicated_sandbox",
            "mounted_paths": ["/workspace", "/tmp"],
            "env_vars": {"ENV": "staging"},
            "is_root": False,
            "egress_monitored": True,
        },
    )
    assert resp_clean.status_code == 200
    clean_data = resp_clean.json()
    assert clean_data["passed"] is True
    assert clean_data["score"] == 100
    assert len(clean_data["checks"]) == 4

    # 2. Leaky audit scan
    resp_leaky = client.post(
        "/api/v1/security/sandbox-trust-audit/audit",
        json={
            "environment_id": "env_api_leaky",
            "isolation_level": "local_restricted_container",
            "mounted_paths": ["/workspace", "/var/run/docker.sock"],
            "env_vars": {"AWS_SECRET_ACCESS_KEY": "AKIAIOSFODNN7EXAMPLE"},
            "is_root": True,
            "egress_monitored": False,
        },
    )
    assert resp_leaky.status_code == 200
    leaky_data = resp_leaky.json()
    assert leaky_data["passed"] is False
    assert leaky_data["score"] <= 40


def test_badge_endpoint(client: TestClient) -> None:
    # 1. Valid badge calculation
    resp = client.post(
        "/api/v1/security/sandbox-trust-audit/badge",
        json={
            "isolation_level": "cloud_dedicated_sandbox",
            "audit_score": 100,
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["trust_grade"] == "maximum_isolation"
    assert data["color_hex"] == "#10B981"
    assert "云托管专属沙箱" in data["badge_label"]

    # 2. Invalid isolation level returns 400
    resp_invalid = client.post(
        "/api/v1/security/sandbox-trust-audit/badge",
        json={
            "isolation_level": "non_existent_tier",
            "audit_score": 100,
        },
    )
    assert resp_invalid.status_code == 400


def test_boundary_card_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/sandbox-trust-audit/boundary-card",
        json={
            "environment_id": "env_api_card",
            "isolation_level": "cloud_dedicated_sandbox",
            "allowed_paths": ["/workspace", "/data"],
        },
    )
    assert resp.status_code == 200
    card = resp.json()
    assert card["environment_id"] == "env_api_card"
    assert "/workspace" in card["allowed_paths"]
    assert "~/.ssh" in card["denied_paths"]
    assert len(card["active_guards"]) >= 3
    assert "Sentinel" in card["egress_policy"]
