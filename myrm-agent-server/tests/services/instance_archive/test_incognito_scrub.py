"""A web incognito chat is promised to disappear once idle, so no exported or staged file may carry it.

Runs on the real schema (ORM tables, migrations, FTS triggers), real LangGraph checkpoints and the real snapshot
path: the rule depends on ON DELETE CASCADE, the messages_fts triggers, secure_delete and the checkpointer's own
tables, none of which a hand-written table set reproduces.
"""

from __future__ import annotations

import sqlite3
import zipfile
from collections.abc import Callable
from datetime import UTC, datetime
from pathlib import Path

import pytest
from langgraph.checkpoint.base import empty_checkpoint
from myrm_agent_harness.infra.state_archive import snapshot_sqlite
from myrm_agent_harness.runtime.checkpointing.factory import create_checkpointer
from sqlalchemy import create_engine
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.orm import Session

from app.database import migrations
from app.database.models import Base, Chat, Message, WidgetKVEntry
from app.services.instance_archive import export_service
from app.services.instance_archive.checkpoint_scrub import scrub_checkpoint_threads
from app.services.instance_archive.export_service import DataDbScrubber, build_export
from app.services.instance_archive.stage_db import StageContext, prepare_staged_db
from app.services.instance_archive.table_policy import scrub_sensitive_surface, web_incognito_chat_ids

INCOGNITO_SECRET = "incognito_secret_question"
KEPT_TEXT = "ordinary_kept_question"
IMPORTED_TEXT = "imported_transcript_text"


async def _seed_instance_db(path: Path) -> None:
    """A WAL-mode instance database (as the app runs it) holding one chat of each kind."""
    engine = create_async_engine(f"sqlite+aiosqlite:///{path}")
    try:
        async with engine.begin() as conn:
            await conn.run_sync(Base.metadata.create_all)
        await migrations.run_migrations(engine)
        await migrations.ensure_raw_sql_schema(engine)
    finally:
        await engine.dispose()

    sync_engine = create_engine(f"sqlite:///{path}")
    try:
        with sync_engine.connect() as raw:
            raw.exec_driver_sql("PRAGMA journal_mode=WAL")
        now = datetime.now(UTC)
        with Session(sync_engine) as session:
            session.add_all(
                [
                    Chat(id="kept", title="kept", is_incognito=False),
                    Chat(id="incognito", is_incognito=True),
                    Chat(id="imported", title="imported", is_incognito=True, source="claude_code"),
                ]
            )
            session.flush()
            session.add_all(
                [
                    Message(id="m-kept", chat_id="kept", role="user", content=KEPT_TEXT, sent_at=now, sent_timezone="UTC"),
                    Message(
                        id="m-incognito",
                        chat_id="incognito",
                        role="user",
                        content=INCOGNITO_SECRET,
                        sent_at=now,
                        sent_timezone="UTC",
                    ),
                    Message(
                        id="m-imported",
                        chat_id="imported",
                        role="user",
                        content=IMPORTED_TEXT,
                        sent_at=now,
                        sent_timezone="UTC",
                    ),
                    # A table that names its chat without a foreign key: the cascade never reaches it.
                    WidgetKVEntry(namespace="ns", key="incognito", value=INCOGNITO_SECRET, chat_id="incognito"),
                    WidgetKVEntry(namespace="ns", key="kept", value=KEPT_TEXT, chat_id="kept"),
                ]
            )
            session.commit()
        with sync_engine.connect() as raw:
            raw.exec_driver_sql(
                "INSERT INTO conversation_recall_documents (chat_id, searchable_text) VALUES ('incognito', ?)",
                (INCOGNITO_SECRET,),
            )
            raw.commit()
    finally:
        sync_engine.dispose()


def _export(snapshot: Path) -> None:
    DataDbScrubber(source_key=None, carry_sensitive=False)(snapshot)


def _stage(snapshot: Path) -> None:
    ctx = StageContext(
        live_db=None, source_user_id="u", target_user_id="u", max_schema_version=10**6, source_key=None, target_key=None
    )
    prepare_staged_db(snapshot, ctx)


@pytest.fixture(params=[_export, _stage], ids=["export", "import-staging"])
async def scrubbed(request: pytest.FixtureRequest, tmp_path: Path) -> Path:
    """The standalone copy an archive would carry, after the scrub of one of the two shared paths."""
    live = tmp_path / "live.db"
    await _seed_instance_db(live)
    snapshot = tmp_path / "snapshot.db"
    snapshot_sqlite(live, snapshot, compact=True)
    scrub: Callable[[Path], None] = request.param
    scrub(snapshot)
    return snapshot


def _scalar(db: Path, sql: str, *params: str) -> int:
    conn = sqlite3.connect(db)
    try:
        return int(conn.execute(sql, params).fetchone()[0])
    finally:
        conn.close()


