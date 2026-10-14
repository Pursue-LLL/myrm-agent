"""Unit and integration tests for SafeVaultPurgeService and /database/safe-purge endpoint."""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import patch

import pytest
from fastapi.testclient import TestClient
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from myrm_agent_harness.runtime.checkpointing import create_checkpointer
from myrm_agent_harness.runtime.context.session.session_continuity import sync_checkpoint_messages
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncEngine, create_async_engine

from app.platform_utils import _reset_checkpointer_for_testing, set_checkpointer
from app.services.system.vault_purge_service import (
    SafeVaultPurgeResult,
    SafeVaultPurgeService,
)
from tests.support.minimal_app import build_minimal_app


@pytest.fixture
async def purge_test_engine() -> AsyncEngine:
    """Fixture creating an isolated in-memory SQLite database populated with schema & data."""
    test_engine = create_async_engine("sqlite+aiosqlite:///:memory:", echo=False)

    async with test_engine.begin() as conn:
        # Whitelisted configuration & identity tables
        await conn.execute(text("CREATE TABLE agents (id TEXT PRIMARY KEY, name TEXT)"))
        await conn.execute(text("CREATE TABLE api_keys (id TEXT PRIMARY KEY, key TEXT)"))
        await conn.execute(text("CREATE TABLE user_configs (key TEXT PRIMARY KEY, value TEXT)"))
        await conn.execute(text("CREATE TABLE channel_pairings (id TEXT PRIMARY KEY, channel TEXT)"))

        # Conversation corpora & recall tables
        await conn.execute(text("CREATE TABLE chats (id TEXT PRIMARY KEY, title TEXT, sandbox_base_dir TEXT)"))
        await conn.execute(text("CREATE TABLE messages (id TEXT PRIMARY KEY, chat_id TEXT, content TEXT)"))
        await conn.execute(text("CREATE TABLE channel_messages (id INTEGER PRIMARY KEY AUTOINCREMENT, body TEXT)"))
        await conn.execute(text("CREATE TABLE conversation_recall_segments (id INTEGER PRIMARY KEY AUTOINCREMENT, text TEXT)"))
        await conn.execute(text("CREATE TABLE conversation_recall_documents (id INTEGER PRIMARY KEY AUTOINCREMENT, doc TEXT)"))
        await conn.execute(text("CREATE TABLE interrupted_turn_markers (id TEXT PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE conversation_forks (id TEXT PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE widget_kv_entries (id TEXT PRIMARY KEY)"))

        # Episodic memory tables
        await conn.execute(text("CREATE TABLE pending_memories (id TEXT PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE memory_extract_retries (id TEXT PRIMARY KEY)"))
        await conn.execute(text("CREATE TABLE memory_operation_events (id TEXT PRIMARY KEY)"))

        # Seed whitelisted data
        await conn.execute(text("INSERT INTO agents VALUES ('agent-1', 'Coder')"))
        await conn.execute(text("INSERT INTO api_keys VALUES ('k-1', 'sk-secret-test')"))
        await conn.execute(text("INSERT INTO user_configs VALUES ('theme', 'dark')"))
        await conn.execute(text("INSERT INTO channel_pairings VALUES ('p-1', 'feishu')"))

        # Seed conversation corpora
        await conn.execute(text("INSERT INTO chats VALUES ('chat-1', 'Test Chat', NULL)"))
        await conn.execute(text("INSERT INTO messages VALUES ('m-1', 'chat-1', 'hello')"))
        await conn.execute(text("INSERT INTO messages VALUES ('m-2', 'chat-1', 'world')"))
        await conn.execute(text("INSERT INTO channel_messages (body) VALUES ('channel note')"))
        await conn.execute(text("INSERT INTO conversation_recall_segments (text) VALUES ('recall segment 1')"))
        await conn.execute(text("INSERT INTO conversation_recall_documents (doc) VALUES ('recall doc 1')"))
        await conn.execute(text("INSERT INTO interrupted_turn_markers VALUES ('marker-1')"))
        await conn.execute(text("INSERT INTO pending_memories VALUES ('mem-1')"))

    yield test_engine
    await test_engine.dispose()


