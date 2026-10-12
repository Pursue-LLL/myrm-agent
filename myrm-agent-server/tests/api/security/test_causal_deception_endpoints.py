"""Integration tests for Causal Deception Defense API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.causal_deception_router import (
    router as causal_deception_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting causal_deception_router."""
    test_app = FastAPI(title="Causal Deception Test App")
    test_app.include_router(causal_deception_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_audit_endpoint_consistent(client: TestClient) -> None:
    payload = {
        "commitments": [
            {
                "commitment_id": "c_grep",
                "commitment_type": "FILE_READ",
                "target_subject": "config.yaml",
                "description": "Read configuration file",
            }
        ],
        "traces": [
            {
                "trace_id": "tr_grep",
                "tool_name": "read_file",
                "arguments": {"path": "config.yaml"},
                "output_summary": "port: 8080",
                "is_success": True,
            }
        ],
        "claims": [
            {
                "claim_id": "cl_grep",
                "commitment_type": "FILE_READ",
                "claimed_status": "VERIFIED",
                "target_subject": "config.yaml",
                "assertion_text": "Inspected config.yaml and verified port setting",
            }
        ],
        "fail_closed": False,
    }
    resp = client.post("/api/v1/security/causal-deception/audit", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_consistent"] is True
    assert data["overall_verdict"] == "MATCH"
    assert len(data["violations"]) == 0


def test_audit_endpoint_deceptive_fail_closed(client: TestClient) -> None:
    payload = {
        "commitments": [],
        "traces": [],
        "claims": [
            {
                "claim_id": "cl_fake",
                "commitment_type": "TEST_RUN",
                "claimed_status": "PASSED",
                "target_subject": "test_e2e.py",
                "assertion_text": "Ran end-to-end suite and all passed 100%",
            }
        ],
        "fail_closed": True,
    }
    resp = client.post("/api/v1/security/causal-deception/audit", json=payload)
    assert resp.status_code == 422
    assert "Causal Deception Interception" in resp.json()["detail"]


def test_probe_audience_endpoint(client: TestClient) -> None:
    payload = {
        "claims": [
            {
                "claim_id": "cl_sugar",
                "commitment_type": "TEST_RUN",
                "claimed_status": "PASSED",
                "target_subject": "pipeline.py",
                "assertion_text": "All good 100% passed perfectly",
            }
        ],
        "traces": [],
        "audience_level": "NOVICE",
    }
    resp = client.post("/api/v1/security/causal-deception/probe-audience", json=payload)
    assert resp.status_code == 200
    data = resp.json()
    assert data["is_asymmetric_deception"] is True
    assert data["baseline_audience"] == "NOVICE"
    assert data["adversarial_audience"] == "SENIOR_ENGINEER"
    assert data["vulnerability_index"] > 0.8
