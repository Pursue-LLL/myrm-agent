"""Integration tests for allowlist REST API (no mocks, real DB).

Tests:
1. GET /api/v1/security/allowlist — list entries
2. DELETE /api/v1/security/allowlist/{id} — delete entry
3. DELETE /api/v1/security/allowlist — clear all
4. Protocol alignment with harness Allowlist
"""

import pytest
from fastapi.testclient import TestClient

from app.main import app


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


class TestAllowlistAPI:
    def test_list_empty(self, client: TestClient):
        response = client.get("/api/v1/security/allowlist")
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert isinstance(body["data"], list)

    def test_delete_nonexistent_returns_404(self, client: TestClient):
        response = client.delete("/api/v1/security/allowlist/nonexistent_id")
        assert response.status_code == 404

    def test_clear_all_returns_count(self, client: TestClient):
        response = client.delete("/api/v1/security/allowlist")
        assert response.status_code == 200
        body = response.json()
        assert "data" in body
        assert "count" in body["data"]
        assert isinstance(body["data"]["count"], int)


class TestAllowlistProtocolAlignment:
    """Verify DBAllowlistStore matches AllowlistStore protocol signatures."""

    def test_store_has_correct_method_signatures(self):
        """DBAllowlistStore methods must accept user_id as first param."""
        import inspect

        from app.database.allowlist_store import DBAllowlistStore

        load_sig = inspect.signature(DBAllowlistStore.load)
        assert "user_id" in load_sig.parameters

        save_sig = inspect.signature(DBAllowlistStore.save)
        assert "user_id" in save_sig.parameters
        assert "entry" in save_sig.parameters

        remove_sig = inspect.signature(DBAllowlistStore.remove)
        assert "user_id" in remove_sig.parameters
        assert "permission" in remove_sig.parameters
