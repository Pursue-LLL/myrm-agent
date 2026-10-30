"""fts5_swap_tokenizer: an FTS5 table moves to another tokenizer with its rows, or stays exactly as it was."""

from __future__ import annotations

import sqlite3
from collections.abc import Iterator, Sequence
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


class _RenameFails(sqlite3.Connection):
    """A connection whose last swap step fails after the old table is already dropped."""

    def execute(self, sql: str, parameters: Sequence[object] = (), /) -> sqlite3.Cursor:
        if sql.startswith("ALTER TABLE"):
            raise sqlite3.OperationalError("disk I/O error")
        return super().execute(sql, parameters)


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
    ],
)
def test_a_name_that_could_alter_the_statement_is_rejected(
    notes: sqlite3.Connection, table: str, columns: tuple[str, ...], tokenizer: str
) -> None:
    with pytest.raises(ValueError, match="Invalid FTS5"):
        fts5_swap_tokenizer(notes, table, columns, tokenizer)

    assert _rows(notes) == _ROWS


def test_a_failed_swap_leaves_the_table_as_it_was_and_the_connection_usable(tmp_path: Path) -> None:
    with closing(sqlite3.connect(tmp_path / "failing.db", factory=_RenameFails)) as conn:
        _create_notes(conn)
        conn.execute("INSERT INTO notes(rowid, title, body) VALUES (11, 'Pending', 'not committed yet')")

        assert fts5_swap_tokenizer(conn, "notes", _COLUMNS, _STEMMING) is False

        assert "porter" not in _declaration(conn)
        assert _matches(conn, "transformer") == []
        assert conn.execute("SELECT count(*) FROM sqlite_master WHERE name LIKE 'notes_retokenize%'").fetchone()[0] == 0
        # The savepoint undid the swap only: the caller's own uncommitted write is still part of its transaction.
        assert _rows(conn) == [*_ROWS, (11, "Pending", "not committed yet")]
        conn.commit()
        assert _matches(conn, "models") == [7]


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
