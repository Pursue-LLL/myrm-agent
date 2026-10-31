"""fts5_swap_tokenizer: an FTS5 table moves to another tokenizer with its rows, or stays exactly as it was."""

from __future__ import annotations

import sqlite3
import threading
from collections.abc import Iterator
from concurrent.futures import ThreadPoolExecutor
from contextlib import closing
from pathlib import Path

import pytest

from myrm_agent_harness.utils.db.fts5 import fts5_swap_tokenizer

_STEMMING = "porter unicode61 remove_diacritics 1"
_COLUMNS = ("title", "body")
_ROWS = [(7, "Transformers", "trained models"), (9, "Kitchen", "whisk eggs")]


def _create_notes(conn: sqlite3.Connection, table: str = "notes") -> None:
    conn.execute(f'CREATE VIRTUAL TABLE {table} USING fts5(title, body, tokenize="unicode61 remove_diacritics 1")')
    conn.executemany(f"INSERT INTO {table}(rowid, title, body) VALUES (?, ?, ?)", _ROWS)
    conn.commit()


def _matches(conn: sqlite3.Connection, query: str, schema: str = "main") -> list[int]:
    rows = conn.execute(f"SELECT rowid FROM {schema}.notes WHERE notes MATCH ?", (f'"{query}"',))
    return [int(row[0]) for row in rows]


def _declaration(conn: sqlite3.Connection, table: str = "notes") -> str:
    return str(conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()[0])


def _rows(conn: sqlite3.Connection, table: str = "notes") -> list[tuple[int, str, str]]:
    return conn.execute(f"SELECT rowid, title, body FROM {table} ORDER BY rowid").fetchall()


def _refuse_renames(action: int, arg1: str | None, arg2: str | None, db_name: str | None, source: str | None) -> int:
    """SQLite authorizer under which the last swap step fails, after the old table is already dropped."""
    return sqlite3.SQLITE_DENY if action == sqlite3.SQLITE_ALTER_TABLE else sqlite3.SQLITE_OK


@pytest.fixture
def notes(tmp_path: Path) -> Iterator[sqlite3.Connection]:
    with closing(sqlite3.connect(tmp_path / "notes.db")) as conn:
        _create_notes(conn)
        yield conn


def test_the_swapped_table_keeps_every_row_and_rowid_and_stems(notes: sqlite3.Connection) -> None:
    assert _matches(notes, "transformer") == []

    assert fts5_swap_tokenizer(notes, "notes", _COLUMNS, _STEMMING) is True

    assert _rows(notes) == _ROWS
    assert _matches(notes, "transformer") == [7]
    assert _matches(notes, "training") == [7]
    assert _matches(notes, "kitchens") == [9]
    assert "porter" in _declaration(notes)


def test_a_table_that_already_uses_the_tokenizer_is_left_alone(notes: sqlite3.Connection) -> None:
    assert fts5_swap_tokenizer(notes, "notes", _COLUMNS, _STEMMING) is True
    root_page = notes.execute("SELECT rootpage FROM sqlite_master WHERE name = 'notes'").fetchone()[0]

    assert fts5_swap_tokenizer(notes, "notes", _COLUMNS, _STEMMING.upper().replace(" ", "  ")) is False

    assert notes.execute("SELECT rootpage FROM sqlite_master WHERE name = 'notes'").fetchone()[0] == root_page
    assert _rows(notes) == _ROWS


def test_a_missing_table_is_not_created(notes: sqlite3.Connection) -> None:
    assert fts5_swap_tokenizer(notes, "absent", _COLUMNS, _STEMMING) is False

    assert notes.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'absent%'").fetchone()[0] == 0


@pytest.mark.parametrize(
    ("table", "columns", "tokenizer"),
    [
        ("notes; DROP TABLE notes", _COLUMNS, _STEMMING),
        ("notes", ("title", "bo dy"), _STEMMING),
        ("notes", _COLUMNS, 'porter"); DROP TABLE notes; --'),
        ("notes\n", _COLUMNS, _STEMMING),
        ("notes", ("title", "body\n"), _STEMMING),
        ("notes", _COLUMNS, f"{_STEMMING}\n"),
    ],
)
def test_a_name_that_could_alter_the_statement_is_rejected(
    notes: sqlite3.Connection, table: str, columns: tuple[str, ...], tokenizer: str
) -> None:
    with pytest.raises(ValueError, match="Invalid FTS5"):
        fts5_swap_tokenizer(notes, table, columns, tokenizer)

    assert _rows(notes) == _ROWS


def test_a_failed_swap_leaves_the_table_as_it_was_and_the_connection_usable(tmp_path: Path) -> None:
    with closing(sqlite3.connect(tmp_path / "failing.db")) as conn:
        _create_notes(conn)
        conn.set_authorizer(_refuse_renames)

        assert fts5_swap_tokenizer(conn, "notes", _COLUMNS, _STEMMING) is False

        assert not conn.in_transaction
        assert "porter" not in _declaration(conn)
        assert _matches(conn, "transformer") == []
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'notes_retokenize%'").fetchone()[0] == 0
        assert _rows(conn) == _ROWS
        conn.execute("INSERT INTO notes(rowid, title, body) VALUES (11, 'Later', 'still writable')")
        conn.commit()
        assert _matches(conn, "writable") == [11]


