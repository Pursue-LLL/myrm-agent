"""
[POS] tests/api/security/test_ephemeral_identity_voucher_endpoints.py
[INPUT] fastapi, fastapi.testclient, app.api.security.ephemeral_identity_voucher_router
[OUTPUT] Integration tests for Ephemeral Identity & Verifiable Audit Trail REST endpoints

Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.ephemeral_identity_voucher_router import (
    router as ephemeral_identity_voucher_router,
)
from app.services.security.ephemeral_identity_voucher_service import (
    EphemeralIdentityVoucherService,
    get_ephemeral_identity_voucher_service,
)


@pytest.fixture
def client() -> TestClient:
    """Fixture providing isolated TestClient with freshly instantiated service."""
    service = EphemeralIdentityVoucherService()
    app = FastAPI()
    app.include_router(ephemeral_identity_voucher_router)
    app.dependency_overrides[get_ephemeral_identity_voucher_service] = lambda: service
    return TestClient(app)


def test_endpoint_identity_lifecycle(client: TestClient) -> None:
    """Test identity issuance, get, verify, and revoke via HTTP endpoints."""
    # 1. Issue identity
    issue_resp = client.post(
        "/ephemeral-identity-voucher/identities",
        json={
            "agent_id": "agent-procure-1",
            "task_id": "task-procure-99",
            "allowed_scopes": ["cart.read", "checkout.pay"],
            "ttl_seconds": 600.0,
            "metadata": {"ip": "127.0.0.1"},
        },
    )
    assert issue_resp.status_code == 201
    data = issue_resp.json()
    identity_id: str = data["identity_id"]
    token: str = data["ephemeral_token"]
    assert identity_id.startswith("eph-id-")
    assert data["status"] == "ACTIVE"

    # 2. Get identity
    get_resp = client.get(f"/ephemeral-identity-voucher/identities/{identity_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["identity_id"] == identity_id

    # 3. Verify valid
    verify_resp = client.post(
        "/ephemeral-identity-voucher/identities/verify",
        json={
            "identity_id": identity_id,
            "ephemeral_token": token,
            "required_scope": "checkout.pay",
        },
    )
    assert verify_resp.status_code == 200
    assert verify_resp.json()["is_valid"] is True
    assert verify_resp.json()["status"] == "ACTIVE"

    # 4. Revoke identity
    revoke_resp = client.post(
        f"/ephemeral-identity-voucher/identities/{identity_id}/revoke",
        json={"reason": "Completed session early"},
    )
    assert revoke_resp.status_code == 200
    assert revoke_resp.json()["revoked"] is True

    # 5. Verify after revocation
    verify_again = client.post(
        "/ephemeral-identity-voucher/identities/verify",
        json={
            "identity_id": identity_id,
            "ephemeral_token": token,
        },
    )
    assert verify_again.status_code == 200
    assert verify_again.json()["is_valid"] is False
    assert verify_again.json()["status"] == "REVOKED"


def test_endpoint_identity_consume(client: TestClient) -> None:
    """Test single-use identity consumption endpoint."""
    issue_resp = client.post(
        "/ephemeral-identity-voucher/identities",
        json={
            "agent_id": "agent-single-use",
            "task_id": "task-single-1",
            "allowed_scopes": ["exec.run"],
        },
    )
    assert issue_resp.status_code == 201
    identity_id: str = issue_resp.json()["identity_id"]

    consume_resp = client.post(
        f"/ephemeral-identity-voucher/identities/{identity_id}/consume"
    )
    assert consume_resp.status_code == 200
    assert consume_resp.json()["consumed"] is True

    # Check consumed status
    get_resp = client.get(f"/ephemeral-identity-voucher/identities/{identity_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["status"] == "CONSUMED"


def test_endpoint_voucher_operations(client: TestClient) -> None:
    """Test issuing, getting, redeeming, and voiding disposable payment vouchers."""
    # 1. Issue voucher
    issue_resp = client.post(
        "/ephemeral-identity-voucher/vouchers",
        json={
            "identity_id": "eph-id-fake-1",
            "target_merchant_domain": "https://api.stripe.com/v1",
            "max_authorized_amount": 250.0,
            "currency": "USD",
            "ttl_seconds": 600.0,
        },
    )
    assert issue_resp.status_code == 201
    v_data = issue_resp.json()
    voucher_id: str = v_data["voucher_id"]
    token: str = v_data["single_use_token"]
    assert v_data["target_merchant_domain"] == "api.stripe.com"
    assert v_data["status"] == "ISSUED"

    # 2. Get voucher
    get_resp = client.get(f"/ephemeral-identity-voucher/vouchers/{voucher_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["voucher_id"] == voucher_id

    # 3. Redeem with domain violation
    bad_domain_resp = client.post(
        "/ephemeral-identity-voucher/vouchers/redeem",
        json={
            "voucher_id": voucher_id,
            "single_use_token": token,
            "request_domain": "phishing.com",
            "requested_amount": 50.0,
        },
    )
    assert bad_domain_resp.status_code == 200
    assert bad_domain_resp.json()["is_success"] is False
    assert bad_domain_resp.json()["status"] == "DOMAIN_MISMATCH"

    # 4. Issue fresh voucher and redeem successfully
    v2_resp = client.post(
        "/ephemeral-identity-voucher/vouchers",
        json={
            "identity_id": "eph-id-fake-2",
            "target_merchant_domain": "api.stripe.com",
            "max_authorized_amount": 250.0,
            "currency": "USD",
        },
    )
    v2_id: str = v2_resp.json()["voucher_id"]
    v2_token: str = v2_resp.json()["single_use_token"]

    redeem_resp = client.post(
        "/ephemeral-identity-voucher/vouchers/redeem",
        json={
            "voucher_id": v2_id,
            "single_use_token": v2_token,
            "request_domain": "api.stripe.com",
            "requested_amount": 199.95,
            "merchant_order_ref": "INV-STRIPE-4040",
        },
    )
    assert redeem_resp.status_code == 200
    assert redeem_resp.json()["is_success"] is True
    assert redeem_resp.json()["status"] == "REDEEMED"

    # 5. Issue another voucher and void it
    v3_resp = client.post(
        "/ephemeral-identity-voucher/vouchers",
        json={
            "identity_id": "eph-id-fake-3",
            "target_merchant_domain": "api.stripe.com",
            "max_authorized_amount": 50.0,
        },
    )
    v3_id: str = v3_resp.json()["voucher_id"]
    void_resp = client.post(
        f"/ephemeral-identity-voucher/vouchers/{v3_id}/void",
        json={"reason": "Payment aborted by user"},
    )
    assert void_resp.status_code == 200
    assert void_resp.json()["voided"] is True


def test_endpoint_audit_trail_and_bundle(client: TestClient) -> None:
    """Test recording audit phase events, verifying integrity, and exporting proof bundle."""
    task_id = "task-flight-booking-771"

    # 1. Record events for all 4 phases
    phases: list[str] = [
        "USER_INTENT",
        "CREDENTIAL_GRANT",
        "EXECUTION_SNAPSHOT",
        "SETTLEMENT_RECEIPT",
    ]
    for ph in phases:
        ev_resp = client.post(
            "/ephemeral-identity-voucher/audit/events",
            json={
                "task_id": task_id,
                "phase": ph,
                "summary": f"Completed phase {ph}",
                "structured_payload": {"step": ph, "status": "ok"},
            },
        )
        assert ev_resp.status_code == 201
        assert ev_resp.json()["phase"] == ph
        assert ev_resp.json()["task_id"] == task_id

    # 2. Verify audit trail integrity
    verify_resp = client.get(f"/ephemeral-identity-voucher/audit/verify/{task_id}")
    assert verify_resp.status_code == 200
    v_data = verify_resp.json()
    assert v_data["is_valid"] is True
    assert v_data["merkle_root"] is not None

    # 3. Export proof bundle
    bundle_resp = client.get(f"/ephemeral-identity-voucher/audit/bundle/{task_id}")
    assert bundle_resp.status_code == 200
    b_data = bundle_resp.json()
    assert b_data["task_id"] == task_id
    assert b_data["verification_success"] is True
    assert len(b_data["events"]) == 4
    assert len(b_data["phases_included"]) == 4

    # 4. Get metrics
    metrics_resp = client.get("/ephemeral-identity-voucher/metrics")
    assert metrics_resp.status_code == 200
    assert metrics_resp.json()["audit_events_recorded_total"] >= 4
