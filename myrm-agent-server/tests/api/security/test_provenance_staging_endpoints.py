"""Integration tests for Provenance and Staging API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.provenance_staging_router import router as provenance_staging_router


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting provenance_staging_router."""
    test_app = FastAPI(title="Provenance Staging Test App")
    test_app.include_router(provenance_staging_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_provenance_registration_and_check_endpoints(client: TestClient) -> None:
    session_id = "sess_api_01"

    # 1. Register seen entities
    reg_payload = {
        "session_id": session_id,
        "entity_ids": ["prod_alpha", "prod_beta"],
        "entity_type": "product",
        "source_tool": "catalog_search",
    }
    reg_resp = client.post("/api/v1/security/provenance-staging/register-seen", json=reg_payload)
    assert reg_resp.status_code == 200
    assert reg_resp.json()["registered_count"] == 2
    assert reg_resp.json()["total_observed_count"] == 2

    # 2. Check provenance: observed entity -> allowed = True
    check_payload = {
        "session_id": session_id,
        "entity_id": "prod_alpha",
        "tool_name": "add_to_cart",
    }
    check_resp = client.post("/api/v1/security/provenance-staging/check-provenance", json=check_payload)
    assert check_resp.status_code == 200
    assert check_resp.json()["allowed"] is True

    # 3. Check provenance: hallucinated entity -> allowed = False
    unseen_payload = {
        "session_id": session_id,
        "entity_id": "prod_hallucinated",
        "tool_name": "add_to_cart",
    }
    unseen_resp = client.post("/api/v1/security/provenance-staging/check-provenance", json=unseen_payload)
    assert unseen_resp.status_code == 200
    assert unseen_resp.json()["allowed"] is False
    assert "has not been observed" in unseen_resp.json()["reason"]


def test_two_stage_staging_and_token_flow_endpoints(client: TestClient) -> None:
    session_id = "sess_api_02"

    # 1. Stage a mutation
    stage_payload = {
        "session_id": session_id,
        "target_entity_id": "item_999",
        "mutation_type": "update_price",
        "diff_payload": {"price": 19.99},
        "ttl_seconds": 300.0,
    }
    stage_resp = client.post("/api/v1/security/provenance-staging/stage", json=stage_payload)
    assert stage_resp.status_code == 200
    staged_data = stage_resp.json()
    staged_id = staged_data["staged_id"]
    assert staged_data["status"] == "staged"

    # 2. Get staged by ID
    get_resp = client.get(f"/api/v1/security/provenance-staging/staged/{staged_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["staged_id"] == staged_id

    # 3. Issue host approval token
    token_resp = client.post(
        "/api/v1/security/provenance-staging/issue-token",
        json={"staged_id": staged_id, "operator_id": "ops_charlie", "ttl_seconds": 60.0},
    )
    assert token_resp.status_code == 200
    token_data = token_resp.json()

    # 4. Apply with forged token -> 403 Forbidden
    forged_token = dict(token_data)
    forged_token["signature"] = "forged_hex"
    apply_fail_resp = client.post(
        "/api/v1/security/provenance-staging/apply",
        json={"staged_id": staged_id, "token": forged_token},
    )
    assert apply_fail_resp.status_code == 403

    # 5. Apply with authentic token -> 200 OK
    apply_resp = client.post(
        "/api/v1/security/provenance-staging/apply",
        json={"staged_id": staged_id, "token": token_data},
    )
    assert apply_resp.status_code == 200
    assert apply_resp.json()["status"] == "applied"


def test_business_caps_endpoint(client: TestClient) -> None:
    # 1. Compliant caps
    pass_resp = client.post(
        "/api/v1/security/provenance-staging/check-caps",
        json={"discount_percent": 30.0, "affected_rows": 20, "budget_delta": 250.0},
    )
    assert pass_resp.status_code == 200
    assert pass_resp.json()["passed"] is True
    assert len(pass_resp.json()["violations"]) == 0

    # 2. Exceeded caps
    breach_resp = client.post(
        "/api/v1/security/provenance-staging/check-caps",
        json={"discount_percent": 90.0, "affected_rows": 500, "budget_delta": 5000.0},
    )
    assert breach_resp.status_code == 200
    assert breach_resp.json()["passed"] is False
    assert len(breach_resp.json()["violations"]) == 3