@pytest.mark.parametrize("journal_mode", ["wal", "delete"])
def test_a_swap_that_runs_out_of_space_halfway_leaves_the_table_as_it_was(tmp_path: Path, journal_mode: str) -> None:
    rows = [(i, f"title {i}", f"{'trained transformers ' * 40}{i}") for i in range(1, 801)]
    with closing(sqlite3.connect(tmp_path / "full.db")) as conn:
        conn.execute(f"PRAGMA journal_mode = {journal_mode}")
        conn.execute('CREATE VIRTUAL TABLE notes USING fts5(title, body, tokenize="unicode61 remove_diacritics 1")')
        conn.executemany("INSERT INTO notes(rowid, title, body) VALUES (?, ?, ?)", rows)
        conn.commit()
        pages = conn.execute("PRAGMA page_count").fetchone()[0]
        conn.execute(f"PRAGMA max_page_count = {pages + 6}")

        assert fts5_swap_tokenizer(conn, "notes", _COLUMNS, _STEMMING) is False

        # SQLite undid the whole transaction by itself when the disk filled up; the helper must not fail on that.
        assert not conn.in_transaction
        conn.execute("PRAGMA max_page_count = 1000000")
        assert "porter" not in _declaration(conn)
        assert _rows(conn) == rows
        assert _matches(conn, "transformer") == []
        assert fts5_swap_tokenizer(conn, "notes", _COLUMNS, _STEMMING) is True
        assert _rows(conn) == rows
        assert _matches(conn, "transformer") == [row[0] for row in rows]


def test_a_swap_inside_a_transaction_is_refused_and_leaves_the_transaction_alone(notes: sqlite3.Connection) -> None:
    notes.execute("INSERT INTO notes(rowid, title, body) VALUES (11, 'Pending', 'not committed yet')")
    assert notes.in_transaction

    with pytest.raises(ValueError, match="outside a transaction"):
        fts5_swap_tokenizer(notes, "notes", _COLUMNS, _STEMMING)

    assert notes.in_transaction
    assert "porter" not in _declaration(notes)
    notes.commit()
    assert _rows(notes) == [*_ROWS, (11, "Pending", "not committed yet")]


def test_two_connections_swapping_at_once_swap_the_table_once(tmp_path: Path) -> None:
    db_path = tmp_path / "race.db"
    filler = [(i, f"title {i}", f"{'trained transformers ' * 10}{i}") for i in range(100, 3100)]
    with closing(sqlite3.connect(db_path)) as setup:
        _create_notes(setup)
        setup.executemany("INSERT INTO notes(rowid, title, body) VALUES (?, ?, ?)", filler)
        setup.commit()
    start = threading.Barrier(2)

    def swap() -> bool:
        with closing(sqlite3.connect(db_path, timeout=30)) as conn:
            start.wait()
            return fts5_swap_tokenizer(conn, "notes", _COLUMNS, _STEMMING)

    with ThreadPoolExecutor(max_workers=2) as pool:
        outcomes = [future.result() for future in [pool.submit(swap), pool.submit(swap)]]

    assert sorted(outcomes) == [False, True]
    with closing(sqlite3.connect(db_path)) as check:
        assert "porter" in _declaration(check)
        assert _rows(check) == [*_ROWS, *filler]


def test_a_blocked_staging_name_makes_the_swap_fail_without_touching_anything(notes: sqlite3.Connection) -> None:
    notes.execute("CREATE TABLE notes_retokenize(x)")

    assert fts5_swap_tokenizer(notes, "notes", _COLUMNS, _STEMMING) is False

    assert _rows(notes) == _ROWS
    assert "porter" not in _declaration(notes)
    assert notes.execute("SELECT count(*) FROM sqlite_master WHERE name = 'notes_retokenize'").fetchone()[0] == 1


def test_only_the_main_schema_is_swapped_when_a_database_with_the_same_table_is_attached(
    tmp_path: Path, notes: sqlite3.Connection
) -> None:
    with closing(sqlite3.connect(tmp_path / "shared.db")) as shared:
        _create_notes(shared)
    notes.execute("ATTACH DATABASE ? AS shared", (str(tmp_path / "shared.db"),))

    assert fts5_swap_tokenizer(notes, "notes", _COLUMNS, _STEMMING) is True

    assert "porter" in _declaration(notes)
    attached = str(notes.execute("SELECT sql FROM shared.sqlite_master WHERE name = 'notes'").fetchone()[0])
    assert "porter" not in attached
    assert _matches(notes, "transformer", schema="shared") == []
