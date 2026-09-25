"""Tests for Tainted Egress approval, session host trust, and one-time virtual card vouchers."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.tainted_egress import (
    PendingTaintedEgressItem,
    TaintedEgressApprovalManager,
    get_tainted_egress_manager,
)
from app.api.security.tainted_egress import (
    router as tainted_egress_router,
)
from app.commerce.budget_service import (
    get_commerce_budget_service,
)


@pytest.fixture
def app_with_security() -> FastAPI:
    test_app = FastAPI()
    test_app.include_router(tainted_egress_router, prefix="/api/v1/security")
    return test_app


@pytest.fixture
def client(app_with_security: FastAPI) -> TestClient:
    return TestClient(app_with_security)


def test_tainted_egress_manager_lifecycle() -> None:
    manager = TaintedEgressApprovalManager()

    # Initially empty
    assert len(manager.list_pending()) == 0
    assert not manager.is_host_trusted_in_session("session-1", "api.github.com")

    # Register intercepted event
    item = PendingTaintedEgressItem(
        request_id="req-intercept-001",
        session_id="session-1",
        destination_host="api.github.com",
        destination_port=443,
        sensitive_data_type="github_token",
        detected_pattern="ghp_[0-9a-zA-Z]{36}",
    )
    manager.register_pending(item)
    assert len(manager.list_pending()) == 1
    assert len(manager.list_pending(session_id="session-1")) == 1
    assert len(manager.list_pending(session_id="session-other")) == 0

    # Approve with session trust
    decision = manager.approve(
        request_id="req-intercept-001",
        destination_host="api.github.com",
        session_id="session-1",
        trust_session=True,
    )
    assert decision.approved is True
    assert decision.session_trusted is True
    assert len(manager.list_pending()) == 0

    # Verify session trust
    assert manager.is_host_trusted_in_session("session-1", "api.github.com")
    assert not manager.is_host_trusted_in_session("session-2", "api.github.com")

    # Clear trust
    manager.clear_session_trust("session-1")
    assert not manager.is_host_trusted_in_session("session-1", "api.github.com")


def test_tainted_egress_manager_rejection() -> None:
    manager = TaintedEgressApprovalManager()
    item = PendingTaintedEgressItem(
        request_id="req-intercept-002",
        session_id="session-2",
        destination_host="evil-exfiltration.com",
        destination_port=80,
        sensitive_data_type="aws_secret_key",
    )
    manager.register_pending(item)

    decision = manager.reject(
        request_id="req-intercept-002",
        session_id="session-2",
        reason="Suspicious destination",
    )
    assert decision.approved is False
    assert decision.session_trusted is False
    assert "Suspicious destination" in decision.message
    assert len(manager.list_pending()) == 0


def test_tainted_egress_api_endpoints(client: TestClient) -> None:
    manager = get_tainted_egress_manager()

    item = PendingTaintedEgressItem(
        request_id="req-api-001",
        session_id="chat-session-99",
        destination_host="api.openai.com",
        destination_port=443,
        sensitive_data_type="openai_api_key",
    )
    manager.register_pending(item)

    # 1. GET /pending
    resp = client.get("/api/v1/security/tainted-egress/pending?session_id=chat-session-99")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total"] >= 1
    assert any(x["request_id"] == "req-api-001" for x in data["items"])

    # 2. POST /approve
    approve_resp = client.post(
        "/api/v1/security/tainted-egress/approve",
        json={
            "request_id": "req-api-001",
            "destination_host": "api.openai.com",
            "session_id": "chat-session-99",
            "trust_session": True,
        },
    )
    assert approve_resp.status_code == 200
    assert approve_resp.json()["approved"] is True
    assert approve_resp.json()["session_trusted"] is True
    assert manager.is_host_trusted_in_session("chat-session-99", "api.openai.com")

    # 3. DELETE /trust/{session_id}
    del_resp = client.delete("/api/v1/security/tainted-egress/trust/chat-session-99")
    assert del_resp.status_code == 200
    assert not manager.is_host_trusted_in_session("chat-session-99", "api.openai.com")


def test_virtual_card_voucher_issuance_and_resolution() -> None:
    budget_svc = get_commerce_budget_service()

    # Allowed merchant
    res = budget_svc.create_virtual_card_voucher(
        merchant_domain="stripe.com",
        amount_cap_cents=100,
        ttl_seconds=60,
        session_id="session-card-1",
    )
    assert res["success"] is True
    voucher_data = res["voucher"]
    assert isinstance(voucher_data, dict)
    voucher_id = voucher_data["voucher_id"]
    assert voucher_id.startswith("vcard-stripe_com-")

    # Resolve voucher
    resolved = budget_svc.resolve_virtual_card_voucher(voucher_id)
    assert resolved is not None
    assert resolved.amount_cap_cents == 100
    assert resolved.status == "active"

    # Revoke voucher
    assert budget_svc.revoke_virtual_card_voucher(voucher_id) is True
    revoked = budget_svc.resolve_virtual_card_voucher(voucher_id)
    assert revoked is None  # Status is not active
