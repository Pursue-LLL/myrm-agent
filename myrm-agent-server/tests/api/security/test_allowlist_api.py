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


@pytest.fixture(autouse=False)
def _clean_allowlist_table() -> None:
    from app.database.connection import init_database

    asyncio.run(init_database())
    asyncio.run(clear_allowlist_entries())
    yield
    asyncio.run(clear_allowlist_entries())


class TestAllowlistAPI:
    def test_list_empty(self, client: TestClient):
        asyncio.run(clear_allowlist_entries())
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
        assert "agent_id" in remove_sig.parameters


class TestAllowlistPatternIntegration:
    def test_list_returns_pattern_granularity(self, client: TestClient) -> None:
        asyncio.run(clear_allowlist_entries())
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
        asyncio.run(clear_allowlist_entries())

    def test_delete_pattern_entry_removes_from_list(self, client: TestClient) -> None:
        asyncio.run(clear_allowlist_entries())
        entry_id = asyncio.run(seed_pattern_allowlist_entry())

        delete_response = client.delete(f"/api/v1/security/allowlist/{entry_id}")
        assert delete_response.status_code == 200
        assert delete_response.json()["data"]["deleted"] is True

        list_response = client.get("/api/v1/security/allowlist")
        assert list_response.status_code == 200
        assert list_response.json()["data"] == []
        asyncio.run(clear_allowlist_entries())

    def test_list_and_delete_agent_scoped_entry(self, client: TestClient) -> None:
        asyncio.run(clear_allowlist_entries())
        import uuid

        from app.database.models import UserToolAllowlist
        from app.platform_utils import get_session_factory

        entry_id = uuid.uuid4().hex
        factory = get_session_factory()

        async def _seed():
            async with factory() as session:
                session.add(
                    UserToolAllowlist(
                        id=entry_id,
                        permission="mcp_invoke",
                        tool_name="mcp__github__create_issue",
                        tool_args_hash="",
                        command_pattern="",
                        agent_id="code_worker_subagent",
                    )
                )
                await session.commit()

        asyncio.run(_seed())

        response = client.get("/api/v1/security/allowlist")
        assert response.status_code == 200
        rows = response.json()["data"]
        assert len(rows) == 1
        assert rows[0]["id"] == entry_id
        assert rows[0]["agent_id"] == "code_worker_subagent"

        del_resp = client.delete(f"/api/v1/security/allowlist/{entry_id}")
        assert del_resp.status_code == 200
        asyncio.run(clear_allowlist_entries())

    def test_list_and_manage_time_bound_allowlist_entry(self, client: TestClient) -> None:
        asyncio.run(clear_allowlist_entries())
        import uuid
        from datetime import datetime, timedelta, timezone

        from app.database.models import UserToolAllowlist
        from app.platform_utils import get_session_factory

        entry_id = uuid.uuid4().hex
        factory = get_session_factory()
        future_dt = datetime.now(timezone.utc) + timedelta(hours=2)

        async def _seed():
            async with factory() as session:
                session.add(
                    UserToolAllowlist(
                        id=entry_id,
                        permission="email_send",
                        tool_name="send_mail",
                        tool_args_hash="",
                        command_pattern="",
                        agent_id="",
                        expires_at=future_dt,
                    )
                )
                await session.commit()

        asyncio.run(_seed())

        response = client.get("/api/v1/security/allowlist")
        assert response.status_code == 200
        rows = response.json()["data"]
        assert len(rows) == 1
        assert rows[0]["id"] == entry_id
        assert rows[0]["expires_at"] is not None
        assert rows[0]["permission"] == "email_send"

        del_resp2 = client.delete(f"/api/v1/security/allowlist/{entry_id}")
        assert del_resp2.status_code == 200
        assert del_resp2.json()["data"]["deleted"] is True
        asyncio.run(clear_allowlist_entries())