@pytest.mark.asyncio
async def test_safe_vault_purge_preserves_whitelist_and_clears_corpora(
    purge_test_engine: AsyncEngine,
) -> None:
    """Verify that safe vault purge wipes conversations & reset sequences while protecting user config."""
    with patch(
        "app.services.system.vault_purge_service.get_database_engine",
        return_value=purge_test_engine,
    ):
        result: SafeVaultPurgeResult = await SafeVaultPurgeService.purge_vault(
            purge_memories=True,
            purge_sandboxes=False,
            reclaim_disk=False,
        )

        assert result.success is True
        assert result.preserved_agents == 1
        assert result.preserved_api_keys == 1
        assert result.preserved_user_configs == 1
        assert result.preserved_channel_pairings == 1

        assert result.purged_chats == 1
        assert result.purged_messages == 2
        assert result.purged_channel_messages == 1
        assert result.purged_memory_events == 1

    # Verify physical database states
    async with purge_test_engine.connect() as conn:
        # Whitelisted tables must still have their data
        agents_count = await conn.scalar(text("SELECT COUNT(*) FROM agents"))
        assert agents_count == 1
        keys_count = await conn.scalar(text("SELECT COUNT(*) FROM api_keys"))
        assert keys_count == 1
        configs_count = await conn.scalar(text("SELECT COUNT(*) FROM user_configs"))
        assert configs_count == 1
        pairings_count = await conn.scalar(text("SELECT COUNT(*) FROM channel_pairings"))
        assert pairings_count == 1

        # Corpora tables must be zeroed out
        chats_count = await conn.scalar(text("SELECT COUNT(*) FROM chats"))
        assert chats_count == 0
        messages_count = await conn.scalar(text("SELECT COUNT(*) FROM messages"))
        assert messages_count == 0
        channel_msgs_count = await conn.scalar(text("SELECT COUNT(*) FROM channel_messages"))
        assert channel_msgs_count == 0
        recall_segs_count = await conn.scalar(text("SELECT COUNT(*) FROM conversation_recall_segments"))
        assert recall_segs_count == 0
        pending_mem_count = await conn.scalar(text("SELECT COUNT(*) FROM pending_memories"))
        assert pending_mem_count == 0


@pytest.mark.asyncio
async def test_safe_vault_purge_retains_memories_when_disabled(
    purge_test_engine: AsyncEngine,
) -> None:
    """Verify purge_memories=False leaves episodic memory tables intact."""
    with patch(
        "app.services.system.vault_purge_service.get_database_engine",
        return_value=purge_test_engine,
    ):
        result = await SafeVaultPurgeService.purge_vault(
            purge_memories=False,
            purge_sandboxes=False,
            reclaim_disk=False,
        )

        assert result.success is True
        assert result.purged_memory_events == 0

    async with purge_test_engine.connect() as conn:
        pending_mem_count = await conn.scalar(text("SELECT COUNT(*) FROM pending_memories"))
        assert pending_mem_count == 1


@pytest.mark.asyncio
async def test_safe_vault_purge_counts_every_memory_pipeline_row(
    purge_test_engine: AsyncEngine,
) -> None:
    """purged_memory_events is the number of rows actually deleted across the three memory tables."""
    async with purge_test_engine.begin() as conn:
        await conn.execute(text("INSERT INTO memory_extract_retries VALUES ('retry-1')"))
        await conn.execute(text("INSERT INTO memory_operation_events VALUES ('event-1')"))

    with patch(
        "app.services.system.vault_purge_service.get_database_engine",
        return_value=purge_test_engine,
    ):
        result = await SafeVaultPurgeService.purge_vault(
            purge_sandboxes=False,
            reclaim_disk=False,
        )

    assert result.purged_memory_events == 3


@pytest.fixture
async def sqlite_checkpointer(tmp_path: Path) -> AsyncIterator[BaseCheckpointSaver[str]]:
    """Real SQLite LangGraph checkpointer registered as the server's global checkpointer."""
    saver, cleanup = await create_checkpointer(
        mode="sqlite",
        sqlite_db_path=str(tmp_path / "checkpoints.db"),
    )
    set_checkpointer(saver)
    yield saver
    _reset_checkpointer_for_testing()
    await cleanup()


async def _store_conversation(saver: BaseCheckpointSaver[str], owner_id: str) -> None:
    await sync_checkpoint_messages(saver, owner_id, [HumanMessage("question"), AIMessage("answer")])


async def _is_stored(saver: BaseCheckpointSaver[str], thread_id: str) -> bool:
    return await saver.aget_tuple({"configurable": {"thread_id": thread_id}}) is not None


@pytest.mark.asyncio
async def test_safe_vault_purge_drops_the_checkpoint_threads_of_every_chat(
    purge_test_engine: AsyncEngine,
    sqlite_checkpointer: BaseCheckpointSaver[str],
) -> None:
    """A purged chat leaves no conversation state in the checkpoint store; other threads are untouched."""
    await _store_conversation(sqlite_checkpointer, "chat-1")
    await _store_conversation(sqlite_checkpointer, "kanban-task-1")
    assert await _is_stored(sqlite_checkpointer, "chat-1")

    with patch(
        "app.services.system.vault_purge_service.get_database_engine",
        return_value=purge_test_engine,
    ):
        result = await SafeVaultPurgeService.purge_vault(
            purge_sandboxes=False,
            reclaim_disk=False,
        )

    assert result.success is True
    assert result.checkpoint_cleared_chats == 1
    assert not await _is_stored(sqlite_checkpointer, "chat-1")
    assert not await _is_stored(sqlite_checkpointer, "chat_chat-1")
    assert await _is_stored(sqlite_checkpointer, "kanban-task-1")


