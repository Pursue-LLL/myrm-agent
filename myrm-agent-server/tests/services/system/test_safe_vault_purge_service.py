"""SafeVaultPurgeService against the server's complete schema: what the purge removes, what it must leave alone.

The schema is the real one (``tests.support.real_schema_db``): a miniature schema built by hand agrees with any
misspelled table name, which is how a purge can report success while a table keeps its rows.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
import pytest_asyncio
from langchain_core.messages import AIMessage, HumanMessage
from langgraph.checkpoint.base import BaseCheckpointSaver
from myrm_agent_harness.runtime.checkpointing import create_checkpointer
from myrm_agent_harness.runtime.context.session.session_continuity import sync_checkpoint_messages
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.platform_utils import _reset_checkpointer_for_testing, set_checkpointer
from app.services.chat import chat_disposal
from app.services.chat.chat_bound_rows import CHAT_BOUND_TABLES
from app.services.chat.chat_disposal import ChatFilesRemoval
from app.services.system.vault_purge_service import SafeVaultPurgeService
from tests.support.real_schema_db import create_real_schema_engine, seed_row

SANDBOX_DIR = "/work/repo"
CONVERSATION_TABLES = (
    "chats",
    "messages",
    "channel_messages",
    "conversation_recall_documents",
    "conversation_recall_segments",
    "pending_memories",
    "memory_extract_retries",
    "memory_operation_events",
    *(bound.table for bound in CHAT_BOUND_TABLES),
)
KEPT_TABLES = ("agents", "api_keys", "user_configs", "channel_pairings", "cron_jobs", "artifacts")
FTS_QUERIES = {
    "messages_fts": "apple",
    "conversation_recall_fts": "banana",
    "conversation_recall_segments_fts": "cherry",
}


async def _seed_conversation(conn: AsyncConnection, chat_id: str = "chat-1") -> None:
    await seed_row(conn, "chats", id=chat_id, sandbox_base_dir=SANDBOX_DIR)
    await seed_row(conn, "messages", id=f"m-{chat_id}", chat_id=chat_id, content="apple pie recipe")
    await seed_row(conn, "messages", id=f"m2-{chat_id}", chat_id=chat_id, content="second reply")
    await seed_row(conn, "channel_messages", chat_id=chat_id, channel="wechat", id=f"c-{chat_id}")
    await seed_row(conn, "conversation_recall_documents", chat_id=chat_id, searchable_text="banana bread notes")
    await seed_row(
        conn, "conversation_recall_segments", chat_id=chat_id, message_id=f"m-{chat_id}", role="user", segment_text="cherry"
    )
    for bound in CHAT_BOUND_TABLES:
        await seed_row(conn, bound.table, **{bound.chat_column: chat_id})
    for pipeline_table in SafeVaultPurgeService.MEMORY_PIPELINE_TABLES:
        await seed_row(conn, pipeline_table)


async def _seed_kept_data(conn: AsyncConnection) -> None:
    for table in ("agents", "api_keys", "user_configs", "channel_pairings"):
        await seed_row(conn, table)
    await seed_row(conn, "cron_jobs", chat_id="chat-1")
    await seed_row(conn, "artifacts", chat_id="chat-1")


async def _count(engine: AsyncEngine, table: str) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text(f"SELECT COUNT(*) FROM {table}"))).scalar_one()


async def _fts_matches(engine: AsyncEngine, table: str, term: str) -> int:
    async with engine.connect() as conn:
        return (await conn.execute(text(f"SELECT COUNT(*) FROM {table} WHERE {table} MATCH :term"), {"term": term})).scalar_one()


@pytest_asyncio.fixture
async def purge_engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    engine = await create_real_schema_engine(tmp_path / "purge.db")
    async with engine.begin() as conn:
        await _seed_kept_data(conn)
        await _seed_conversation(conn)
    with patch("app.services.system.vault_purge_service.get_database_engine", return_value=engine):
        yield engine
    await engine.dispose()


@pytest.fixture
def remove_files() -> AsyncMock:
    """The file removal is covered by the disposal tests; here it must only be called with the right input."""
    spy = AsyncMock(return_value=ChatFilesRemoval(removed_worktrees=1, kept_worktrees=2))
    with patch.object(chat_disposal, "remove_chat_files", spy):
        yield spy


@pytest.mark.asyncio
async def test_purge_empties_every_conversation_table_and_reports_the_counts(
    purge_engine: AsyncEngine, remove_files: AsyncMock
) -> None:
    result = await SafeVaultPurgeService.purge_vault()

    assert result.success is True, result.error
    assert result.purged_chats == 1
    assert result.purged_messages == 2
    assert result.purged_channel_messages == 1
    assert result.purged_memory_events == len(SafeVaultPurgeService.MEMORY_PIPELINE_TABLES)
    for table in CONVERSATION_TABLES:
        assert await _count(purge_engine, table) == 0, f"{table} kept rows after the purge"


@pytest.mark.asyncio
async def test_purge_keeps_configuration_and_records_that_outlive_a_chat(
    purge_engine: AsyncEngine, remove_files: AsyncMock
) -> None:
    result = await SafeVaultPurgeService.purge_vault()

    assert (result.preserved_agents, result.preserved_api_keys) == (1, 1)
    assert (result.preserved_user_configs, result.preserved_channel_pairings) == (1, 1)
    for table in KEPT_TABLES:
        assert await _count(purge_engine, table) == 1, f"{table} lost its rows"


@pytest.mark.asyncio
async def test_purge_leaves_no_searchable_trace_in_any_full_text_index(
    purge_engine: AsyncEngine, remove_files: AsyncMock
) -> None:
    for table, term in FTS_QUERIES.items():
        assert await _fts_matches(purge_engine, table, term) == 1, f"{table} was not seeded"

    result = await SafeVaultPurgeService.purge_vault()

    assert sorted(result.fts_tables_purged) == sorted(FTS_QUERIES)
    for table, term in FTS_QUERIES.items():
        assert await _fts_matches(purge_engine, table, term) == 0, f"{table} still finds {term!r}"


@pytest.mark.asyncio
async def test_purge_resets_the_consumer_cursors_of_the_wiped_tables(
    purge_engine: AsyncEngine, remove_files: AsyncMock
) -> None:
    result = await SafeVaultPurgeService.purge_vault()

    assert sorted(result.cursors_reset) == ["channel_messages", "conversation_recall_documents", "conversation_recall_segments"]


@pytest.mark.asyncio
async def test_purge_hands_every_sandbox_to_the_file_removal_and_reports_what_stayed(
    purge_engine: AsyncEngine, remove_files: AsyncMock
) -> None:
    async with purge_engine.begin() as conn:
        await seed_row(conn, "chats", id="chat-no-sandbox")

    result = await SafeVaultPurgeService.purge_vault()

    remove_files.assert_awaited_once_with({"chat-1": SANDBOX_DIR, "chat-no-sandbox": None})
    assert result.cleared_sandboxes == 1
    assert result.kept_sandboxes == 2


@pytest.mark.asyncio
async def test_purge_reports_a_database_failure_without_raising() -> None:
    engine = MagicMock()
    engine.connect.side_effect = RuntimeError("Database I/O disk failure")

    with patch("app.services.system.vault_purge_service.get_database_engine", return_value=engine):
        result = await SafeVaultPurgeService.purge_vault()

    assert result.success is False
    assert "Database I/O disk failure" in (result.error or "")


# ── Checkpoint threads ──────────────────────────────────────────────


@pytest_asyncio.fixture
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
async def test_purge_drops_the_checkpoint_threads_of_every_chat(
    purge_engine: AsyncEngine,
    remove_files: AsyncMock,
    sqlite_checkpointer: BaseCheckpointSaver[str],
) -> None:
    """A purged chat leaves no conversation state in the checkpoint store; other threads are untouched."""
    await _store_conversation(sqlite_checkpointer, "chat-1")
    await _store_conversation(sqlite_checkpointer, "kanban-task-1")
    assert await _is_stored(sqlite_checkpointer, "chat-1")

    result = await SafeVaultPurgeService.purge_vault()

    assert result.success is True
    assert result.checkpoint_cleared_chats == 1
    assert not await _is_stored(sqlite_checkpointer, "chat-1")
    assert not await _is_stored(sqlite_checkpointer, "chat_chat-1")
    assert await _is_stored(sqlite_checkpointer, "kanban-task-1")


@pytest.mark.asyncio
async def test_purge_drops_checkpoints_before_deleting_the_chat_rows(
    purge_engine: AsyncEngine,
    remove_files: AsyncMock,
    sqlite_checkpointer: BaseCheckpointSaver[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An interrupted purge must never strand checkpoints whose chat can no longer be listed."""
    await _store_conversation(sqlite_checkpointer, "chat-1")
    chats_listed_during_drop: list[int] = []
    delete_thread = sqlite_checkpointer.adelete_thread

    async def recording_delete_thread(thread_id: str) -> None:
        chats_listed_during_drop.append(await _count(purge_engine, "chats"))
        await delete_thread(thread_id)

    monkeypatch.setattr(sqlite_checkpointer, "adelete_thread", recording_delete_thread)

    await SafeVaultPurgeService.purge_vault()

    assert chats_listed_during_drop == [1, 1]  # one entry per thread alias, the chat row still present


