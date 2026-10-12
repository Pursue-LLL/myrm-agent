"""API endpoint tests for Agentic Transaction Safety Pillars and Tri-Flow Isolation."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.security.tri_flow_safety_router import router as tri_flow_safety_router
from app.services.security.tri_flow_safety_service import (
    TriFlowSafetyService,
    get_tri_flow_safety_service,
)


@pytest.fixture
def client() -> TestClient:
    test_service = TriFlowSafetyService(enforce_strict_endpoints=True)
    app = FastAPI()
    app.include_router(tri_flow_safety_router, prefix="/api/v1/security")
    app.dependency_overrides[get_tri_flow_safety_service] = lambda: test_service
    return TestClient(app)


def test_verify_workflow_call_endpoint(client: TestClient) -> None:
    """Test verify-call endpoint enforces tri-flow role isolation and HITL checks."""
    # 1. Read-Only flow invoking safe read tool
    safe_resp = client.post(
        "/api/v1/security/tri-flow/verify-call",
        json={"role": "read_only", "tool_name": "web_search"},
    )
    assert safe_resp.status_code == 200
    safe_data = safe_resp.json()
    assert safe_data["is_allowed"] is True
    assert safe_data["current_role"] == "read_only"
    assert safe_data["requires_hitl"] is False

    # 2. Read-Only flow attempting to call buyer order tool -> BLOCKED
    violation_resp = client.post(
        "/api/v1/security/tri-flow/verify-call",
        json={"role": "read_only", "tool_name": "create_order"},
    )
    assert violation_resp.status_code == 200
    violation_data = violation_resp.json()
    assert violation_data["is_allowed"] is False
    assert "Violation: tool 'create_order' requires roles" in violation_data["reason"]

    # 3. Buyer flow exceeding threshold without HITL -> BLOCKED (requires_hitl=True)
    hitl_needed_resp = client.post(
        "/api/v1/security/tri-flow/verify-call",
        json={
            "role": "buyer",
            "tool_name": "create_order",
            "amount": 250.0,
            "hitl_confirmed": False,
        },
    )
    assert hitl_needed_resp.status_code == 200
    hitl_data = hitl_needed_resp.json()
    assert hitl_data["is_allowed"] is False
    assert hitl_data["requires_hitl"] is True

    # 4. Buyer flow with HITL confirmation -> ALLOWED
    confirmed_resp = client.post(
        "/api/v1/security/tri-flow/verify-call",
        json={
            "role": "buyer",
            "tool_name": "create_order",
            "amount": 250.0,
            "hitl_confirmed": True,
        },
    )
    assert confirmed_resp.status_code == 200
    assert confirmed_resp.json()["is_allowed"] is True


def test_endpoint_validation_and_registration(client: TestClient) -> None:
    """Test registering documented endpoints and validating outgoing calls."""
    # Register documented endpoint
    reg_resp = client.post(
        "/api/v1/security/tri-flow/register-endpoint",
        json={
            "service": "merchant_gateway",
            "path": "/api/v2/items/{item_id}",
            "allowed_methods": ["GET", "POST"],
            "contract_functions": ["reserveInventory"],
        },
    )
    assert reg_resp.status_code == 200
    assert reg_resp.json()["status"] == "registered"

    # Validate allowed endpoint call
    valid_resp = client.post(
        "/api/v1/security/tri-flow/validate-endpoint",
        json={
            "service": "merchant_gateway",
            "path": "/api/v2/items/item_999",
            "method": "POST",
            "function_name": "reserveInventory",
        },
    )
    assert valid_resp.status_code == 200
    assert valid_resp.json()["is_allowed"] is True

    # Validate blind probe guessing undocumented endpoint -> BLOCKED
    guess_resp = client.post(
        "/api/v1/security/tri-flow/validate-endpoint",
        json={
            "service": "merchant_gateway",
            "path": "/api/v2/internal/admin_override",
            "method": "POST",
        },
    )
    assert guess_resp.status_code == 200
    guess_data = guess_resp.json()
    assert guess_data["is_allowed"] is False
    assert "Zero-Guesswork violation" in guess_data["reason"]


def test_sanitize_logs_endpoint(client: TestClient) -> None:
    """Test scrubbing sensitive private keys via sanitize-logs endpoint."""
    raw_prompt = (
        "Agent debug trace: private key 0xabcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789\n"
        "Sending transaction."
    )
    resp = client.post(
        "/api/v1/security/tri-flow/sanitize-logs",
        json={"raw_text": raw_prompt},
    )
    assert resp.status_code == 200
    data = resp.json()
    assert data["redactions_count"] == 1
    assert "0xabcdef0123456789abcdef0123456789abcdef0123456789abcdef0123456789" not in data["sanitized_text"]
    assert "[REDACTED_CREDENTIAL:ethereum_private_key:" in data["sanitized_text"]
    assert "ethereum_private_key" in data["detected_types"]


def test_register_tool_contract_endpoint(client: TestClient) -> None:
    """Test registering a custom tool contract via endpoint."""
    resp = client.post(
        "/api/v1/security/tri-flow/register-tool",
        json={
            "tool_name": "seller_verify_delivery",
            "allowed_roles": ["seller"],
            "is_financial_transaction": False,
        },
    )
    assert resp.status_code == 200
    assert resp.json()["status"] == "registered"

    # Verify that seller can use it and buyer cannot
    check_seller = client.post(
        "/api/v1/security/tri-flow/verify-call",
        json={"role": "seller", "tool_name": "seller_verify_delivery"},
    )
    assert check_seller.json()["is_allowed"] is True

    check_buyer = client.post(
        "/api/v1/security/tri-flow/verify-call",
        json={"role": "buyer", "tool_name": "seller_verify_delivery"},
    )
    assert check_buyer.json()["is_allowed"] is False
