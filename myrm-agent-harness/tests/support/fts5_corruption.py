"""Break a real FTS5 index the way an unclean shutdown can.

[INPUT]
- sqlite3 (POS: standard library database)

[OUTPUT]
- CORRUPTIONS: the supported kinds of damage
- corrupt_fts5_index: damage the shadow tables of an FTS5 table and check that SQLite now refuses to read it

[POS]
Harness pytest-only fixture helper. A mock that raises ``OperationalError`` cannot show what SQLite raises for a
damaged FTS5 index (``DatabaseError: database disk image is malformed``, a sibling of ``OperationalError`` and
not a subclass of it), so the heal and startup-rebuild tests damage a real index and the helper proves the
damage took effect.
"""

from __future__ import annotations

import sqlite3

CORRUPTIONS = ("empty-docsize", "truncated-segment")


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
