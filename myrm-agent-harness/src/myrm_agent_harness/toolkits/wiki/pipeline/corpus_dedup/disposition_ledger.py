"""Durable record of what the user decided about raw files: excluded, trashed, and pairs dismissed as not duplicates.

[INPUT]
- corpus_dedup.path_utils::normalize_raw_relative_path (POS: raw path key SSOT)
- corpus_dedup.types::ExcludedRawEntry, TrashedRawEntry, VaultHygieneSnapshot (POS: entry and listing value types)

[OUTPUT]
- DISPOSITION_SCHEMA: DDL the store creates together with the rest of ``.raw_dedup.db``
- DispositionLedger: excluded paths, trashed paths and dismissed pairs, plus the hygiene listing of the first two

[POS]
Storage half of the user's dedup decisions. ``CorpusEligibilityFilter`` reads it to drop blocked paths from the compile
path and ``CorpusDedupGovernor`` writes it when a disposition is applied. It borrows the store's connection factory, so
one vault keeps one SQLite file; groups and scan bookkeeping stay in ``CorpusDedupStore``.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable
from contextlib import AbstractContextManager
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.path_utils import normalize_raw_relative_path
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import (
    ExcludedRawEntry,
    TrashedRawEntry,
    VaultHygieneSnapshot,
)

DISPOSITION_SCHEMA = """
CREATE TABLE IF NOT EXISTS excluded_paths (
    relative_path TEXT PRIMARY KEY,
    reason TEXT NOT NULL,
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS trashed_paths (
    relative_path TEXT PRIMARY KEY,
    trash_relpath TEXT NOT NULL,
    content_hash TEXT NOT NULL DEFAULT '',
    created_at TEXT NOT NULL
);
CREATE TABLE IF NOT EXISTS dismissed_pairs (
    path_a TEXT NOT NULL,
    path_b TEXT NOT NULL,
    created_at TEXT NOT NULL,
    PRIMARY KEY (path_a, path_b)
);
"""


class DispositionLedger:
    """What the user excluded, trashed or dismissed, keyed by raw-relative path."""

    def __init__(self, connect: Callable[[], AbstractContextManager[sqlite3.Connection]]) -> None:
        self._connect = connect

    def get_excluded_paths(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT relative_path FROM excluded_paths").fetchall()
        return {str(row["relative_path"]) for row in rows}

    def get_trashed_paths(self) -> set[str]:
        with self._connect() as conn:
            rows = conn.execute("SELECT relative_path FROM trashed_paths").fetchall()
        return {str(row["relative_path"]) for row in rows}

    def add_excluded_path(self, relative_path: str, *, reason: str) -> None:
        normalized = normalize_raw_relative_path(relative_path)
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO excluded_paths (relative_path, reason, created_at)
                VALUES (?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    reason = excluded.reason,
                    created_at = excluded.created_at
                """,
                (normalized, reason, now),
            )

    def remove_excluded_path(self, relative_path: str) -> bool:
        normalized = normalize_raw_relative_path(relative_path)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM excluded_paths WHERE relative_path = ?",
                (normalized,),
            )
            return int(cursor.rowcount) > 0

    def list_excluded_entries(self) -> list[ExcludedRawEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT relative_path, reason, created_at
                FROM excluded_paths
                ORDER BY created_at DESC, relative_path ASC
                """
            ).fetchall()
        return [
            ExcludedRawEntry(
                relative_path=str(row["relative_path"]),
                reason=str(row["reason"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def get_excluded_entry(self, relative_path: str) -> ExcludedRawEntry | None:
        normalized = normalize_raw_relative_path(relative_path)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT relative_path, reason, created_at
                FROM excluded_paths
                WHERE relative_path = ?
                """,
                (normalized,),
            ).fetchone()
        if row is None:
            return None
        return ExcludedRawEntry(
            relative_path=str(row["relative_path"]),
            reason=str(row["reason"]),
            created_at=str(row["created_at"]),
        )

    def add_trashed_path(
        self,
        relative_path: str,
        *,
        trash_relpath: str,
        content_hash: str,
    ) -> None:
        normalized = normalize_raw_relative_path(relative_path)
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT INTO trashed_paths (relative_path, trash_relpath, content_hash, created_at)
                VALUES (?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    trash_relpath = excluded.trash_relpath,
                    content_hash = excluded.content_hash,
                    created_at = excluded.created_at
                """,
                (normalized, trash_relpath, content_hash, now),
            )

    def remove_trashed_path(self, relative_path: str) -> bool:
        normalized = normalize_raw_relative_path(relative_path)
        with self._connect() as conn:
            cursor = conn.execute(
                "DELETE FROM trashed_paths WHERE relative_path = ?",
                (normalized,),
            )
            return int(cursor.rowcount) > 0

    def get_trashed_entry(self, relative_path: str) -> TrashedRawEntry | None:
        normalized = normalize_raw_relative_path(relative_path)
        with self._connect() as conn:
            row = conn.execute(
                """
                SELECT relative_path, trash_relpath, content_hash, created_at
                FROM trashed_paths
                WHERE relative_path = ?
                """,
                (normalized,),
            ).fetchone()
        if row is None:
            return None
        return TrashedRawEntry(
            relative_path=str(row["relative_path"]),
            trash_relpath=str(row["trash_relpath"]),
            content_hash=str(row["content_hash"]),
            created_at=str(row["created_at"]),
        )

    def list_trashed_entries(self) -> list[TrashedRawEntry]:
        with self._connect() as conn:
            rows = conn.execute(
                """
                SELECT relative_path, trash_relpath, content_hash, created_at
                FROM trashed_paths
                ORDER BY created_at DESC, relative_path ASC
                """
            ).fetchall()
        return [
            TrashedRawEntry(
                relative_path=str(row["relative_path"]),
                trash_relpath=str(row["trash_relpath"]),
                content_hash=str(row["content_hash"]),
                created_at=str(row["created_at"]),
            )
            for row in rows
        ]

    def build_vault_hygiene_snapshot(self) -> VaultHygieneSnapshot:
        return VaultHygieneSnapshot(
            trashed=tuple(self.list_trashed_entries()),
            excluded=tuple(self.list_excluded_entries()),
        )

    def add_dismissed_pair(self, path_a: str, path_b: str) -> None:
        left, right = sorted((path_a, path_b))
        now = datetime.now(UTC).isoformat()
        with self._connect() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO dismissed_pairs (path_a, path_b, created_at)
                VALUES (?, ?, ?)
                """,
                (left, right, now),
            )

    def is_pair_dismissed(self, path_a: str, path_b: str) -> bool:
        left, right = sorted((path_a, path_b))
        with self._connect() as conn:
            row = conn.execute(
                "SELECT 1 FROM dismissed_pairs WHERE path_a = ? AND path_b = ?",
                (left, right),
            ).fetchone()
        return row is not None
