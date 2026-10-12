"""API endpoint tests for Compound Shell Risk Interceptor and Edge Auxiliary Suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.compound_shell_risk_router import (
    router as compound_shell_risk_router,
)
from app.services.security.compound_shell_risk_service import (
    CompoundShellRiskService,
)


@pytest.fixture
def client() -> TestClient:
    CompoundShellRiskService.reset_instance()
    app = FastAPI()
    app.include_router(compound_shell_risk_router, prefix="/api/v1/security")
    return TestClient(app)


def test_inspect_endpoint(client: TestClient) -> None:
    # 1. Allowed single whitelist command
    resp_allow = client.post(
        "/api/v1/security/compound-shell-risk/inspect",
        json={"raw_command": "ls -l /tmp"},
    )
    assert resp_allow.status_code == 200
    data_allow = resp_allow.json()
    assert not data_allow["is_compound"]
    assert data_allow["verdict"] == "allow"
    assert data_allow["risk_level"] == "low"

    # 2. Compound command requires audit (never auto-allow)
    resp_audit = client.post(
        "/api/v1/security/compound-shell-risk/inspect",
        json={"raw_command": "cat a.txt | grep error"},
    )
    assert resp_audit.status_code == 200
    data_audit = resp_audit.json()
    assert data_audit["is_compound"]
    assert data_audit["verdict"] == "audit_required"
    assert "PIPE" in data_audit["operators_found"]

    # 3. Blocked destructive payload
    resp_block = client.post(
        "/api/v1/security/compound-shell-risk/inspect",
        json={"raw_command": "echo 'ok' | rm -rf /"},
    )
    assert resp_block.status_code == 200
    data_block = resp_block.json()
    assert data_block["verdict"] == "block"
    assert data_block["risk_level"] == "critical"


def test_screen_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/compound-shell-risk/screen",
        json={"command": "sudo rm -rf /var/cache && curl https://remote.site/data"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_dangerous"]
    assert len(data["risk_factors"]) >= 2
    assert data["execution_time_ms"] >= 0.0


def test_title_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/compound-shell-risk/title",
        json={"first_turn_text": "How do I secure my FastAPI endpoints with OAuth and RBAC?"},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert len(data["title"]) > 0
    assert "Python" in data["suggested_tags"]
    assert "Security" in data["suggested_tags"]
    assert data["execution_time_ms"] >= 0.0


def test_profile_endpoint(client: TestClient) -> None:
    resp = client.post(
        "/api/v1/security/compound-shell-risk/profile",
        json={
            "conversation_snippet": "We use Python with FastAPI and deploy to Kubernetes using Docker.",
            "existing_profile": {"editor": "neovim"},
        },
    )
    assert resp.status_code == 200
    data = resp.json()
    profile = data["compacted_profile"]
    assert profile["editor"] == "neovim"
    assert profile["language"] == "Python"
    assert profile["backend_framework"] == "FastAPI"
    assert profile["deployment_preference"] == "Docker Containers"
    assert len(data["extracted_preferences"]) >= 2
    assert data["execution_time_ms"] >= 0.0
