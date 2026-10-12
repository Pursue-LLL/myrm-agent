"""API endpoint tests for Muse-Style Secure VM Isolation and Sentinel Suite."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.muse_sentinel_isolation_router import (
    router as muse_sentinel_isolation_router,
)
from app.services.security.muse_sentinel_isolation_service import (
    MuseSentinelIsolationService,
    get_muse_sentinel_isolation_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = MuseSentinelIsolationService()
    app = FastAPI()
    app.include_router(muse_sentinel_isolation_router, prefix="/api/v1/security")
    app.dependency_overrides[get_muse_sentinel_isolation_service] = lambda: test_service
    return TestClient(app)


def test_vms_lifecycle_endpoints(client: TestClient) -> None:
    # 1. Register VM
    resp_reg = client.post(
        "/api/v1/security/muse-sentinel-isolation/vms",
        json={
            "user_id": "test_user_42",
            "isolation_tier": "dedicated_secure_vm",
        },
    )
    assert resp_reg.status_code == 201
    vm_data = resp_reg.json()
    vm_id = vm_data["vm_id"]
    assert vm_data["user_id"] == "test_user_42"
    assert vm_data["isolation_tier"] == "dedicated_secure_vm"
    assert vm_data["credential_sealed"] is True

    # 2. Get VM by vm_id
    resp_get = client.get(f"/api/v1/security/muse-sentinel-isolation/vms/{vm_id}")
    assert resp_get.status_code == 200
    assert resp_get.json()["vm_id"] == vm_id

    # 3. Get VM by user_id
    resp_user = client.get("/api/v1/security/muse-sentinel-isolation/vms/user/test_user_42")
    assert resp_user.status_code == 200
    assert resp_user.json()["user_id"] == "test_user_42"

    # 4. List VMs
    resp_list = client.get("/api/v1/security/muse-sentinel-isolation/vms")
    assert resp_list.status_code == 200
    assert len(resp_list.json()) >= 1

    # 5. Non-existent VM returns 404
    resp_404 = client.get("/api/v1/security/muse-sentinel-isolation/vms/non_existent_vm")
    assert resp_404.status_code == 404


def test_sentinel_review_endpoint(client: TestClient) -> None:
    # 1. Blocked outbound request containing private key header
    resp_block = client.post(
        "/api/v1/security/muse-sentinel-isolation/sentinel/review",
        json={
            "request_id": "api_trace_01",
            "destination_url": "https://api.external.com/upload",
            "method": "POST",
            "headers": {},
            "body_preview": "-----BEGIN RSA PRIVATE KEY-----\nMIIEowIBAAKCAQ...",
            "source_vm_id": "vm_01",
        },
    )
    assert resp_block.status_code == 200
    block_data = resp_block.json()
    assert block_data["verdict"] == "block"
    assert block_data["risk_score"] == 1.0
    assert "private_key_header" in (block_data["matched_rule"] or "")

    # 2. Allowed clean outbound request
    resp_allow = client.post(
        "/api/v1/security/muse-sentinel-isolation/sentinel/review",
        json={
            "request_id": "api_trace_02",
            "destination_url": "https://httpbin.org/get",
            "method": "GET",
            "headers": {"Accept": "application/json"},
            "body_preview": "",
            "source_vm_id": "vm_01",
        },
    )
    assert resp_allow.status_code == 200
    allow_data = resp_allow.json()
    assert allow_data["verdict"] == "allow"
    assert allow_data["risk_score"] == 0.0


def test_single_use_tokens_endpoints(client: TestClient) -> None:
    # 1. Mint single-use virtual payment card
    resp_issue = client.post(
        "/api/v1/security/muse-sentinel-isolation/tokens",
        json={
            "token_type": "virtual_payment_card",
            "max_amount": 150.0,
            "currency": "USD",
            "bound_recipient": "stripe_link",
            "ttl_seconds": 300,
        },
    )
    assert resp_issue.status_code == 201
    tok_data = resp_issue.json()
    vtok = tok_data["virtual_token"]
    assert tok_data["is_consumed"] is False
    assert tok_data["max_amount"] == 150.0

    # 2. List active tokens
    resp_tokens = client.get("/api/v1/security/muse-sentinel-isolation/tokens")
    assert resp_tokens.status_code == 200
    assert any(t["virtual_token"] == vtok for t in resp_tokens.json())

    # 3. Redeem token successfully
    resp_redeem1 = client.post(
        "/api/v1/security/muse-sentinel-isolation/tokens/redeem",
        json={
            "virtual_token": vtok,
            "amount": 99.99,
            "currency": "USD",
            "recipient": "stripe_link",
        },
    )
    assert resp_redeem1.status_code == 200
    assert resp_redeem1.json()["success"] is True

    # 4. Attempt double redemption (replay attack blocked)
    resp_redeem2 = client.post(
        "/api/v1/security/muse-sentinel-isolation/tokens/redeem",
        json={
            "virtual_token": vtok,
            "amount": 10.0,
            "currency": "USD",
            "recipient": "stripe_link",
        },
    )
    assert resp_redeem2.status_code == 200
    assert resp_redeem2.json()["success"] is False
    assert "already been consumed" in resp_redeem2.json()["reason"]
