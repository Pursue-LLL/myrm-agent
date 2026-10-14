"""The list of tables erased with a chat must match the real schema, and nothing may slip past it.

A deletion list written by hand fails silently: a misspelled table name matches nothing, and a table added later
is never mentioned. Both are caught here against the complete schema.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from pathlib import Path

import pytest
import pytest_asyncio
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncConnection, AsyncEngine

from app.services.chat.chat_bound_rows import CHAT_BOUND_TABLES, delete_trashed_chat_bound_rows
from tests.support.real_schema_db import create_real_schema_engine, seed_row

CHAT_LINK_COLUMNS = frozenset({"chat_id", "session_id", "thread_id", "source_chat_id", "parent_chat_id", "child_chat_id"})

# Tables with a chat column that have their own, tested route out when the chat goes.
ERASED_BY_ANOTHER_ROUTE = {
    "messages": "deleted with the chat row",
    "conversation_forks": "ON DELETE CASCADE from chats",
    "interrupted_turn_markers": "ON DELETE CASCADE from chats",
    "conversation_recall_documents": "ConversationRecallIndexService.delete_chat, ON DELETE CASCADE from chats",
    "conversation_recall_segments": "ConversationRecallIndexService.delete_chat, ON DELETE CASCADE from chats",
    "memory_extract_retries": "chat_disposal.forget_chat_memories clears the retry queue; the safe purge empties it",
    "channel_messages": "keyed by the channel's own conversation id, not a chat id; only the safe purge wipes it",
}

# Tables that name a chat but are meant to outlive it.
RETAINED_ON_PURPOSE = {
    "artifacts": "cross-session artifact hub; its files are removed with the chat workspace, the index is user-managed",
    "media_library": "gallery of generated media with its own management; not conversation content",
    "batch_image_jobs": "image batch jobs belong to the media library, not to the conversation",
    "cron_jobs": "a schedule is user configuration; the chat is only its delivery target",
    "assessment_import_ledger": "project-level import dedup ledger; deleting it would allow duplicate imports",
    "risk_hits": "security audit trail",
    "browser_runtime_records": "numeric usage ledger without content",
    "sandbox_workload_records": "numeric usage ledger without content",
}


@pytest_asyncio.fixture
async def engine(tmp_path: Path) -> AsyncIterator[AsyncEngine]:
    created = await create_real_schema_engine(tmp_path / "chat_bound.db")
    yield created
    await created.dispose()


async def _tables_with_chat_columns(engine: AsyncEngine) -> dict[str, set[str]]:
    async with engine.connect() as conn:
        names = [r[0] for r in (await conn.execute(text("SELECT name FROM sqlite_master WHERE type='table'"))).fetchall()]
        found: dict[str, set[str]] = {}
        for name in names:
            columns = {r[1] for r in (await conn.execute(text(f"PRAGMA table_info({name})"))).fetchall()}
            if columns & CHAT_LINK_COLUMNS:
                found[name] = columns
    return found


@pytest.mark.asyncio
async def test_every_listed_table_and_column_exists_in_the_schema(engine: AsyncEngine) -> None:
    schema = await _tables_with_chat_columns(engine)

    for bound in CHAT_BOUND_TABLES:
        assert bound.table in schema, f"{bound.table} is not a table with a chat column"
        assert bound.chat_column in schema[bound.table], f"{bound.table} has no column {bound.chat_column}"


@pytest.mark.asyncio
async def test_no_table_with_a_chat_column_is_unclassified(engine: AsyncEngine) -> None:
    """A new table that stores a chat id must be listed for deletion or named as an exception with a reason."""
    listed = {bound.table for bound in CHAT_BOUND_TABLES}
    classified = [listed, set(ERASED_BY_ANOTHER_ROUTE), set(RETAINED_ON_PURPOSE)]

    for index, group in enumerate(classified):
        for other in classified[index + 1 :]:
            assert not group & other, f"classified twice: {sorted(group & other)}"

    unclassified = set(await _tables_with_chat_columns(engine)) - listed - set(ERASED_BY_ANOTHER_ROUTE) - set(RETAINED_ON_PURPOSE)
    assert not unclassified, f"tables with a chat column that nothing erases or justifies keeping: {sorted(unclassified)}"


TRASHED_AT = "2026-01-01 00:00:00"


async def _seed_chat(conn: AsyncConnection, chat_id: str, *, trashed: bool) -> None:
    await seed_row(conn, "chats", id=chat_id, deleted_at=TRASHED_AT if trashed else None)


@pytest.mark.asyncio
async def test_delete_removes_the_rows_of_trashed_chats_and_spares_the_rest(engine: AsyncEngine) -> None:
    async with engine.begin() as conn:
        await _seed_chat(conn, "gone-1", trashed=True)
        await _seed_chat(conn, "gone-2", trashed=True)
        await _seed_chat(conn, "stays", trashed=True)
        await _seed_chat(conn, "restored", trashed=False)
        for bound in CHAT_BOUND_TABLES:
            for chat_id in ("gone-1", "gone-2", "stays", "restored"):
                await seed_row(conn, bound.table, **{bound.chat_column: chat_id})

    async with engine.begin() as conn:
        await delete_trashed_chat_bound_rows(conn, ["gone-1", "gone-2", "restored"])

    async with engine.connect() as conn:
        for bound in CHAT_BOUND_TABLES:
            remaining: list[str] = list((await conn.execute(text(f"SELECT {bound.chat_column} FROM {bound.table}"))).scalars())
            assert sorted(remaining) == ["restored", "stays"], f"{bound.table} kept {remaining}"


@pytest.mark.asyncio
async def test_delete_handles_more_chats_than_one_statement_can_bind(engine: AsyncEngine) -> None:
    chat_ids = [f"bulk-{n}" for n in range(1_300)]
    target = CHAT_BOUND_TABLES[0]
    async with engine.begin() as conn:
        await _seed_chat(conn, chat_ids[1_250], trashed=True)
        await seed_row(conn, target.table, **{target.chat_column: chat_ids[1_250]})
        await _seed_chat(conn, "stays", trashed=True)
        await seed_row(conn, target.table, **{target.chat_column: "stays"})

    async with engine.begin() as conn:
        await delete_trashed_chat_bound_rows(conn, chat_ids)

    async with engine.connect() as conn:
        remaining: list[str] = list((await conn.execute(text(f"SELECT {target.chat_column} FROM {target.table}"))).scalars())
    assert remaining == ["stays"]
