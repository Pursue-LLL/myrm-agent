"""
[POS] tests/api/security/test_data_sovereignty_watchdog_endpoints.py
[INPUT] fastapi, fastapi.testclient, app.api.security.data_sovereignty_watchdog_router, app.services.security.data_sovereignty_watchdog_service
[OUTPUT] Endpoint integration tests

Validates FastAPI REST endpoints for Private Sandbox Data Sovereignty & Sub-Intrusive Watchdog Suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.data_sovereignty_watchdog_router import (
    router as sovereignty_router,
)
from app.services.security.data_sovereignty_watchdog_service import (
    DataSovereigntyWatchdogService,
    get_data_sovereignty_watchdog_service,
)


@pytest.fixture
def client() -> TestClient:
    service = DataSovereigntyWatchdogService()
    app = FastAPI()
    app.include_router(sovereignty_router)
    app.dependency_overrides[get_data_sovereignty_watchdog_service] = lambda: service
    return TestClient(app)


def test_sovereignty_seal_endpoints(client: TestClient) -> None:
    """Validate POST /sovereignty/issue-seal, verify-seal, and GET /sovereignty/latest."""
    # 1. Issue seal
    issue_res = client.post(
        "/data-sovereignty-watchdog/sovereignty/issue-seal",
        json={
            "storage_target": "sqlite:///app/data/sovereign.db",
            "volume_mount_path": "/var/lib/myrm/sovereign_vol",
            "seal_level": "PRIVATE_SANDBOX_VOLUME",
        },
    )
    assert issue_res.status_code == 201
    sdata = issue_res.json()
    seal_id = sdata["seal_id"]
    assert sdata["central_cloud_zero_retention"] is True

    # 2. Verify seal
    verify_res = client.post(
        "/data-sovereignty-watchdog/sovereignty/verify-seal",
        json={"seal_id": seal_id},
    )
    assert verify_res.status_code == 200
    assert verify_res.json()["is_valid"] is True

    # 3. Get latest seal
    latest_res = client.get("/data-sovereignty-watchdog/sovereignty/latest")
    assert latest_res.status_code == 200
    assert latest_res.json()["seal_id"] == seal_id


def test_watchdog_card_evaluation_endpoints(client: TestClient) -> None:
    """Validate POST /watchdog/evaluate, GET /watchdog/cards/active, and /watchdog/cards/all."""
    # 1. Evaluate high-value suggestion ($30.00)
    eval_res = client.post(
        "/data-sovereignty-watchdog/watchdog/evaluate",
        json={
            "title": "Duplicate AWS VPC NAT Gateway",
            "service_name": "AWSVPC",
            "potential_savings_cents": 3000,
            "deadline_epoch": None,
            "message": "Remove idle NAT gateway to save $30/mo.",
        },
    )
    assert eval_res.status_code == 200
    edata = eval_res.json()
    assert edata["is_suppressed"] is False
    assert edata["value_level"] == "HIGH_VALUE_ALERT"

    # 2. Evaluate low-value noise ($1.00)
    noise_res = client.post(
        "/data-sovereignty-watchdog/watchdog/evaluate",
        json={
            "title": "Minor log cleanup",
            "service_name": "LogCleaner",
            "potential_savings_cents": 100,
            "deadline_epoch": None,
            "message": "Tiny cleanup.",
        },
    )
    assert noise_res.status_code == 200
    assert noise_res.json()["is_suppressed"] is True

    # 3. List active cards
    active_res = client.get("/data-sovereignty-watchdog/watchdog/cards/active")
    assert active_res.status_code == 200
    assert len(active_res.json()) == 1

    # 4. List all cards
    all_res = client.get("/data-sovereignty-watchdog/watchdog/cards/all")
    assert all_res.status_code == 200
    assert len(all_res.json()) == 2


def test_consent_ticket_endpoints_lifecycle(client: TestClient) -> None:
    """Validate create-ticket, pending list, approve, and deny endpoints."""
    # 1. Create ticket
    ticket_res = client.post(
        "/data-sovereignty-watchdog/consent/create-ticket",
        json={
            "action_type": "SUBSCRIPTION_CANCEL",
            "service_name": "Spotify Family",
            "financial_impact_cents": 1999,
            "payload_summary": "Cancel family plan subscription",
        },
    )
    assert ticket_res.status_code == 201
    tdata = ticket_res.json()
    ticket_id = tdata["ticket_id"]
    assert tdata["is_approved"] is False

    # 2. List pending
    pending_res = client.get("/data-sovereignty-watchdog/consent/pending")
    assert pending_res.status_code == 200
    assert len(pending_res.json()) == 1
    assert pending_res.json()[0]["ticket_id"] == ticket_id

    # 3. Approve ticket
    appr_res = client.post(
        "/data-sovereignty-watchdog/consent/approve",
        json={"ticket_id": ticket_id},
    )
    assert appr_res.status_code == 200
    assert appr_res.json()["is_approved"] is True

    # 4. Create and deny another ticket
    t2_res = client.post(
        "/data-sovereignty-watchdog/consent/create-ticket",
        json={
            "action_type": "REFUND_DISPUTE",
            "service_name": "Unknown Seller",
            "financial_impact_cents": 5000,
            "payload_summary": "Chargeback dispute",
        },
    )
    t2_id = t2_res.json()["ticket_id"]
    deny_res = client.post(
        "/data-sovereignty-watchdog/consent/deny",
        json={"ticket_id": t2_id},
    )
    assert deny_res.status_code == 200
    assert deny_res.json()["is_denied"] is True

    # 5. Metrics
    metrics_res = client.get("/data-sovereignty-watchdog/metrics")
    assert metrics_res.status_code == 200
    mdata = metrics_res.json()
    assert mdata["high_stakes_actions_blocked_total"] == 2
    assert mdata["high_stakes_consents_approved_total"] == 1
    assert mdata["high_stakes_consents_denied_total"] == 1