async def test_web_incognito_chats_and_everything_derived_from_them_are_dropped(scrubbed: Path) -> None:
    conn = sqlite3.connect(scrubbed)
    try:
        chats = {row[0] for row in conn.execute("SELECT id FROM chats")}
        messages = {row[0] for row in conn.execute("SELECT id FROM messages")}
        recall = conn.execute("SELECT COUNT(*) FROM conversation_recall_documents WHERE chat_id = 'incognito'").fetchone()[0]
        indexed = conn.execute("SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH ?", (INCOGNITO_SECRET,)).fetchone()[0]
    finally:
        conn.close()

    assert chats == {"kept", "imported"}
    assert messages == {"m-kept", "m-imported"}
    assert recall == 0
    assert indexed == 0
    assert _scalar(scrubbed, "SELECT COUNT(*) FROM widget_kv WHERE chat_id = ?", "incognito") == 0
    assert _scalar(scrubbed, "SELECT COUNT(*) FROM widget_kv WHERE chat_id = ?", "kept") == 1


async def test_the_removed_text_does_not_survive_in_the_file_and_no_wal_is_left(scrubbed: Path) -> None:
    assert INCOGNITO_SECRET.encode() not in scrubbed.read_bytes()
    assert not scrubbed.with_name(scrubbed.name + "-wal").exists()


async def test_normal_chats_and_imported_transcripts_keep_their_messages(scrubbed: Path) -> None:
    assert _scalar(scrubbed, "SELECT COUNT(*) FROM messages WHERE content = ?", KEPT_TEXT) == 1
    assert _scalar(scrubbed, "SELECT COUNT(*) FROM messages WHERE content = ?", IMPORTED_TEXT) == 1
    assert _scalar(scrubbed, "SELECT COUNT(*) FROM messages_fts WHERE messages_fts MATCH ?", KEPT_TEXT) == 1


def _ignore_foreign_key_switch(action: int, arg1: str | None, arg2: str | None, *_: str | None) -> int:
    """Authorizer that turns ``PRAGMA foreign_keys = <value>`` into a silent no-op, as a build without them would."""
    if action == sqlite3.SQLITE_PRAGMA and arg1 == "foreign_keys" and arg2 is not None:
        return sqlite3.SQLITE_IGNORE
    return sqlite3.SQLITE_OK


def test_the_scrub_refuses_to_continue_when_cascading_deletes_cannot_be_enabled() -> None:
    """Without foreign keys the messages would be orphaned but kept, so the export must fail instead."""

    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE chats (id TEXT PRIMARY KEY, is_incognito BOOLEAN, source TEXT)")
    conn.execute("INSERT INTO chats VALUES ('incognito', 1, 'web')")
    conn.set_authorizer(_ignore_foreign_key_switch)
    try:
        with pytest.raises(sqlite3.OperationalError, match="foreign keys"):
            scrub_sensitive_surface(conn)
        assert conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0] == 1
    finally:
        conn.close()


def test_a_database_from_before_the_incognito_columns_is_left_alone() -> None:
    conn = sqlite3.connect(":memory:")
    conn.execute("CREATE TABLE chats (id TEXT PRIMARY KEY, title TEXT)")
    conn.execute("INSERT INTO chats VALUES ('old', 'kept')")
    try:
        assert web_incognito_chat_ids(conn) == []
        scrub_sensitive_surface(conn)
        assert conn.execute("SELECT COUNT(*) FROM chats").fetchone()[0] == 1
    finally:
        conn.close()


# --- the conversation checkpoints that live beside data.db -------------------------------------------------------

_CHECKPOINT_THREADS = {
    "incognito": INCOGNITO_SECRET,
    "chat_incognito": INCOGNITO_SECRET,
    "kept": KEPT_TEXT,
    "chat_kept": KEPT_TEXT,
    "imported": IMPORTED_TEXT,
    "chat_imported": IMPORTED_TEXT,
}
_SURVIVING_THREADS = {"kept", "chat_kept", "imported", "chat_imported"}


async def _seed_checkpoints(path: Path) -> None:
    """Real LangGraph checkpoint threads (both aliases a chat gets), each with a pending write."""
    saver, cleanup = await create_checkpointer(mode="sqlite", sqlite_db_path=str(path))
    try:
        for thread_id, text in _CHECKPOINT_THREADS.items():
            checkpoint = empty_checkpoint()
            checkpoint["channel_values"] = {"messages": text}
            stored = await saver.aput(
                {"configurable": {"thread_id": thread_id, "checkpoint_ns": ""}},
                checkpoint,
                {"source": "loop", "step": 0, "parents": {}},
                {},
            )
            await saver.aput_writes(stored, [("messages", text)], task_id=f"task-{thread_id}")
    finally:
        await cleanup()


