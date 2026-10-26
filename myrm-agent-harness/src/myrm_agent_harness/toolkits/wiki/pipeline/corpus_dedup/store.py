"""SQLite persistence for raw corpus dedup governance.

[INPUT]
- core.structure::WikiStructure (POS: vault directory that holds ``.raw_dedup.db``)
- corpus_dedup.disposition_ledger / fingerprint_cache / compile_holds (POS: sub-stores that own their tables)
- corpus_dedup.types (POS: group, progress and stats value types)

[OUTPUT]
- CorpusDedupStore: duplicate groups (atomic ``replace_scan_groups``), scan progress, last-scan time and coverage instant,
  prevented-compile counter, deferred member sets, stats; ``dispositions``, ``fingerprints`` and ``holds`` sub-stores

[POS]
One SQLite file per vault, opened per call with WAL and a busy timeout, one transaction per ``with``. The store owns
the group tables and scan bookkeeping and creates every table of the file; the sub-stores borrow its connection factory.
"""

from __future__ import annotations

import contextlib
import json
import sqlite3
from collections.abc import Iterator, Sequence
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.wiki.core.structure import WikiStructure
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.compile_holds import COMPILE_HOLD_SCHEMA, CompileHoldLedger
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.disposition_ledger import (
    DISPOSITION_SCHEMA,
    DispositionLedger,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.fingerprint_cache import (
    FINGERPRINT_SCHEMA,
    FingerprintCache,
)
from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import (
    DedupStats,
    DedupTier,
    DuplicateGroup,
    DuplicateMember,
    GroupStatus,
    PlannedGroup,
    ScanProgress,
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
        self.dispositions = DispositionLedger(self._conn)
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
                + DISPOSITION_SCHEMA
                + FINGERPRINT_SCHEMA
                + COMPILE_HOLD_SCHEMA
            )

    def collect_deferred_member_sets(self) -> set[frozenset[str]]:
        groups = self.list_groups(status=GroupStatus.DEFERRED)
        return {frozenset(member.relative_path for member in group.members) for group in groups}

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
            excluded_raw_count=len(self.dispositions.get_excluded_paths()),
            trashed_raw_count=len(self.dispositions.get_trashed_paths()),
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