@pytest.mark.asyncio
async def test_purge_keeps_going_when_one_chat_checkpoint_cannot_be_cleared(
    purge_engine: AsyncEngine,
    remove_files: AsyncMock,
    sqlite_checkpointer: BaseCheckpointSaver[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """One failing chat is reported as not cleared; the rest of the purge still completes."""
    async with purge_engine.begin() as conn:
        await _seed_conversation(conn, "chat-2")
    await _store_conversation(sqlite_checkpointer, "chat-1")
    await _store_conversation(sqlite_checkpointer, "chat-2")
    delete_thread = sqlite_checkpointer.adelete_thread

    async def flaky_delete_thread(thread_id: str) -> None:
        if "chat-2" in thread_id:
            raise OSError("disk I/O error")
        await delete_thread(thread_id)

    monkeypatch.setattr(sqlite_checkpointer, "adelete_thread", flaky_delete_thread)

    result = await SafeVaultPurgeService.purge_vault()

    assert result.success is True
    assert result.purged_chats == 2
    assert result.checkpoint_cleared_chats == 1
    assert not await _is_stored(sqlite_checkpointer, "chat-1")
    assert await _is_stored(sqlite_checkpointer, "chat-2")
    assert await _count(purge_engine, "chats") == 0


@pytest.mark.asyncio
async def test_purge_without_a_registered_checkpointer_still_purges(
    purge_engine: AsyncEngine, remove_files: AsyncMock
) -> None:
    """A missing checkpoint store is reported as zero cleared threads and never aborts the purge."""
    _reset_checkpointer_for_testing()

    result = await SafeVaultPurgeService.purge_vault()

    assert result.success is True
    assert result.purged_chats == 1
    assert result.checkpoint_cleared_chats == 0