async def _seed_state_dir(root: Path) -> None:
    root.mkdir(parents=True, exist_ok=True)
    await _seed_instance_db(root / "data.db")
    await _seed_checkpoints(root / "checkpoints.db")


def _threads(db: Path, table: str) -> set[str]:
    conn = sqlite3.connect(db)
    try:
        return {row[0] for row in conn.execute(f"SELECT DISTINCT thread_id FROM {table}")}
    finally:
        conn.close()


def _export_members(state: Path, dest: Path) -> dict[str, bytes]:
    result = build_export(
        state_dir=state, dest=dest, user_id="user-a", app_version="1.0.0", deploy_mode="local", config_key=None, passphrase=None
    )
    with zipfile.ZipFile(result.path) as archive:
        return {name: archive.read(name) for name in archive.namelist()}


def _member(members: dict[str, bytes], file_name: str) -> bytes:
    return next(data for name, data in members.items() if name.endswith(file_name))


async def test_a_full_export_carries_no_trace_of_a_web_incognito_chat_in_any_file(tmp_path: Path) -> None:
    state = tmp_path / "state"
    await _seed_state_dir(state)

    members = _export_members(state, tmp_path / "out.zip")

    assert [name for name, data in members.items() if INCOGNITO_SECRET.encode() in data] == []
    for file_name in ("data.db", "checkpoints.db"):
        assert KEPT_TEXT.encode() in _member(members, file_name)  # the scrub removes the chats, not the file
    checkpoints = tmp_path / "exported-checkpoints.db"
    checkpoints.write_bytes(_member(members, "checkpoints.db"))
    assert _threads(checkpoints, "checkpoints") == _SURVIVING_THREADS
    assert _threads(checkpoints, "writes") == _SURVIVING_THREADS


async def test_staging_an_older_archive_drops_the_incognito_threads_that_sit_beside_its_data_db(tmp_path: Path) -> None:
    live = tmp_path / "live"
    await _seed_state_dir(live)
    staged = tmp_path / "staging"
    staged.mkdir()
    for name in ("data.db", "checkpoints.db"):  # what extracting an archive made before the scrub existed leaves
        snapshot_sqlite(live / name, staged / name, compact=True)

    _stage(staged / "data.db")

    assert INCOGNITO_SECRET.encode() not in (staged / "checkpoints.db").read_bytes()
    assert _threads(staged / "checkpoints.db", "checkpoints") == _SURVIVING_THREADS
    assert _threads(staged / "checkpoints.db", "writes") == _SURVIVING_THREADS


async def test_checkpoints_that_cannot_be_scrubbed_are_left_out_of_the_archive_and_reported(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    def failing_scrubber(_main_db: Path) -> Callable[[Path], None]:
        def scrub(_copy: Path) -> None:
            raise sqlite3.OperationalError("simulated failure")

        return scrub

    state = tmp_path / "state"
    await _seed_state_dir(state)
    monkeypatch.setattr(export_service, "live_checkpoint_scrubber", failing_scrubber)

    members = _export_members(state, tmp_path / "out.zip")

    assert not any(name.endswith("checkpoints.db") for name in members)
    assert [name for name, data in members.items() if INCOGNITO_SECRET.encode() in data] == []


def test_threads_of_more_chats_than_one_statement_holds_are_all_removed(tmp_path: Path) -> None:
    db = tmp_path / "checkpoints.db"
    conn = sqlite3.connect(db)
    conn.execute("CREATE TABLE checkpoints (thread_id TEXT, payload TEXT)")
    conn.execute("CREATE TABLE writes (thread_id TEXT, payload TEXT)")
    conn.execute("CREATE TABLE settings (name TEXT, payload TEXT)")
    chat_ids = [f"chat-{index}" for index in range(500)]
    for chat_id in chat_ids:
        for thread_id in (chat_id, f"chat_{chat_id}"):
            conn.executemany("INSERT INTO checkpoints VALUES (?, ?)", [(thread_id, "text")])
            conn.executemany("INSERT INTO writes VALUES (?, ?)", [(thread_id, "text")])
    conn.execute("INSERT INTO checkpoints VALUES ('other', 'text')")
    conn.execute("INSERT INTO writes VALUES ('other', 'text')")
    conn.execute("INSERT INTO settings VALUES ('thread_id', 'not a thread table')")
    conn.commit()
    conn.close()

    scrub_checkpoint_threads(db, chat_ids)

    assert _threads(db, "checkpoints") == {"other"}
    assert _threads(db, "writes") == {"other"}
    assert _scalar(db, "SELECT COUNT(*) FROM settings") == 1
