"""What salvage replays: tables, virtual tables, indexes and views, and which tables are only FTS shadows.

The classifier is pure, so the rules are checked on hand-written ``sqlite_master`` rows; one end-to-end test salvages a
real file that holds a table named like an FTS4 shadow table.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

import pytest

from myrm_agent_harness.infra.sqlite_salvage import SQLiteRowidSalvageEngine
from myrm_agent_harness.infra.sqlite_salvage_schema import classify_schema_objects

_FTS_TABLE = "CREATE VIRTUAL TABLE notes_fts USING fts5(body, content=notes, content_rowid=id)"
_SHADOW_NAMES = (
    "notes_fts_data",
    "notes_fts_idx",
    "notes_fts_content",
    "notes_fts_docsize",
    "notes_fts_config",
    "notes_fts_segments",
    "notes_fts_segdir",
    "notes_fts_stat",
)


def test_a_table_that_ends_like_a_shadow_table_but_belongs_to_no_virtual_table_is_a_real_table() -> None:
    rows = [
        ("table", "conversation_recall_segments", "CREATE TABLE conversation_recall_segments (id INTEGER PRIMARY KEY)"),
        ("table", "app_config", "CREATE TABLE app_config (k TEXT PRIMARY KEY, v TEXT)"),
        ("table", "notes", "CREATE TABLE notes (id INTEGER PRIMARY KEY, body TEXT)"),
        ("table", "notes_fts", _FTS_TABLE),
    ]

    tables, virtual_tables, _indexes, _views = classify_schema_objects(rows)

    assert set(tables) == {"conversation_recall_segments", "app_config", "notes"}
    assert set(virtual_tables) == {"notes_fts"}


def test_the_shadow_tables_of_a_virtual_table_are_left_to_the_virtual_table_that_recreates_them() -> None:
    rows = [("table", "notes_fts", _FTS_TABLE)]
    rows += [("table", name, f"CREATE TABLE '{name}'(id INTEGER PRIMARY KEY, block BLOB)") for name in _SHADOW_NAMES]

    tables, virtual_tables, _indexes, _views = classify_schema_objects(rows)

    assert tables == {}
    assert set(virtual_tables) == {"notes_fts"}


def test_a_shadow_suffix_only_counts_for_the_virtual_table_it_follows() -> None:
    rows = [
        ("table", "notes_fts", _FTS_TABLE),
        ("table", "notes_fts_data", "CREATE TABLE 'notes_fts_data'(id INTEGER PRIMARY KEY, block BLOB)"),
        ("table", "other_data", "CREATE TABLE other_data (id INTEGER PRIMARY KEY)"),
    ]

    tables, _virtual_tables, _indexes, _views = classify_schema_objects(rows)

    assert set(tables) == {"other_data"}


@pytest.mark.parametrize(
    "statement",
    [
        "CREATE VIRTUAL TABLE v USING fts5(body)",
        "create virtual table v using fts5(body)",
        "  CREATE\n  VIRTUAL\tTABLE v USING fts5(body)",
    ],
)
def test_a_statement_that_opens_with_create_virtual_table_is_a_virtual_table(statement: str) -> None:
    tables, virtual_tables, _indexes, _views = classify_schema_objects([("table", "v", statement)])

    assert tables == {}
    assert set(virtual_tables) == {"v"}


def test_a_plain_table_that_mentions_the_word_virtual_keeps_its_rows_in_the_salvage() -> None:
    statement = (
        "CREATE TABLE devices (id INTEGER PRIMARY KEY, is_virtual BOOLEAN DEFAULT 0, kind TEXT DEFAULT 'virtual')"
    )

    tables, virtual_tables, _indexes, _views = classify_schema_objects([("table", "devices", statement)])

    assert set(tables) == {"devices"}
    assert virtual_tables == {}


def test_indexes_named_like_a_shadow_table_are_kept_and_autoindexes_are_dropped() -> None:
    rows = [
        ("table", "chats", "CREATE TABLE chats (id TEXT PRIMARY KEY, title TEXT)"),
        ("index", "idx_chats_config", "CREATE INDEX idx_chats_config ON chats(title)"),
        ("index", "idx_chats_data", "CREATE INDEX idx_chats_data ON chats(id, title)"),
        ("index", "sqlite_autoindex_chats_1", "CREATE UNIQUE INDEX sqlite_autoindex_chats_1 ON chats(id)"),
        ("view", "v_chats", "CREATE VIEW v_chats AS SELECT id FROM chats"),
    ]

    tables, _virtual_tables, indexes, views = classify_schema_objects(rows)

    assert set(tables) == {"chats"}
    assert set(indexes) == {"idx_chats_config", "idx_chats_data"}
    assert set(views) == {"v_chats"}


def test_entries_without_a_statement_are_skipped() -> None:
    rows = [("table", "ghost", None), ("index", "ghost_ix", ""), ("view", "ghost_v", None)]

    assert classify_schema_objects(rows) == ({}, {}, {}, {})


def test_salvage_copies_a_table_named_like_an_fts4_shadow_table_with_its_rows_indexes_and_search_index(
    tmp_path: Path,
) -> None:
    source = tmp_path / "recall.db"
    recovered = tmp_path / "recovered.db"
    with closing(sqlite3.connect(source)) as conn:
        conn.executescript(
            """
            CREATE TABLE conversation_recall_segments (id INTEGER PRIMARY KEY AUTOINCREMENT, segment_text TEXT NOT NULL);
            CREATE INDEX idx_recall_segments_text ON conversation_recall_segments(segment_text);
            CREATE VIRTUAL TABLE conversation_recall_segments_fts USING fts5(
                segment_text, content=conversation_recall_segments, content_rowid=id, tokenize='trigram'
            );
            INSERT INTO conversation_recall_segments (segment_text) VALUES ('the quarterly budget review'), ('lunch plans');
            INSERT INTO conversation_recall_segments_fts(conversation_recall_segments_fts) VALUES ('rebuild');
            """
        )
        conn.commit()

    result = SQLiteRowidSalvageEngine(chunk_size=50).salvage_database(source, recovered)

    assert result.success is True
    assert result.table_stats["conversation_recall_segments"].recovered_rows == 2
    assert "idx_recall_segments_text" in result.indexes_rebuilt
    with closing(sqlite3.connect(recovered)) as conn:
        assert conn.execute("SELECT COUNT(*) FROM conversation_recall_segments").fetchone()[0] == 2
        hits = conn.execute(
            "SELECT rowid FROM conversation_recall_segments_fts WHERE conversation_recall_segments_fts MATCH 'budget'"
        ).fetchall()
        assert hits == [(1,)]
        assert conn.execute("PRAGMA quick_check").fetchone()[0] == "ok"
