"""Tests for Chat DB compression ineffective streak persistence."""

from __future__ import annotations

from pathlib import Path

import pytest
from myrm_agent_harness.agent.context_management.strategies.compression.compression_anti_thrash_guard import (
    ANTI_THRASHING_STREAK_LIMIT,
    should_block_automatic_compression,
)
from myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store import (
    get_compression_streak_store,
    register_compression_streak_store,
)
from myrm_agent_harness.agent.context_management.tracking.task_metrics import (
    clear_task_metrics,
)
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat
from app.services.chat.compact.compression_streak import (
    ChatCompressionStreakStore,
    hydrate_compression_streak_from_db,
    load_compression_ineffective_streak,
    register_chat_compression_streak_store,
    save_compression_ineffective_streak,
)


@pytest.fixture(autouse=True)
def _register_db_streak_store() -> None:
    register_chat_compression_streak_store()
    yield
    register_compression_streak_store(None)


@pytest.mark.asyncio
async def test_save_and_load_streak_from_chat_row(db_session: AsyncSession) -> None:
    chat_id = "chat-db-streak-1"
    db_session.add(Chat(id=chat_id, source="web"))
    await db_session.commit()

    await save_compression_ineffective_streak(
        db_session, chat_id, ANTI_THRASHING_STREAK_LIMIT
    )
    await db_session.commit()

    loaded = await load_compression_ineffective_streak(db_session, chat_id)
    assert loaded == ANTI_THRASHING_STREAK_LIMIT


@pytest.mark.asyncio
async def test_hydrate_seeds_store_for_should_block(db_session: AsyncSession) -> None:
    chat_id = "chat-db-streak-2"
    db_session.add(Chat(id=chat_id, source="web"))
    await db_session.commit()
    clear_task_metrics(chat_id)

    await db_session.execute(
        update(Chat)
        .where(Chat.id == chat_id)
        .values(compression_ineffective_streak=ANTI_THRASHING_STREAK_LIMIT)
    )
    await db_session.commit()

    await hydrate_compression_streak_from_db(db_session, chat_id)

    assert should_block_automatic_compression(
        chat_id,
        total_tokens=50_000,
        max_context_tokens=128_000,
    )
    store = get_compression_streak_store()
    assert isinstance(store, ChatCompressionStreakStore)
    assert store.get_streak(chat_id) == ANTI_THRASHING_STREAK_LIMIT


@pytest.mark.asyncio
async def test_sync_store_reads_persisted_chat_row(db_session: AsyncSession) -> None:
    chat_id = "chat-db-streak-3"
    db_session.add(Chat(id=chat_id, source="web"))
    await db_session.commit()

    await save_compression_ineffective_streak(db_session, chat_id, 2)
    await db_session.commit()

    loaded = await load_compression_ineffective_streak(db_session, chat_id)
    assert loaded == 2

    store = ChatCompressionStreakStore()
    store.seed_streak(chat_id, loaded)
    assert store.get_streak(chat_id) == 2


def test_guard_record_persists_via_chat_compression_streak_store(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    db_file = tmp_path / "streak_guard.db"
    monkeypatch.setattr(
        "app.config.settings.settings.database.sqlite_path", str(db_file)
    )

    import sqlite3

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "CREATE TABLE chats ("
            "id TEXT PRIMARY KEY, "
            "compression_ineffective_streak INTEGER NOT NULL DEFAULT 0)"
        )
        conn.execute(
            "INSERT INTO chats (id, compression_ineffective_streak) VALUES ('chat-guard-persist', 0)"
        )
        conn.commit()

    register_chat_compression_streak_store()
    try:
        from myrm_agent_harness.agent.context_management.strategies.compression.compression_anti_thrash_guard import (
            record_compression_effectiveness,
        )

        record_compression_effectiveness(
            "chat-guard-persist",
            original_tokens=10_000,
            tokens_saved=50,
        )

        reloaded = ChatCompressionStreakStore()
        assert reloaded.get_streak("chat-guard-persist") == 1
    finally:
        register_compression_streak_store(None)


