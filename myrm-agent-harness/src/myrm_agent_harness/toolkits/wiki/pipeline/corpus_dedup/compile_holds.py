"""Ledger of raw files kept out of the compile queue until a duplicate scan has looked at them.

[INPUT]
- corpus_dedup.path_utils::normalize_raw_relative_path (POS: raw path key SSOT)
- corpus_dedup.types::HeldFile (POS: one held raw file and the instant it was held)

[OUTPUT]
- COMPILE_HOLD_SCHEMA: DDL the store creates together with the rest of ``.raw_dedup.db``
- CompileHoldLedger: hold / list_held / drop / any_held_after over the ``compile_holds`` table

[POS]
Durable half of the compile hold. A held path survives a crash, so a file that was published but not yet judged is
neither compiled twice nor stranded. Which held files may go is policy and lives in ``CorpusDedupGovernor``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Iterable
from contextlib import AbstractContextManager

from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.path_utils import normalize_raw_relative_path
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import HeldFile

COMPILE_HOLD_SCHEMA = """
CREATE TABLE IF NOT EXISTS compile_holds (
    relative_path TEXT PRIMARY KEY,
    held_at_ns INTEGER NOT NULL
);
"""


class CompileHoldLedger:
    """Held raw files, one row per raw-relative path."""

    def __init__(self, connect: Callable[[], AbstractContextManager[sqlite3.Connection]]) -> None:
        self._connect = connect

    def hold(self, relative_paths: Iterable[str], *, held_at_ns: int) -> None:
        """Hold the paths as of ``held_at_ns``; a path held again takes the newer instant."""
        rows = [(normalize_raw_relative_path(path), held_at_ns) for path in relative_paths]
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO compile_holds (relative_path, held_at_ns) VALUES (?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET held_at_ns = excluded.held_at_ns
                """,
                rows,
            )

    def list_held(self) -> list[HeldFile]:
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT relative_path, held_at_ns FROM compile_holds ORDER BY held_at_ns ASC, relative_path ASC"
            ).fetchall()
        return [HeldFile(relative_path=str(row["relative_path"]), held_at_ns=int(row["held_at_ns"])) for row in rows]

    def drop(self, held: Iterable[HeldFile]) -> None:
        """Forget the given holds; a path held again since it was read keeps its newer hold."""
        rows = [(item.relative_path, item.held_at_ns) for item in held]
        if not rows:
            return
        with self._connect() as conn:
            conn.executemany("DELETE FROM compile_holds WHERE relative_path = ? AND held_at_ns = ?", rows)

    def any_held_after(self, instant_ns: int) -> bool:
        with self._connect() as conn:
            row = conn.execute("SELECT 1 FROM compile_holds WHERE held_at_ns > ? LIMIT 1", (instant_ns,)).fetchone()
        return row is not None
