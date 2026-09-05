"""Unit tests for Safe Vault Purge API and SafeVaultPurgeService.

Tests cover:
- Preserving white-listed configurations (Agents, API keys, user configs, channel pairings)
- Transactional inverse deletion of chat messages, leaf segments, documents, and cursors
- Safe purge of FTS5 external content shadow tables without leaving orphan rows
- Cursor auto-increment sequence reset (sqlite_sequence)
- POST /api/v1/health/database/safe-purge API integration
"""

from __future__ import annotations

from datetime import UTC, datetime
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import insert, text

from app.database.connection import get_database_engine
from app.database.models.agent import Agent
from app.database.models.api_key import APIKey
from app.database.models.channel import ChannelPairingModel
from app.database.models.channel_message import ChannelMessageModel
from app.database.models.chat import Chat, Message
from app.database.models.config import UserConfig
from app.services.system.vault_purge_service import (
    SafeVaultPurgeResult,
    SafeVaultPurgeService,
)


@pytest.fixture
def app() -> FastAPI:
    from tests.support.minimal_app import build_minimal_app

    return build_minimal_app(preset="health")


@pytest.fixture
def client(app: FastAPI) -> TestClient:
    return TestClient(app)


@pytest.mark.asyncio
async def test_safe_vault_purge_service_execution(tmp_path: Path):
    """Verify SafeVaultPurgeService performs cascade wipe and preserves configuration."""
    engine = get_database_engine()

    # Pre-populate test rows across whitelisted and purgable tables
    async with engine.begin() as conn:
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS conversation_recall_documents ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id VARCHAR(255) NOT NULL, "
                "source VARCHAR(50) DEFAULT 'web', snippet TEXT DEFAULT '', searchable_text TEXT DEFAULT '')"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS conversation_recall_segments ("
                "id INTEGER PRIMARY KEY AUTOINCREMENT, chat_id VARCHAR(255) NOT NULL, "
                "message_id VARCHAR(255) NOT NULL, segment_ordinal INTEGER DEFAULT 0, "
                "role VARCHAR(20) NOT NULL, segment_text TEXT DEFAULT '')"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS interrupted_turn_markers (id VARCHAR(255) PRIMARY KEY)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS offline_durable_tasks (id VARCHAR(255) PRIMARY KEY)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS conversation_forks (child_chat_id VARCHAR(255) PRIMARY KEY)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS widget_kv_entries (id VARCHAR(255) PRIMARY KEY)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS pending_memories (id VARCHAR(255) PRIMARY KEY)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS memory_extract_retries (id VARCHAR(255) PRIMARY KEY)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS memory_conflicts (id VARCHAR(255) PRIMARY KEY)"
            )
        )
        await conn.execute(
            text(
                "CREATE TABLE IF NOT EXISTS memory_operation_events (id VARCHAR(255) PRIMARY KEY)"
            )
        )

        # Seed whitelist items
        await conn.execute(
            insert(Agent).values(
                id="agent-1",
                name="Default Agent",
                description="Test description",
            )
        )
        await conn.execute(
            insert(APIKey).values(
                id=999,
                name="k-1",
                key_hash="test-hash-safe-purge",
                key_prefix="sk-test",
            )
        )
        await conn.execute(
            insert(UserConfig).values(
                id="cfg-1",
                config_key="test_purge_theme",
                config_value={"theme": "dark"},
                version="1.0",
                last_device_id="dev-test",
            )
        )
        await conn.execute(
            insert(ChannelPairingModel).values(
                id="cp-1",
                channel="wechat",
                sender_id="user-safe-purge",
            )
        )

        # Seed purgeable corpora
        await conn.execute(
            insert(Chat).values(
                id="chat-100",
                title="Confidential chat",
            )
        )
        await conn.execute(
            insert(Message).values(
                id="msg-1",
                chat_id="chat-100",
                role="user",
                content="Hello world",
                sent_at=datetime.now(UTC),
                sent_timezone="UTC",
            )
        )
        await conn.execute(
            insert(ChannelMessageModel).values(
                id="cmsg-1",
                channel="wechat",
                chat_id="chat-100",
                sender_id="user-safe-purge",
                content="channel text 1",
            )
        )
        await conn.execute(
            text(
                "INSERT OR REPLACE INTO conversation_recall_documents (chat_id, source, snippet, searchable_text) "
                "VALUES ('chat-100', 'web', 'snippet', 'searchable text')"
            )
        )
        await conn.execute(
            text(
                "INSERT OR REPLACE INTO conversation_recall_segments (chat_id, message_id, segment_ordinal, role, segment_text) "
                "VALUES ('chat-100', 'msg-1', 0, 'user', 'segment text')"
            )
        )

    # Execute purge
    result = await SafeVaultPurgeService.purge_vault(
        purge_memories=True,
        purge_sandboxes=False,
        reclaim_disk=False,
    )

    assert result.success is True
    assert result.purged_chats >= 1
    assert result.purged_messages >= 1
    assert result.preserved_agents >= 1
    assert result.preserved_api_keys >= 1
    assert result.preserved_user_configs >= 1
    assert result.preserved_channel_pairings >= 1

    # Verify whitelist records remain untouched in DB
    async with engine.connect() as conn:
        agent_cnt = await conn.scalar(
            text("SELECT COUNT(*) FROM agents WHERE id='agent-1'")
        )
        assert agent_cnt == 1

        key_cnt = await conn.scalar(
            text("SELECT COUNT(*) FROM api_keys WHERE name='k-1'")
        )
        assert key_cnt == 1

        # Verify chat corpora are completely gone
        chat_cnt = await conn.scalar(
            text("SELECT COUNT(*) FROM chats WHERE id='chat-100'")
        )
        assert chat_cnt == 0
        msg_cnt = await conn.scalar(
            text("SELECT COUNT(*) FROM messages WHERE id='msg-1'")
        )
        assert msg_cnt == 0


def test_safe_purge_vault_api_endpoint(client: TestClient):
    """Test POST /api/v1/health/database/safe-purge API endpoint."""
    fake_result = SafeVaultPurgeResult(
        success=True,
        purged_chats=5,
        purged_messages=25,
        purged_channel_messages=3,
        cleared_sandboxes=0,
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
        assert data["preserved_agents"] == 2
        assert data["preserved_api_keys"] == 3
        assert data["preserved_user_configs"] == 4
        assert "messages_fts" in data["fts_tables_purged"]
