"""SQLite persistence for raw corpus dedup governance.

[POS]
See module docstring.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.compile_holds import COMPILE_HOLD_SCHEMA, CompileHoldLedger
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.fingerprint_cache import (
    FINGERPRINT_SCHEMA,
    FingerprintCache,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.path_utils import normalize_raw_relative_path
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import (
    DedupStats,
    DedupTier,
    DuplicateGroup,
    DuplicateMember,
    ExcludedRawEntry,
    GroupStatus,
    PlannedGroup,
    ScanProgress,
    TrashedRawEntry,
    VaultHygieneSnapshot,
)

_META_COMPILE_JOBS_PREVENTED = "compile_jobs_prevented"
_META_LAST_SCAN_AT = "last_scan_at"
_META_SCAN_COVERAGE_NS = "scan_coverage_ns"
_META_SCAN_PROGRESS = "scan_progress"


def _write_meta(conn: sqlite3.Connection, key: str, value: str) -> None:
    conn.execute(
        """
        INSERT INTO dedup_meta (key, value) VALUES (?, ?)
        ON CONFLICT(key) DO UPDATE SET value = excluded.value
        """,
        (key, value),
    )


class CorpusDedupStore:
    """Persist dedup scan results and user dispositions per vault."""

    def __init__(self, structure: WikiStructure) -> None:
        self._structure = structure
        self.db_path = structure.base_dir / ".raw_dedup.db"
        self.fingerprints = FingerprintCache(self._conn)
        self.holds = CompileHoldLedger(self._conn)
        self._init_db()

    @contextlib.contextmanager
    def _conn(self) -> Iterator[sqlite3.Connection]:
        from myrm_agent_harness.utils.db.sqlite import DEFAULT, harden_connection_sync

        conn = sqlite3.connect(self.db_path)
        conn.row_factory = sqlite3.Row
        harden_connection_sync(conn, DEFAULT, db_path=self.db_path)
        try:
            with conn:
                yield conn
        finally:
            conn.close()

    def _init_db(self) -> None:
        with self._conn() as conn:
            conn.executescript(
                """
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
                CREATE TABLE IF NOT EXISTS duplicate_groups (
                    id INTEGER PRIMARY KEY AUTOINCREMENT,
                    tier TEXT NOT NULL,
                    fingerprint TEXT NOT NULL,
                    recommended_keep_path TEXT NOT NULL,
                    status TEXT NOT NULL DEFAULT 'open',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS group_members (
                    group_id INTEGER NOT NULL,
                    relative_path TEXT NOT NULL,
                    size_bytes INTEGER NOT NULL,
                    mtime_ns INTEGER NOT NULL,
                    PRIMARY KEY (group_id, relative_path),
                    FOREIGN KEY (group_id) REFERENCES duplicate_groups(id) ON DELETE CASCADE
                );
                CREATE TABLE IF NOT EXISTS dedup_meta (
                    key TEXT PRIMARY KEY,
                    value TEXT NOT NULL
                );
                """
                + FINGERPRINT_SCHEMA
                + COMPILE_HOLD_SCHEMA
            )

    def get_excluded_paths(self) -> set[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT relative_path FROM excluded_paths").fetchall()
        return {str(row["relative_path"]) for row in rows}

    def get_trashed_paths(self) -> set[str]:
        with self._conn() as conn:
            rows = conn.execute("SELECT relative_path FROM trashed_paths").fetchall()
        return {str(row["relative_path"]) for row in rows}

    def add_excluded_path(self, relative_path: str, *, reason: str) -> None:
        normalized = normalize_raw_relative_path(relative_path)
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
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
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM excluded_paths WHERE relative_path = ?",
                (normalized,),
            )
            return int(cursor.rowcount) > 0

    def list_excluded_entries(self) -> list[ExcludedRawEntry]:
        with self._conn() as conn:
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
        with self._conn() as conn:
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
        with self._conn() as conn:
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
        with self._conn() as conn:
            cursor = conn.execute(
                "DELETE FROM trashed_paths WHERE relative_path = ?",
                (normalized,),
            )
            return int(cursor.rowcount) > 0

    def get_trashed_entry(self, relative_path: str) -> TrashedRawEntry | None:
        normalized = normalize_raw_relative_path(relative_path)
        with self._conn() as conn:
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
        with self._conn() as conn:
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

    def collect_deferred_member_sets(self) -> set[frozenset[str]]:
        groups = self.list_groups(status=GroupStatus.DEFERRED)
        return {frozenset(member.relative_path for member in group.members) for group in groups}

    def add_dismissed_pair(self, path_a: str, path_b: str) -> None:
        left, right = sorted((path_a, path_b))
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                """
                INSERT OR IGNORE INTO dismissed_pairs (path_a, path_b, created_at)
                VALUES (?, ?, ?)
                """,
                (left, right, now),
            )

    def is_pair_dismissed(self, path_a: str, path_b: str) -> bool:
        left, right = sorted((path_a, path_b))
        with self._conn() as conn:
            row = conn.execute(
                "SELECT 1 FROM dismissed_pairs WHERE path_a = ? AND path_b = ?",
                (left, right),
            ).fetchone()
        return row is not None

    def replace_scan_groups(self, groups: Sequence[PlannedGroup], *, scan_started_ns: int) -> None:
        """Swap the stored groups for a scan's result in one transaction.

        Readers and overlapping scans see either the old set or the new one, never a partial set, and the instant the
        new set covers is stored with it.
        """
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute("DELETE FROM group_members")
            conn.execute("DELETE FROM duplicate_groups")
            for group in groups:
                cursor = conn.execute(
                    """
                    INSERT INTO duplicate_groups
                        (tier, fingerprint, recommended_keep_path, status, created_at, updated_at)
                    VALUES (?, ?, ?, ?, ?, ?)
                    """,
                    (group.tier.value, group.fingerprint, group.recommended_keep_path, group.status.value, now, now),
                )
                conn.executemany(
                    """
                    INSERT INTO group_members (group_id, relative_path, size_bytes, mtime_ns)
                    VALUES (?, ?, ?, ?)
                    """,
                    [
                        (cursor.lastrowid, member.relative_path, member.size_bytes, member.mtime_ns)
                        for member in group.members
                    ],
                )
            _write_meta(conn, _META_SCAN_COVERAGE_NS, str(scan_started_ns))

    def list_groups(self, *, status: GroupStatus | None = None) -> list[DuplicateGroup]:
        query = """
            SELECT id, tier, fingerprint, recommended_keep_path, status
            FROM duplicate_groups
        """
        params: tuple[str, ...] = ()
        if status is not None:
            query += " WHERE status = ?"
            params = (status.value,)
        query += " ORDER BY id ASC"
        groups: list[DuplicateGroup] = []
        with self._conn() as conn:
            rows = conn.execute(query, params).fetchall()
            for row in rows:
                group_id = int(row["id"])
                member_rows = conn.execute(
                    """
                    SELECT relative_path, size_bytes, mtime_ns
                    FROM group_members
                    WHERE group_id = ?
                    ORDER BY relative_path ASC
                    """,
                    (group_id,),
                ).fetchall()
                members = tuple(
                    DuplicateMember(
                        relative_path=str(member["relative_path"]),
                        size_bytes=int(member["size_bytes"]),
                        mtime_ns=int(member["mtime_ns"]),
                    )
                    for member in member_rows
                )
                groups.append(
                    DuplicateGroup(
                        group_id=group_id,
                        tier=DedupTier(str(row["tier"])),
                        fingerprint=str(row["fingerprint"]),
                        recommended_keep_path=str(row["recommended_keep_path"]),
                        status=GroupStatus(str(row["status"])),
                        members=members,
                    )
                )
        return groups

    def get_group(self, group_id: int) -> DuplicateGroup | None:
        groups = self.list_groups()
        for group in groups:
            if group.group_id == group_id:
                return group
        return None

    def update_group_status(self, group_id: int, status: GroupStatus) -> None:
        now = datetime.now(UTC).isoformat()
        with self._conn() as conn:
            conn.execute(
                "UPDATE duplicate_groups SET status = ?, updated_at = ? WHERE id = ?",
                (status.value, now, group_id),
            )

    def increment_compile_jobs_prevented(self, count: int) -> None:
        if count <= 0:
            return
        current = self.get_compile_jobs_prevented()
        self._set_meta(_META_COMPILE_JOBS_PREVENTED, str(current + count))

    def get_compile_jobs_prevented(self) -> int:
        raw = self._get_meta(_META_COMPILE_JOBS_PREVENTED)
        return int(raw) if raw.isdigit() else 0

    def set_scan_progress(self, progress: ScanProgress) -> None:
        payload = json.dumps(
            {
                "phase": progress.phase,
                "files_scanned": progress.files_scanned,
                "files_total": progress.files_total,
                "groups_found": progress.groups_found,
                "message": progress.message,
            }
        )
        self._set_meta(_META_SCAN_PROGRESS, payload)

    def get_scan_progress(self) -> ScanProgress:
        raw = self._get_meta(_META_SCAN_PROGRESS)
        if not raw:
            return ScanProgress()
        try:
            loaded = json.loads(raw)
        except json.JSONDecodeError:
            return ScanProgress()
        if not isinstance(loaded, dict):
            return ScanProgress()
        phase = loaded.get("phase", "idle")
        if phase not in {"idle", "scanning", "grouping", "done", "failed"}:
            phase = "idle"
        return ScanProgress(
            phase=phase,
            files_scanned=int(loaded.get("files_scanned", 0)),
            files_total=int(loaded.get("files_total", 0)),
            groups_found=int(loaded.get("groups_found", 0)),
            message=str(loaded.get("message", "")),
        )

    def mark_scan_complete(self) -> None:
        self._set_meta(_META_LAST_SCAN_AT, datetime.now(UTC).isoformat())

    def get_last_scan_at(self) -> str | None:
        raw = self._get_meta(_META_LAST_SCAN_AT)
        return raw or None

    def confirm_scan_coverage(self, scan_started_ns: int) -> None:
        """Record that the stored groups still describe every file written before ``scan_started_ns``."""
        self._set_meta(_META_SCAN_COVERAGE_NS, str(scan_started_ns))

    def get_scan_coverage_ns(self) -> int:
        """The instant up to which the stored groups cover the corpus; 0 before the first scan."""
        raw = self._get_meta(_META_SCAN_COVERAGE_NS)
        return int(raw) if raw.isdigit() else 0

    def build_stats(self, *, eligible_raw_count: int) -> DedupStats:
        open_groups = self.list_groups(status=GroupStatus.OPEN)
        return DedupStats(
            duplicate_groups_pending=len(open_groups),
            compile_jobs_prevented=self.get_compile_jobs_prevented(),
            eligible_raw_count=eligible_raw_count,
            excluded_raw_count=len(self.get_excluded_paths()),
            trashed_raw_count=len(self.get_trashed_paths()),
        )

    def _get_meta(self, key: str) -> str:
        with self._conn() as conn:
            row = conn.execute("SELECT value FROM dedup_meta WHERE key = ?", (key,)).fetchone()
        if row is None:
            return ""
        return str(row["value"])

    def _set_meta(self, key: str, value: str) -> None:
        with self._conn() as conn:
            _write_meta(conn, key, value)