def test_store_empty_chat_id_is_safe() -> None:
    """Empty chat_id short-circuits get/set without touching persistence."""
    store = ChatCompressionStreakStore()
    assert store.get_streak(None) == 0
    assert store.get_streak("") == 0
    store.set_streak(None, 3)
    store.set_streak("", 3)


def test_store_reads_zero_when_db_missing(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Missing DB file degrades to streak 0."""
    missing = tmp_path / "no_such" / "missing.db"
    monkeypatch.setattr(
        "app.config.settings.settings.database.sqlite_path", str(missing)
    )
    store = ChatCompressionStreakStore()
    assert store.get_streak("chat-missing-db") == 0


def test_store_reads_zero_when_row_absent(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Absent chat row or NULL streak degrades to 0."""
    db_file = tmp_path / "streak_empty.db"
    monkeypatch.setattr(
        "app.config.settings.settings.database.sqlite_path", str(db_file)
    )
    import sqlite3

    with sqlite3.connect(db_file) as conn:
        conn.execute(
            "CREATE TABLE chats ("
            "id TEXT PRIMARY KEY, "
            "compression_ineffective_streak INTEGER NOT NULL DEFAULT 0)"
        )
        conn.commit()

    store = ChatCompressionStreakStore()
    assert store.get_streak("chat-absent") == 0


def test_store_handles_sqlite_read_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Corrupt/unsupported DB surface a warning and degrade to 0."""
    db_file = tmp_path / "streak_bad.db"
    monkeypatch.setattr(
        "app.config.settings.settings.database.sqlite_path", str(db_file)
    )
    db_file.write_text("this is not a sqlite database at all", encoding="utf-8")

    store = ChatCompressionStreakStore()
    assert store.get_streak("chat-bad-db") == 0


def test_store_handles_sqlite_write_error(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Write failure against a non-sqlite file is tolerated."""
    db_file = tmp_path / "streak_bad_write.db"
    monkeypatch.setattr(
        "app.config.settings.settings.database.sqlite_path", str(db_file)
    )
    db_file.write_text("not a database", encoding="utf-8")

    store = ChatCompressionStreakStore()
    store.set_streak("chat-write-err", 2)
    assert store.get_streak("chat-write-err") == 2


@pytest.mark.asyncio
async def test_hydrate_falls_back_to_generic_store(
    db_session: AsyncSession, tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """When the registered store is not a ChatStore, hydrate uses set_streak."""
    chat_id = "chat-hydrate-generic"
    db_session.add(Chat(id=chat_id, source="web"))
    await db_session.commit()

    from myrm_agent_harness.agent.context_management.strategies.compression.compression_streak_store import (
        InMemoryCompressionStreakStore,
    )

    register_compression_streak_store(InMemoryCompressionStreakStore())
    try:
        streak = await hydrate_compression_streak_from_db(db_session, chat_id)
    finally:
        register_compression_streak_store(None)
    assert streak == 0


@pytest.mark.asyncio
async def test_load_streak_handles_null_column(
    db_session: AsyncSession,
) -> None:
    """A Chat row without a streak still loads as 0."""
    chat_id = "chat-null-col"
    db_session.add(Chat(id=chat_id, source="web"))
    await db_session.commit()

    loaded = await load_compression_ineffective_streak(db_session, chat_id)
    assert loaded == 0


def test_store_creates_parent_dir_on_write(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Write creates missing parent directories for the SQLite file."""
    db_file = tmp_path / "nested" / "dir" / "streak.db"
    monkeypatch.setattr(
        "app.config.settings.settings.database.sqlite_path", str(db_file)
    )

    store = ChatCompressionStreakStore()
    store.set_streak("chat-mkdir", 1)

    assert db_file.parent.exists()
    assert store.get_streak("chat-mkdir") == 1
