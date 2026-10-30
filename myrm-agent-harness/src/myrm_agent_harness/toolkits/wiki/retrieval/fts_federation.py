"""Federated FTS access shared by the wiki index readers.

[INPUT]
- sqlite3 (POS: standard library database)

[OUTPUT]
- MAX_FEDERATED_DATABASES: how many shared vault indexes a connection attaches, and how many `pub_N` aliases the readers look for
- attached_tables: a table of the primary index plus the same table of every attached shared index that has it

[POS]
Leaf module of the retrieval package: it imports nothing from it, so the search, sidecar, truth and graph
readers share one definition of "which shared indexes does this query reach".
"""

from __future__ import annotations

import sqlite3

MAX_FEDERATED_DATABASES = 6


def attached_tables(conn: sqlite3.Connection, table: str) -> list[str]:
    """Return ``table`` of the primary index, then ``pub_N.table`` for each attached shared index that has it.

    A shared index that is attached but unreadable, or that lacks the table, is skipped.
    """
    tables = [table]
    attached = {str(row[1]) for row in conn.execute("PRAGMA database_list").fetchall()}
    for idx in range(MAX_FEDERATED_DATABASES):
        alias = f"pub_{idx}"
        if alias not in attached:
            continue
        try:
            found = conn.execute(
                f"SELECT 1 FROM {alias}.sqlite_master WHERE type IN ('table', 'view') AND name = ?",
                (table,),
            ).fetchone()
        except (sqlite3.OperationalError, sqlite3.DatabaseError):
            continue
        if found:
            tables.append(f"{alias}.{table}")
    return tables
