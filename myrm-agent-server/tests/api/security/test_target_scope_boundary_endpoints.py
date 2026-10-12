"""
Integration tests for Strict Target Scope Authorization & Egress Boundary REST endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.target_scope_boundary_router import (
    router as target_scope_boundary_router,
)
from app.services.security.target_scope_boundary_service import (
    TargetScopeBoundaryService,
    get_target_scope_boundary_service,
)


@pytest.fixture
def client() -> TestClient:
    service = TargetScopeBoundaryService()
    app = FastAPI()
    app.include_router(target_scope_boundary_router)
    app.dependency_overrides[get_target_scope_boundary_service] = lambda: service
    return TestClient(app)


def test_endpoint_contract_crud(client: TestClient) -> None:
    # 1. Set contract
    set_resp = client.post(
        "/target-scope-boundary/contracts",
        json={
            "contract_id": "roe-test-01",
            "engagement_name": "API Pentest Engagement",
            "authorized_domains": ["*.pentest.target.com"],
            "authorized_cidrs": ["10.0.0.0/8"],
            "prohibited_targets": ["admin.pentest.target.com"],
            "signed_by": "pentest_lead",
            "signature_hash": "sha256_dummy_hash",
            "is_active": True,
        },
    )
    assert set_resp.status_code == 200
    assert set_resp.json()["contract_id"] == "roe-test-01"

    # 2. Get active
    get_resp = client.get("/target-scope-boundary/contracts/active")
    assert get_resp.status_code == 200
    assert get_resp.json() is not None
    assert get_resp.json()["contract_id"] == "roe-test-01"

    # 3. Clear
    del_resp = client.delete("/target-scope-boundary/contracts/active")
    assert del_resp.status_code == 204

    # 4. Verify cleared
    get_cleared = client.get("/target-scope-boundary/contracts/active")
    assert get_cleared.status_code == 200
    assert get_cleared.json() is None


def test_endpoint_verify_target_outcomes(client: TestClient) -> None:
    # Setup contract
    client.post(
        "/target-scope-boundary/contracts",
        json={
            "contract_id": "roe-test-02",
            "engagement_name": "Web Pentest Engagement",
            "authorized_domains": ["*.pentest.target.com"],
            "authorized_cidrs": ["192.168.1.0/24"],
            "prohibited_targets": ["admin.pentest.target.com"],
            "signed_by": "sec_auditor",
            "signature_hash": "sha256_mock_sig",
            "is_active": True,
        },
    )

    # 1. In scope
    v1 = client.post(
        "/target-scope-boundary/verify",
        json={"target_host": "api.pentest.target.com"},
    )
    assert v1.status_code == 200
    assert v1.json()["is_allowed"]
    assert v1.json()["verdict"] == "IN_SCOPE_ALLOWED"

    # 2. Out of scope
    v2 = client.post(
        "/target-scope-boundary/verify",
        json={"target_host": "external-forbidden.org"},
    )
    assert v2.status_code == 200
    assert not v2.json()["is_allowed"]
    assert v2.json()["verdict"] == "OUT_OF_SCOPE_BLOCKED"

    # 3. Metadata endpoint
    v3 = client.post(
        "/target-scope-boundary/verify",
        json={"target_host": "169.254.169.254"},
    )
    assert v3.status_code == 200
    assert not v3.json()["is_allowed"]
    assert v3.json()["verdict"] == "CLOUD_METADATA_PROHIBITED"


def test_endpoint_kill_switch_and_metrics(client: TestClient) -> None:
    # Check initial status
    s_init = client.get("/target-scope-boundary/kill-switch/status")
    assert s_init.status_code == 200
    assert not s_init.json()["is_kill_switch_active"]

    # Activate kill switch
    act_resp = client.post("/target-scope-boundary/kill-switch/activate")
    assert act_resp.status_code == 200
    assert act_resp.json()["is_kill_switch_active"]

    # Reset kill switch
    reset_resp = client.post("/target-scope-boundary/kill-switch/reset")
    assert reset_resp.status_code == 200
    assert not reset_resp.json()["is_kill_switch_active"]

    # Metrics
    m_resp = client.get("/target-scope-boundary/metrics")
    assert m_resp.status_code == 200
    m_data = m_resp.json()
    assert "scope_checks_total" in m_data
    assert "kill_switch_activations_total" in m_data