@pytest.mark.asyncio
async def test_safe_vault_purge_drops_checkpoints_before_deleting_the_chat_rows(
    purge_test_engine: AsyncEngine,
    sqlite_checkpointer: BaseCheckpointSaver[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An interrupted purge must never strand checkpoints whose chat can no longer be listed."""
    await _store_conversation(sqlite_checkpointer, "chat-1")
    chats_listed_during_drop: list[int] = []
    delete_thread = sqlite_checkpointer.adelete_thread

    async def recording_delete_thread(thread_id: str) -> None:
        async with purge_test_engine.connect() as conn:
            chats_listed_during_drop.append(await conn.scalar(text("SELECT COUNT(*) FROM chats")) or 0)
        await delete_thread(thread_id)

    monkeypatch.setattr(sqlite_checkpointer, "adelete_thread", recording_delete_thread)

    with patch(
        "app.services.system.vault_purge_service.get_database_engine",
        return_value=purge_test_engine,
    ):
        await SafeVaultPurgeService.purge_vault(
            purge_sandboxes=False,
            reclaim_disk=False,
        )

    assert chats_listed_during_drop == [1, 1]  # one entry per thread alias, the chat row still present


@pytest.mark.asyncio
async def test_safe_vault_purge_keeps_going_when_one_chat_checkpoint_cannot_be_cleared(
    purge_test_engine: AsyncEngine,
    sqlite_checkpointer: BaseCheckpointSaver[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One failing chat is reported as not cleared; the rest of the purge still completes."""
    async with purge_test_engine.begin() as conn:
        await conn.execute(text("INSERT INTO chats VALUES ('chat-2', 'Second Chat', NULL)"))
    await _store_conversation(sqlite_checkpointer, "chat-1")
    await _store_conversation(sqlite_checkpointer, "chat-2")

    delete_thread = sqlite_checkpointer.adelete_thread

    async def flaky_delete_thread(thread_id: str) -> None:
        if "chat-2" in thread_id:
            raise OSError("disk I/O error")
        await delete_thread(thread_id)

    monkeypatch.setattr(sqlite_checkpointer, "adelete_thread", flaky_delete_thread)

    with patch(
        "app.services.system.vault_purge_service.get_database_engine",
        return_value=purge_test_engine,
    ):
        result = await SafeVaultPurgeService.purge_vault(
            purge_sandboxes=False,
            reclaim_disk=False,
        )

    assert result.success is True
    assert result.purged_chats == 2
    assert result.checkpoint_cleared_chats == 1
    assert not await _is_stored(sqlite_checkpointer, "chat-1")
    assert await _is_stored(sqlite_checkpointer, "chat-2")
    async with purge_test_engine.connect() as conn:
        assert await conn.scalar(text("SELECT COUNT(*) FROM chats")) == 0


@pytest.mark.asyncio
async def test_safe_vault_purge_without_a_registered_checkpointer_still_purges(
    purge_test_engine: AsyncEngine,
) -> None:
    """A missing checkpoint store is reported as zero cleared threads and never aborts the purge."""
    _reset_checkpointer_for_testing()

    with patch(
        "app.services.system.vault_purge_service.get_database_engine",
        return_value=purge_test_engine,
    ):
        result = await SafeVaultPurgeService.purge_vault(
            purge_sandboxes=False,
            reclaim_disk=False,
        )

    assert result.success is True
    assert result.purged_chats == 1
    assert result.checkpoint_cleared_chats == 0


def test_safe_vault_purge_api_endpoint() -> None:
    """Test the POST /api/v1/health/database/safe-purge HTTP endpoint."""
    app = build_minimal_app(preset="health")
    mock_result = SafeVaultPurgeResult(
        success=True,
        purged_chats=5,
        purged_messages=25,
        purged_channel_messages=3,
        purged_memory_events=2,
        checkpoint_cleared_chats=5,
        fts_tables_purged=["messages_fts"],
        cursors_reset=["channel_messages"],
        cleared_sandboxes=0,
        preserved_agents=2,
        preserved_api_keys=1,
        preserved_user_configs=4,
        preserved_channel_pairings=1,
        duration_ms=45.2,
    )

    with patch(
        "app.services.system.vault_purge_service.SafeVaultPurgeService.purge_vault",
        return_value=mock_result,
    ):
        client = TestClient(app)
        response = client.post("/api/v1/health/database/safe-purge")
        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "success"
        assert data["purged_chats"] == 5
        assert data["purged_messages"] == 25
        assert data["purged_memory_events"] == 2
        assert data["checkpoint_cleared_chats"] == 5
        assert data["preserved_agents"] == 2
        assert data["preserved_api_keys"] == 1
        assert "duration_ms" in data
