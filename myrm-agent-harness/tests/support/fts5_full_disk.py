"""A disk with no room left for the table copy an indexer makes when it converts an old index.

[INPUT]
- myrm_agent_harness.utils.db.sqlite::harden_connection_sync (POS: applies a SQLite profile to every index connection the harness opens)

[OUTPUT]
- limit_database_growth: from now on every index connection may grow its database file by only a few pages

[POS]
Harness pytest-only fixture helper. SQLite reports a full disk (``SQLITE_FULL``) by undoing the whole transaction
on its own, which a mocked error cannot reproduce, so the conversion tests cap the real page count with
``PRAGMA max_page_count`` and let SQLite fail the copy halfway.
"""

from __future__ import annotations

import sqlite3
from pathlib import Path

import pytest

from myrm_agent_harness.utils.db import sqlite as sqlite_utils
from myrm_agent_harness.utils.db.sqlite import DEFAULT, SQLiteProfile

_JOURNAL_MODES = ("wal", "delete")


def limit_database_growth(patch: pytest.MonkeyPatch, *, extra_pages: int, journal_mode: str) -> None:
    """Cap the database of every connection hardened from now on at its current size plus ``extra_pages``.

    The connection is also switched to ``journal_mode`` (``wal`` or ``delete``): the two modes keep a
    transaction's pages in different files, and both must leave the database as it was after a full disk.
    """
    assert journal_mode in _JOURNAL_MODES
    harden = sqlite_utils.harden_connection_sync

    def limited(conn: sqlite3.Connection, profile: SQLiteProfile = DEFAULT, *, db_path: Path | None = None) -> str:
        harden(conn, profile, db_path=db_path)
        conn.execute(f"PRAGMA journal_mode = {journal_mode}")
        pages = int(conn.execute("PRAGMA page_count").fetchone()[0])
        conn.execute(f"PRAGMA max_page_count = {pages + extra_pages}")
        return journal_mode.upper()

    patch.setattr(sqlite_utils, "harden_connection_sync", limited)
