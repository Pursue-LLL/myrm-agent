"""Break a real FTS5 index the way an unclean shutdown can.

[INPUT]
- sqlite3 (POS: standard library database)

[OUTPUT]
- CORRUPTIONS: the supported kinds of damage to the index
- corrupt_fts5_index: damage the shadow tables of an FTS5 table and check that SQLite now refuses to read it
- corrupt_fts5_content_page: damage the page that stores the text of an FTS5 table, in the database file, and check the rows can no longer be read

[POS]
Harness pytest-only fixture helper. A mock that raises ``OperationalError`` cannot show what SQLite raises for a
damaged FTS5 index (``DatabaseError: database disk image is malformed``; ``OperationalError`` is a subclass of
``DatabaseError``, so a handler of ``OperationalError`` alone misses it), so the heal and startup-rebuild tests
damage a real index and the helper proves the damage took effect.
"""

from __future__ import annotations

import sqlite3
from contextlib import closing
from pathlib import Path

CORRUPTIONS = ("empty-docsize", "truncated-segment")

# A b-tree page keeps its cell count at bytes 3-4 of the page header.
_CELL_COUNT_OFFSET = 3


def corrupt_fts5_index(conn: sqlite3.Connection, table: str, kind: str) -> None:
    """Damage the shadow tables of ``table`` so the FTS5 ``integrity-check`` command fails.

    ``empty-docsize`` also makes ordinary queries fail; ``truncated-segment`` keeps simple queries working
    and only the integrity check sees it. ``table`` must hold enough rows to own at least one segment block.
    """
    if kind == "empty-docsize":
        conn.execute(f"DELETE FROM {table}_docsize")
    elif kind == "truncated-segment":
        block = conn.execute(f"SELECT id, length(block) FROM {table}_data WHERE id > 10 ORDER BY id LIMIT 1").fetchone()
        assert block is not None, f"{table} has no segment block to truncate"
        conn.execute(
            f"UPDATE {table}_data SET block = substr(block, 1, ?) WHERE id = ?", (max(1, block[1] // 3), block[0])
        )
    else:
        raise ValueError(f"unknown FTS5 corruption: {kind}")
    conn.commit()
    try:
        conn.execute(f"INSERT INTO {table}({table}) VALUES('integrity-check')")
    except sqlite3.DatabaseError:
        return
    raise AssertionError(f"{kind} left the FTS5 index of {table} readable")


def corrupt_fts5_content_page(db_path: Path, table: str) -> None:
    """Break the root page of the b-tree that stores the text of ``table`` so its rows can no longer be read.

    Edits the database file: no connection to ``db_path`` may be open, and everything must be committed to the
    main file (rollback-journal mode). The damage is a cell count no page can hold, which SQLite reports as
    ``database disk image is malformed`` as soon as it reads the page.
    """
    with closing(sqlite3.connect(db_path)) as conn:
        page_size = int(conn.execute("PRAGMA page_size").fetchone()[0])
        root = conn.execute("SELECT rootpage FROM sqlite_master WHERE name = ?", (f"{table}_content",)).fetchone()
    assert root is not None, f"{table} has no content table"
    with db_path.open("r+b") as db_file:
        db_file.seek((int(root[0]) - 1) * page_size + _CELL_COUNT_OFFSET)
        db_file.write(b"\xff\xff")
    with closing(sqlite3.connect(db_path)) as conn:
        try:
            conn.execute(f"SELECT * FROM {table}_content").fetchall()
        except sqlite3.DatabaseError:
            return
    raise AssertionError(f"the stored text of {table} is still readable")
