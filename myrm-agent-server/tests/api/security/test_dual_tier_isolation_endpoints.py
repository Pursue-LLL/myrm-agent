"""Integration tests for Dual-Tier Root Admin & User API Key Isolation API endpoints."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.dual_tier_isolation_router import (
    router as dual_tier_isolation_router,
)


@pytest.fixture(scope="function")
def client() -> TestClient:
    """Fixture providing test client mounting dual_tier_isolation_router."""
    test_app = FastAPI(title="Dual Tier Isolation Test App")
    test_app.include_router(dual_tier_isolation_router, prefix="/api/v1/security")
    return TestClient(test_app, raise_server_exceptions=False)


def test_register_admin_and_evaluate_endpoints(client: TestClient) -> None:
    # 1. Register admin key
    reg_resp = client.post(
        "/api/v1/security/dual-tier-isolation/register-admin-key",
        json={"allowed_scopes": ["admin:*"]},
    )
    assert reg_resp.status_code == 200
    adm_data = reg_resp.json()
    assert adm_data["tier"] == "ROOT_ADMIN"
    admin_key = adm_data["raw_key"]

    # 2. Evaluate admin on control plane -> 200 OK, permitted
    eval_cp_resp = client.post(
        "/api/v1/security/dual-tier-isolation/evaluate-access",
        json={"raw_key": admin_key, "requested_plane": "CONTROL_PLANE"},
    )
    assert eval_cp_resp.status_code == 200
    cp_data = eval_cp_resp.json()
    assert cp_data["is_permitted"] is True
    assert cp_data["verdict"] == "PERMITTED"

    # 3. Evaluate admin on data plane -> 200 OK, blocked (Physical Separation)
    eval_dp_resp = client.post(
        "/api/v1/security/dual-tier-isolation/evaluate-access",
        json={
            "raw_key": admin_key,
            "requested_plane": "DATA_PLANE",
            "target_user_id": "victim_user",
        },
    )
    assert eval_dp_resp.status_code == 200
    dp_data = eval_dp_resp.json()
    assert dp_data["is_permitted"] is False
    assert dp_data["verdict"] == "BLOCKED_DATA_PLANE_VIOLATION"


def test_derive_user_and_evaluate_endpoints(client: TestClient) -> None:
    # 1. Derive user key
    derive_resp = client.post(
        "/api/v1/security/dual-tier-isolation/derive-user-key",
        json={
            "user_id": "alice",
            "tenant_id": "org_sec",
            "allowed_scopes": ["data:*"],
        },
    )
    assert derive_resp.status_code == 200
    usr_data = derive_resp.json()
    assert usr_data["tier"] == "DERIVED_USER"
    user_key = usr_data["raw_key"]

    # 2. Evaluate user on own data plane -> permitted
    eval_own_resp = client.post(
        "/api/v1/security/dual-tier-isolation/evaluate-access",
        json={
            "raw_key": user_key,
            "requested_plane": "DATA_PLANE",
            "target_user_id": "alice",
            "target_tenant_id": "org_sec",
        },
    )
    assert eval_own_resp.status_code == 200
    assert eval_own_resp.json()["is_permitted"] is True
    assert eval_own_resp.json()["verdict"] == "PERMITTED"

    # 3. Evaluate user on cross-tenant data plane -> blocked
    eval_cross_resp = client.post(
        "/api/v1/security/dual-tier-isolation/evaluate-access",
        json={
            "raw_key": user_key,
            "requested_plane": "DATA_PLANE",
            "target_user_id": "bob",
        },
    )
    assert eval_cross_resp.status_code == 200
    assert eval_cross_resp.json()["is_permitted"] is False
    assert eval_cross_resp.json()["verdict"] == "BLOCKED_CROSS_TENANT_BREACH"

    # 4. Evaluate user on control plane -> blocked
    eval_cp_resp = client.post(
        "/api/v1/security/dual-tier-isolation/evaluate-access",
        json={"raw_key": user_key, "requested_plane": "CONTROL_PLANE"},
    )
    assert eval_cp_resp.status_code == 200
    assert eval_cp_resp.json()["is_permitted"] is False
    assert eval_cp_resp.json()["verdict"] == "BLOCKED_CONTROL_PLANE_VIOLATION"
