"""HTTP contract of the safe vault purge endpoint.

What the purge deletes is tested against the complete schema in
``tests/services/system/test_safe_vault_purge_service.py``; this module covers the route:
- POST /api/v1/health/database/safe-purge reports the audit summary, including the sandboxes it kept
- Refusal (409) while a conversation is running, with nothing deleted
"""

from __future__ import annotations

from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import insert, text

from app.database.connection import get_database_engine
from app.database.models.chat import Chat
from app.services.chat import chat_disposal
from app.services.system.vault_purge_service import (
    SafeVaultPurgeResult,
    SafeVaultPurgeService,
    VaultPurgeBusyError,
)


@pytest.fixture
def app() -> FastAPI:
    from tests.support.minimal_app import build_minimal_app

    return build_minimal_app(preset="health")


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


def test_safe_purge_vault_api_endpoint(client: TestClient) -> None:
    """Test POST /api/v1/health/database/safe-purge API endpoint."""
    fake_result = SafeVaultPurgeResult(
        success=True,
        purged_chats=5,
        purged_messages=25,
        purged_channel_messages=3,
        cleared_sandboxes=3,
        kept_sandboxes=2,
        fts_tables_purged=["messages_fts"],
        cursors_reset=["conversation_recall_segments"],
        preserved_agents=2,
        preserved_api_keys=3,
        preserved_user_configs=4,
        preserved_channel_pairings=1,
        duration_ms=42.5,
    )

    with patch.object(
        SafeVaultPurgeService,
        "purge_vault",
        new=AsyncMock(return_value=fake_result),
    ):
        resp = client.post("/api/v1/health/database/safe-purge")
        assert resp.status_code == 200
        data = resp.json()
        assert data["status"] == "success"
        assert data["purged_chats"] == 5
        assert data["purged_messages"] == 25
        assert data["cleared_sandboxes"] == 3
        assert data["kept_sandboxes"] == 2
        assert data["preserved_agents"] == 2
        assert data["preserved_api_keys"] == 3
        assert data["preserved_user_configs"] == 4
        assert "messages_fts" in data["fts_tables_purged"]


class _BusyGateway:
    """Stand-in for the agent gateway with two conversations mid-turn."""

    def active_session_ids(self) -> frozenset[str]:
        return frozenset({"chat-running-1", "chat-running-2"})


@pytest.mark.asyncio
async def test_safe_vault_purge_refuses_while_a_conversation_is_running() -> None:
    """A turn that is still writing would race the wipe, so nothing is touched and the caller is told why."""
    engine = get_database_engine()
    async with engine.begin() as conn:
        await conn.execute(insert(Chat).values(id="chat-busy-guard", title="Running chat"))

    try:
        with (
            patch("app.services.system.vault_purge_service.get_agent_gateway", return_value=_BusyGateway()),
            patch.object(chat_disposal, "clear_runtime_caches", new=AsyncMock()) as stop_runtime,
            pytest.raises(VaultPurgeBusyError) as busy,
        ):
            await SafeVaultPurgeService.purge_vault()

        assert busy.value.running == 2
        stop_runtime.assert_not_awaited()
        async with engine.connect() as conn:
            assert await conn.scalar(text("SELECT COUNT(*) FROM chats WHERE id='chat-busy-guard'")) == 1
    finally:
        async with engine.begin() as conn:
            await conn.execute(text("DELETE FROM chats WHERE id='chat-busy-guard'"))


def test_safe_purge_vault_api_answers_409_while_a_conversation_is_running(client: TestClient) -> None:
    with patch("app.services.system.vault_purge_service.get_agent_gateway", return_value=_BusyGateway()):
        resp = client.post("/api/v1/health/database/safe-purge")

    assert resp.status_code == 409
    assert "2 conversations are running" in resp.text
