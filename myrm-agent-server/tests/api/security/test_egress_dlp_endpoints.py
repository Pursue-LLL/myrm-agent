"""Integration tests for Agent Egress Telemetry Scraper & Enterprise DLP API endpoints."""

from __future__ import annotations

from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.egress_dlp_router import (
    router as egress_dlp_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting egress_dlp_router."""
    test_app = FastAPI(title="Egress DLP Test App")
    test_app.include_router(egress_dlp_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_validate_egress_policy_endpoint(client: TestClient) -> None:
    # 1. Safe rules
    safe_payload = {
        "rules": [
            {"destination": "api.openai.com", "port": 443, "protocol": "tcp"},
            {"destination": "github.com", "port": 443, "protocol": "tcp"},
        ],
        "allowed_exceptions": [],
    }
    resp = client.post("/api/v1/security/egress-dlp/validate-policy", json=safe_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_safe"] is True
    assert data["verdict"] == "ALLOWED"

    # 2. Blocked telemetry domain
    blocked_payload = {
        "rules": [
            {"destination": "app.posthog.com", "port": 443, "protocol": "tcp"},
        ],
        "allowed_exceptions": [],
    }
    resp_blocked = client.post("/api/v1/security/egress-dlp/validate-policy", json=blocked_payload)
    assert resp_blocked.status_code == 200
    blocked_data = resp_blocked.json()
    assert blocked_data["is_safe"] is False
    assert blocked_data["verdict"] == "BLOCKED_TELEMETRY_DOMAIN"
    assert len(blocked_data["detected_signatures"]) >= 1


def test_scan_dependencies_and_signatures_endpoints(client: TestClient) -> None:
    # 1. Dependency scan with telemetry SDK
    dep_payload = {
        "manifest_content": "requests==2.31.0\nsentry-sdk==1.40.0\n",
    }
    resp = client.post("/api/v1/security/egress-dlp/scan-dependencies", json=dep_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_safe"] is False
    assert data["verdict"] == "BLOCKED_TELEMETRY_DEPENDENCY"
    assert "sentry-sdk" in data["detected_dependencies"]

    # 2. Signatures catalog
    sig_resp = client.get("/api/v1/security/egress-dlp/signatures")
    assert sig_resp.status_code == 200
    sigs = sig_resp.json()
    assert len(sigs) >= 5
    assert any(s["target_domain"] == "crewai.com" for s in sigs)


def test_scan_project_endpoint(client: TestClient, tmp_path: Path) -> None:
    proj_dir = tmp_path / "sample_service"
    proj_dir.mkdir()
    code_file = proj_dir / "service.py"
    code_file.write_text("print('clean service')", encoding="utf-8")

    scan_payload = {"project_dir": str(proj_dir)}
    resp = client.post("/api/v1/security/egress-dlp/scan-project", json=scan_payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_safe"] is True
