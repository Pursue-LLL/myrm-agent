"""API endpoint tests for Agent Commerce Dispute & Escrow in myrm-agent-server."""

from __future__ import annotations

import hashlib

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from myrm_agent_harness.core.security.commerce_dispute_escrow import (
    CommerceEscrowManager,
)

from app.api.security.commerce_dispute_escrow_router import (
    router as commerce_dispute_escrow_router,
)
from app.services.security.commerce_dispute_escrow_service import (
    CommerceDisputeEscrowService,
    get_commerce_dispute_escrow_service,
)


@pytest.fixture
def client() -> TestClient:
    app = FastAPI()
    manager = CommerceEscrowManager()
    service = CommerceDisputeEscrowService(manager=manager)

    app.dependency_overrides[get_commerce_dispute_escrow_service] = lambda: service
    app.include_router(commerce_dispute_escrow_router, prefix="/api/v1/security")
    return TestClient(app)


def test_escrow_crud_and_lifecycle_api(client: TestClient) -> None:
    # 1. Create escrow
    payload = {
        "job_id": "job_api_1",
        "client_agent_id": "client_alpha",
        "provider_agent_id": "provider_beta",
        "strategy_type": "PROGRAM",
        "amount": 500.0,
    }
    resp = client.post("/api/v1/security/commerce-dispute-escrow/escrows", json=payload)
    assert resp.status_code == 201
    escrow = resp.json()
    assert escrow["status"] == "FUNDED"
    escrow_id = escrow["escrow_id"]

    # 2. Get escrow
    get_resp = client.get(f"/api/v1/security/commerce-dispute-escrow/escrows/{escrow_id}")
    assert get_resp.status_code == 200
    assert get_resp.json()["amount"] == 500.0

    # 3. Submit deliverable
    deliver_resp = client.post(
        "/api/v1/security/commerce-dispute-escrow/escrows/deliver",
        json={
            "escrow_id": escrow_id,
            "provider_agent_id": "provider_beta",
            "deliverable_hash": "0xproof_hash_abc",
        },
    )
    assert deliver_resp.status_code == 200
    assert deliver_resp.json()["status"] == "DELIVERED"

    # 4. Release funds
    release_resp = client.post(
        "/api/v1/security/commerce-dispute-escrow/escrows/release",
        json={"escrow_id": escrow_id, "client_agent_id": "client_alpha"},
    )
    assert release_resp.status_code == 200
    assert release_resp.json()["status"] == "RESOLVED_RELEASED"


def test_circuit_breaker_api(client: TestClient) -> None:
    create_resp = client.post(
        "/api/v1/security/commerce-dispute-escrow/escrows",
        json={
            "job_id": "job_cb_api",
            "client_agent_id": "client_alpha",
            "provider_agent_id": "provider_beta",
            "strategy_type": "CEX_CAPITAL",
            "amount": 1000.0,
            "circuit_breakers": {
                "max_position_pct": 20.0,
                "max_daily_loss_pct": 5.0,
                "max_open_exposure_pct": 30.0,
            },
        },
    )
    escrow_id = create_resp.json()["escrow_id"]

    cb_resp = client.post(
        "/api/v1/security/commerce-dispute-escrow/escrows/circuit-breaker",
        json={
            "escrow_id": escrow_id,
            "current_position_pct": 25.0,  # Trips max 20%
        },
    )
    assert cb_resp.status_code == 200
    assert cb_resp.json()["triggered"] is True
    assert cb_resp.json()["escrow_status"] == "FROZEN_CIRCUIT_BREAKER"


def test_dispute_arbitration_lifecycle_api(client: TestClient) -> None:
    # 1. Setup escrow & deliverable
    escrow_resp = client.post(
        "/api/v1/security/commerce-dispute-escrow/escrows",
        json={
            "job_id": "job_disp_api",
            "client_agent_id": "alice",
            "provider_agent_id": "bob",
            "strategy_type": "RUBRIC",
            "amount": 2000.0,
        },
    )
    escrow_id = escrow_resp.json()["escrow_id"]

    client.post(
        "/api/v1/security/commerce-dispute-escrow/escrows/deliver",
        json={
            "escrow_id": escrow_id,
            "provider_agent_id": "bob",
            "deliverable_hash": "0xproof_disputed",
        },
    )

    # 2. Raise dispute
    disp_resp = client.post(
        "/api/v1/security/commerce-dispute-escrow/disputes",
        json={
            "escrow_id": escrow_id,
            "initiator_agent_id": "alice",
            "deposit_amount": 100.0,
            "arbitrators": ["arb_0", "arb_1", "arb_2"],
        },
    )
    assert disp_resp.status_code == 201
    dispute_id = disp_resp.json()["dispute_id"]

    # 3. Commit votes: 2 uphold (0), 1 overturn (1)
    s0, s1, s2 = "salt0", "salt1", "salt2"
    h0 = hashlib.sha256(f"0:{s0}".encode()).hexdigest()
    h1 = hashlib.sha256(f"0:{s1}".encode()).hexdigest()
    h2 = hashlib.sha256(f"1:{s2}".encode()).hexdigest()

    client.post(
        "/api/v1/security/commerce-dispute-escrow/disputes/commit",
        json={"dispute_id": dispute_id, "seat_index": 0, "arbitrator_id": "arb_0", "commitment_hash": h0},
    )
    client.post(
        "/api/v1/security/commerce-dispute-escrow/disputes/commit",
        json={"dispute_id": dispute_id, "seat_index": 1, "arbitrator_id": "arb_1", "commitment_hash": h1},
    )
    c3 = client.post(
        "/api/v1/security/commerce-dispute-escrow/disputes/commit",
        json={"dispute_id": dispute_id, "seat_index": 2, "arbitrator_id": "arb_2", "commitment_hash": h2},
    )
    assert c3.json()["status"] == "REVEAL"

    # 4. Reveal votes
    client.post(
        "/api/v1/security/commerce-dispute-escrow/disputes/reveal",
        json={"dispute_id": dispute_id, "seat_index": 0, "arbitrator_id": "arb_0", "vote": 0, "salt": s0},
    )
    client.post(
        "/api/v1/security/commerce-dispute-escrow/disputes/reveal",
        json={"dispute_id": dispute_id, "seat_index": 1, "arbitrator_id": "arb_1", "vote": 0, "salt": s1},
    )
    client.post(
        "/api/v1/security/commerce-dispute-escrow/disputes/reveal",
        json={"dispute_id": dispute_id, "seat_index": 2, "arbitrator_id": "arb_2", "vote": 1, "salt": s2},
    )

    # 5. Settle
    settle_resp = client.post(
        f"/api/v1/security/commerce-dispute-escrow/disputes/{dispute_id}/settle"
    )
    assert settle_resp.status_code == 200
    res = settle_resp.json()
    assert res["dispute"]["outcome"] == "UPHELD"
    assert res["escrow"]["status"] == "RESOLVED_RELEASED"
    assert res["release_to_provider"] == 2000.0


def test_error_handling_api(client: TestClient) -> None:
    # 404 on nonexistent escrow
    resp = client.get("/api/v1/security/commerce-dispute-escrow/escrows/nonexistent")
    assert resp.status_code == 404

    # 400 on negative amount
    resp = client.post(
        "/api/v1/security/commerce-dispute-escrow/escrows",
        json={
            "job_id": "j",
            "client_agent_id": "c",
            "provider_agent_id": "p",
            "strategy_type": "PROGRAM",
            "amount": -10.0,
        },
    )
    assert resp.status_code == 422 or resp.status_code == 400
