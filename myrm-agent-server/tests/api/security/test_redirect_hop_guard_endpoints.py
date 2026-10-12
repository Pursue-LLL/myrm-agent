"""Integration tests for Redirect Private Address Hop Revalidation REST endpoints.

[POS] tests/api/security/test_redirect_hop_guard_endpoints.py
[INPUT] app.api.security.redirect_hop_guard_router, app.services.security.redirect_hop_guard_service
[OUTPUT] End-to-end integration tests for hop evaluation, policy updates, and violation logs
Strict typing applied: No `Any` types allowed. Enforced under 400 lines limit.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.redirect_hop_guard_router import (
    get_hop_guard_service,
    redirect_hop_guard_router,
)
from app.services.security.redirect_hop_guard_service import RedirectHopGuardService


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = RedirectHopGuardService()
    app = FastAPI()
    app.include_router(redirect_hop_guard_router, prefix="/api/security")
    app.dependency_overrides[get_hop_guard_service] = lambda: service
    return TestClient(app)


def test_endpoint_evaluate_cloud_metadata_and_private_network(client: TestClient) -> None:
    # 1. AWS/GCP/Azure IMDS check
    resp_metadata = client.post(
        "/api/security/redirect-hop-guard/evaluate",
        json={"target_url": "http://169.254.169.254/latest/meta-data/", "resource_type": "document"},
    )
    assert resp_metadata.status_code == 200
    data_metadata = resp_metadata.json()
    assert data_metadata["is_private"] is True
    assert data_metadata["disposition"] == "ABORT_AND_RESET_DOCUMENT"
    assert "CLOUD_METADATA_IMDS" in data_metadata["matched_rule"]

    # 2. RFC 1918 Private IP check
    resp_private = client.post(
        "/api/security/redirect-hop-guard/evaluate",
        json={"target_url": "http://192.168.1.1/admin", "resource_type": "fetch"},
    )
    assert resp_private.status_code == 200
    data_private = resp_private.json()
    assert data_private["is_private"] is True
    assert data_private["disposition"] == "ABORT_SUBRESOURCE"
    assert "PRIVATE_IPV4" in data_private["matched_rule"]

    # 3. Public target check
    resp_public = client.post(
        "/api/security/redirect-hop-guard/evaluate",
        json={"target_url": "https://example.com/", "resource_type": "document"},
    )
    assert resp_public.status_code == 200
    data_public = resp_public.json()
    assert data_public["is_private"] is False
    assert data_public["disposition"] == "ALLOW"
    assert data_public["matched_rule"] == "PUBLIC_TARGET"


def test_endpoint_policy_lifecycle(client: TestClient) -> None:
    # 1. Get default policy
    resp_get = client.get("/api/security/redirect-hop-guard/policy")
    assert resp_get.status_code == 200
    default_policy = resp_get.json()
    assert default_policy["allow_private_networks"] is False
    assert default_policy["reset_to_about_blank"] is True

    # 2. Update policy
    update_payload = {
        "allow_private_networks": True,
        "reset_to_about_blank": False,
        "audit_history_max_size": 250,
        "custom_blocked_hostnames": ["custom-cloud-metadata.internal"],
    }
    resp_put = client.put("/api/security/redirect-hop-guard/policy", json=update_payload)
    assert resp_put.status_code == 200
    updated_policy = resp_put.json()
    assert updated_policy["allow_private_networks"] is True
    assert updated_policy["reset_to_about_blank"] is False
    assert updated_policy["audit_history_max_size"] == 250
    assert updated_policy["custom_blocked_hostnames"] == ["custom-cloud-metadata.internal"]

    # 3. Verify internal hops are now allowed due to policy override
    resp_eval = client.post(
        "/api/security/redirect-hop-guard/evaluate",
        json={"target_url": "http://10.0.0.1/api", "resource_type": "document"},
    )
    assert resp_eval.status_code == 200
    assert resp_eval.json()["disposition"] == "ALLOW"


def test_endpoint_simulate_and_violations_lifecycle(client: TestClient) -> None:
    # 1. Initial violations list should be empty
    resp_init = client.get("/api/security/redirect-hop-guard/violations")
    assert resp_init.status_code == 200
    assert resp_init.json()["total"] == 0

    # 2. Simulate violation
    sim_payload = {
        "initial_url": "https://attacker.com/start",
        "hop_url": "http://169.254.169.254/latest/meta-data/",
        "resource_type": "document",
    }
    resp_sim = client.post("/api/security/redirect-hop-guard/simulate-violation", json=sim_payload)
    assert resp_sim.status_code == 201
    sim_data = resp_sim.json()
    assert sim_data["initial_url"] == "https://attacker.com/start"
    assert sim_data["hop_url"] == "http://169.254.169.254/latest/meta-data/"
    assert sim_data["disposition"] == "ABORT_AND_RESET_DOCUMENT"

    # 3. Retrieve violations list
    resp_list = client.get("/api/security/redirect-hop-guard/violations")
    assert resp_list.status_code == 200
    list_data = resp_list.json()
    assert list_data["total"] == 1
    assert list_data["violations"][0]["hop_url"] == "http://169.254.169.254/latest/meta-data/"

    # 4. Clear violations list
    resp_del = client.delete("/api/security/redirect-hop-guard/violations")
    assert resp_del.status_code == 204

    # 5. Confirm cleared
    resp_after = client.get("/api/security/redirect-hop-guard/violations")
    assert resp_after.status_code == 200
    assert resp_after.json()["total"] == 0
