"""Make an FTS5 table look like one an earlier release wrote: the ``unicode61`` tokenizer, no stemming.

[INPUT]
- sqlite3 (POS: standard library database)

[OUTPUT]
- downgrade_fts5_tokenizer: re-create a table on the plain ``unicode61`` tokenizer with plain SQL, keeping its rows and rowids
- fts5_declaration: the ``CREATE`` statement SQLite stored for a table, which names its tokenizer
- fts5_rows: every stored row of a table as (rowid, *columns), the fingerprint a tokenizer swap must keep

[POS]
Harness pytest-only fixture helper. It uses no code under test, so a test can start from an old-style index and
then prove what opening it with the current code does to it.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path


def downgrade_fts5_tokenizer(db_path: Path, table: str, columns: tuple[str, ...]) -> None:
    """Re-create ``table`` (declared as plain ``columns``) on ``unicode61`` with its rows and rowids as they were."""
    column_list = ", ".join(columns)
    with closing(sqlite3.connect(db_path)) as conn:
        rows = conn.execute(f"SELECT rowid, {column_list} FROM {table}").fetchall()
        conn.execute(f"DROP TABLE {table}")
        conn.execute(
            f'CREATE VIRTUAL TABLE {table} USING fts5({column_list}, tokenize="unicode61 remove_diacritics 1")'
        )
        placeholders = ", ".join("?" * (len(columns) + 1))
        conn.executemany(f"INSERT INTO {table}(rowid, {column_list}) VALUES ({placeholders})", rows)
        conn.commit()
    assert "porter" not in fts5_declaration(db_path, table)


def fts5_declaration(db_path: Path, table: str) -> str:
    with closing(sqlite3.connect(db_path)) as conn:
        row = conn.execute("SELECT sql FROM sqlite_master WHERE name = ?", (table,)).fetchone()
    assert row is not None, f"{table} does not exist"
    return str(row[0])


def fts5_rows(db_path: Path, table: str, columns: tuple[str, ...]) -> list[tuple[int, ...]]:
    with closing(sqlite3.connect(db_path)) as conn:
        return conn.execute(f"SELECT rowid, {', '.join(columns)} FROM {table} ORDER BY rowid").fetchall()
