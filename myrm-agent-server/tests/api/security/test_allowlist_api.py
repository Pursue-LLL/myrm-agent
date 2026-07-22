"""Integration tests for allowlist REST API (no mocks, real DB).

Tests:
1. GET /api/v1/security/allowlist — list entries
2. DELETE /api/v1/security/allowlist/{id} — delete entry
3. DELETE /api/v1/security/allowlist — clear all
4. Protocol alignment with harness Allowlist
5. Pattern granularity list/delete round-trip (Closure Pack regression guard)
"""

from __future__ import annotations

import asyncio

import pytest
from fastapi.testclient import TestClient

from tests.support.allowlist_test_seed import (
    PATTERN_ENTRY_COMMAND_PATTERN,
    PATTERN_ENTRY_PERMISSION,
    PATTERN_ENTRY_TOOL,
    clear_allowlist_entries,
    seed_pattern_allowlist_entry,
)
from tests.support.minimal_app import build_minimal_app

app = build_minimal_app(preset="security")


@pytest.fixture
def client() -> TestClient:
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clean_allowlist_table() -> None:
    asyncio.run(clear_allowlist_entries())
    yield
    asyncio.run(clear_allowlist_entries())


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
        assert "command_pattern" in remove_sig.parameters


class TestAllowlistPatternIntegration:
    def test_list_returns_pattern_granularity(self, client: TestClient) -> None:
        entry_id = asyncio.run(seed_pattern_allowlist_entry())

        response = client.get("/api/v1/security/allowlist")
        assert response.status_code == 200
        rows = response.json()["data"]
        assert len(rows) == 1
        row = rows[0]
        assert row["id"] == entry_id
        assert row["permission"] == PATTERN_ENTRY_PERMISSION
        assert row["tool_name"] == PATTERN_ENTRY_TOOL
        assert row["tool_args_hash"] is None
        assert row["command_pattern"] == PATTERN_ENTRY_COMMAND_PATTERN
        assert row["granularity"] == "pattern"

    def test_delete_pattern_entry_removes_from_list(self, client: TestClient) -> None:
        entry_id = asyncio.run(seed_pattern_allowlist_entry())

        delete_response = client.delete(f"/api/v1/security/allowlist/{entry_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["data"]["deleted"] is True

        list_response = client.get("/api/v1/security/allowlist")
        assert list_response.status_code == 200
        assert list_response.json()["data"] == []
