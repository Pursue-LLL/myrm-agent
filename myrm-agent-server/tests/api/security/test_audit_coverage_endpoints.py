"""Integration tests for Security Audit Explicit Coverage & Replayable Repair Bundle API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.audit_coverage_router import (
    router as audit_coverage_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting audit_coverage_router."""
    test_app = FastAPI(title="Audit Coverage Test App")
    test_app.include_router(audit_coverage_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_session_init_and_report_endpoints(client: TestClient) -> None:
    session_payload = {
        "application_model": {
            "name": "AuthService",
            "tech_stack": ["Python", "FastAPI"],
            "entrypoints": ["/login", "/refresh"],
            "trust_boundaries": ["Client -> Gateway"],
            "data_flows": ["User credentials"],
            "supported_finding_categories": ["AUTH_ACCESS_CONTROL", "SECRET_LEAKAGE"],
        },
        "scopes": [
            {
                "category": "AUTH_ACCESS_CONTROL",
                "status": "COVERED",
                "audit_surface": "Audited login endpoints",
                "coverage_percentage": 90.0,
                "uncovered_reason": None,
            }
        ],
    }
    resp = client.post("/api/v1/security/audit-coverage/session", json=session_payload)
    assert resp.status_code == 201
    data = resp.json()
    assert data["application_model"]["name"] == "AuthService"
    assert len(data["scopes"]) == 6

    # Test GET /report endpoint
    report_resp = client.get("/api/v1/security/audit-coverage/report")
    assert report_resp.status_code == 200
    assert report_resp.json()["audit_id"] == data["audit_id"]


def test_record_finding_and_repair_bundle_endpoints(client: TestClient) -> None:
    # 1. Initialize session
    client.post(
        "/api/v1/security/audit-coverage/session",
        json={
            "application_model": {
                "name": "API",
                "tech_stack": ["Python"],
                "entrypoints": ["/api/v1/run"],
                "trust_boundaries": ["Ingress"],
                "data_flows": ["Data"],
                "supported_finding_categories": ["SECRET_LEAKAGE"],
            },
            "scopes": [],
        },
    )

    # 2. Record finding
    finding_payload = {
        "finding": {
            "finding_id": "find_token_leak",
            "category": "SECRET_LEAKAGE",
            "severity": "HIGH",
            "title": "Token leak in logs",
            "description": "Auth token printed to stdout",
            "application_model_ref": "/api/v1/run",
            "evidence": "print(token)",
        },
        "codebase_context": "",
    }
    f_resp = client.post("/api/v1/security/audit-coverage/findings", json=finding_payload)
    assert f_resp.status_code == 201
    assert f_resp.json()["finding_id"] == "find_token_leak"

    # 3. Attach replayable repair bundle
    bundle_payload = {
        "finding_id": "find_token_leak",
        "patches": [
            {
                "file_path": "app/run.py",
                "target_checksum": "sha_orig",
                "diff_content": "- print(token)\n+ logger.info('run')",
                "replay_command": "git apply patch.diff",
            }
        ],
        "replay_script": "pytest",
        "verify_immediately": True,
    }
    b_resp = client.post("/api/v1/security/audit-coverage/repair-bundles", json=bundle_payload)
    assert b_resp.status_code == 201
    b_data = b_resp.json()
    assert b_data["is_verified"] is True
    assert b_data["finding_id"] == "find_token_leak"


def test_unsupported_finding_endpoint_error(client: TestClient) -> None:
    # 1. Initialize session with limited model
    client.post(
        "/api/v1/security/audit-coverage/session",
        json={
            "application_model": {
                "name": "LimitedAPI",
                "tech_stack": ["Python"],
                "entrypoints": ["/"],
                "trust_boundaries": [],
                "data_flows": [],
                "supported_finding_categories": ["AUTH_ACCESS_CONTROL"],
            },
            "scopes": [],
        },
    )

    # 2. Try recording finding outside model category
    finding_payload = {
        "finding": {
            "finding_id": "find_out_of_bounds",
            "category": "INPUT_VALIDATION_INJECTION",  # Unsupported
            "severity": "LOW",
            "title": "SQLi attempt",
            "description": "No SQL in service",
            "application_model_ref": "/",
            "evidence": "SELECT 1",
        }
    }
    resp = client.post("/api/v1/security/audit-coverage/findings", json=finding_payload)
    assert resp.status_code == 422
    assert "outside the supported categories" in resp.json()["detail"]
