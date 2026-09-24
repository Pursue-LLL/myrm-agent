"""Integration tests for Autonomous Commerce Spending Limit and Payment API."""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.commerce.spending_router import router as spending_router
from app.commerce.budget_service import (
    CommerceBudgetConfigDTO,
    CommerceBudgetService,
    get_commerce_budget_service,
)
from app.commerce.spending_ledger import SpendingLedgerStore


@pytest.fixture
def custom_service(tmp_path: pytest.TempPathFactory) -> CommerceBudgetService:
    """Fixture providing an isolated CommerceBudgetService instance with temp ledger storage."""
    temp_ledger_file = tmp_path / "test_spending_ledger.json"
    store = SpendingLedgerStore(storage_path=temp_ledger_file)
    from myrm_agent_harness.core.security.egress.spend_governor import (
        SpendGovernor,
        SpendGovernorConfig,
    )

    governor = SpendGovernor(
        config=SpendGovernorConfig(
            daily_cap_cents=1000,
            per_action_cap_cents=200,
            allowed_merchants=("namesilo.com", "*.openai.com"),
        )
    )
    return CommerceBudgetService(governor=governor, ledger_store=store)


@pytest.fixture
def client(custom_service: CommerceBudgetService) -> TestClient:
    """Fixture providing TestClient with monkeypatched singleton service."""
    app = FastAPI()
    app.include_router(spending_router, prefix="/api/v1")

    # Patch global accessor
    import app.api.commerce.spending_router as mod

    orig = mod.get_commerce_budget_service
    mod.get_commerce_budget_service = lambda: custom_service
    try:
        yield TestClient(app)
    finally:
        mod.get_commerce_budget_service = orig


class TestCommerceSpendingApi:
    def test_get_budget_status(self, client: TestClient) -> None:
        """Test retrieving initial budget status."""
        resp = client.get("/api/v1/commerce/spending/budget")
        assert resp.status_code == 200
        payload = resp.json()["data"]
        assert payload["daily_cap_cents"] == 1000
        assert payload["per_action_cap_cents"] == 200
        assert payload["daily_spent_cents"] == 0
        assert payload["remaining_cents"] == 1000
        assert payload["is_frozen"] is False
        assert "namesilo.com" in payload["allowed_merchants"]

    def test_update_budget_config(self, client: TestClient) -> None:
        """Test updating spending limits and whitelist."""
        update_payload = {
            "daily_cap_cents": 2500,
            "per_action_cap_cents": 500,
            "allowed_merchants": ["namesilo.com", "2captcha.com"],
            "currency": "USD",
            "is_frozen": False,
            "lease_ttl_seconds": 180,
        }
        resp = client.put("/api/v1/commerce/spending/budget", json=update_payload)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["daily_cap_cents"] == 2500
        assert data["per_action_cap_cents"] == 500
        assert data["allowed_merchants"] == ["namesilo.com", "2captcha.com"]

    def test_preauth_and_commit_flow(self, client: TestClient) -> None:
        """Test happy path: preauth -> commit -> ledger audit entry."""
        preauth_req = {
            "merchant_domain": "namesilo.com",
            "amount_cents": 99,
            "session_id": "test_sess_01",
            "task_id": "task_abc",
            "idempotency_key": "txn_001",
        }
        resp = client.post("/api/v1/commerce/spending/preauth", json=preauth_req)
        assert resp.status_code == 200
        data = resp.json()["data"]
        assert data["success"] is True
        assert data["code"] == "APPROVED"
        assert data["amount_cents"] == 99
        lease_id = data["lease_id"]
        assert lease_id is not None
        assert data["voucher"].startswith("myrm-spend-v1.")

        # Commit payment
        commit_req = {"lease_id": lease_id, "idempotency_key": "txn_001"}
        c_resp = client.post("/api/v1/commerce/spending/commit", json=commit_req)
        assert c_resp.status_code == 200
        c_data = c_resp.json()["data"]
        assert c_data["success"] is True
        assert c_data["code"] == "COMMITTED"
        assert c_data["entryHash"] is not None

        # Verify in ledger
        l_resp = client.get("/api/v1/commerce/spending/ledger?session_id=test_sess_01")
        assert l_resp.status_code == 200
        ledger_entries = l_resp.json()["data"]
        assert len(ledger_entries) == 1
        entry = ledger_entries[0]
        assert entry["lease_id"] == lease_id
        assert entry["status"] == "committed"
        assert entry["merchant_domain"] == "namesilo.com"
        assert entry["amount_cents"] == 99

    def test_untrusted_merchant_blocked(self, client: TestClient) -> None:
        """Test rejection of non-whitelisted merchant."""
        req = {
            "merchant_domain": "untrusted-shop.com",
            "amount_cents": 50,
            "session_id": "test_sess_02",
        }
        resp = client.post("/api/v1/commerce/spending/preauth", json=req)
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["code"] == "UNTRUSTED_MERCHANT"

    def test_per_action_cap_exceeded(self, client: TestClient) -> None:
        """Test rejection when single action exceeds cap."""
        req = {
            "merchant_domain": "namesilo.com",
            "amount_cents": 250,  # Cap is 200
            "session_id": "test_sess_03",
        }
        resp = client.post("/api/v1/commerce/spending/preauth", json=req)
        assert resp.status_code == 403
        detail = resp.json()["detail"]
        assert detail["code"] == "LIMIT_EXCEEDED"

    def test_emergency_freeze_breaker(self, client: TestClient) -> None:
        """Test emergency circuit breaker stops transactions immediately."""
        # Toggle freeze
        freeze_resp = client.post("/api/v1/commerce/spending/freeze", json={"freeze": True})
        assert freeze_resp.status_code == 200
        assert freeze_resp.json()["data"]["is_frozen"] is True

        # Preauth must be blocked with 403 FROZEN
        req = {
            "merchant_domain": "namesilo.com",
            "amount_cents": 50,
            "session_id": "test_sess_04",
        }
        block_resp = client.post("/api/v1/commerce/spending/preauth", json=req)
        assert block_resp.status_code == 403
        assert block_resp.json()["detail"]["code"] == "FROZEN"

        # Unfreeze and verify recovery
        unfreeze_resp = client.post("/api/v1/commerce/spending/freeze", json={"freeze": False})
        assert unfreeze_resp.status_code == 200
        assert unfreeze_resp.json()["data"]["is_frozen"] is False

        ok_resp = client.post("/api/v1/commerce/spending/preauth", json=req)
        assert ok_resp.status_code == 200
        assert ok_resp.json()["data"]["success"] is True

    def test_release_spend_reservation(self, client: TestClient) -> None:
        """Test releasing a reserved lease marks it refunded."""
        preauth_req = {
            "merchant_domain": "namesilo.com",
            "amount_cents": 50,
            "session_id": "test_sess_05",
        }
        resp = client.post("/api/v1/commerce/spending/preauth", json=preauth_req)
        lease_id = resp.json()["data"]["lease_id"]

        rel_resp = client.post("/api/v1/commerce/spending/release", json={"lease_id": lease_id})
        assert rel_resp.status_code == 200
        assert rel_resp.json()["data"]["released"] is True

        # Check ledger status is refunded
        l_resp = client.get("/api/v1/commerce/spending/ledger?session_id=test_sess_05")
        entry = l_resp.json()["data"][0]
        assert entry["status"] == "refunded"
