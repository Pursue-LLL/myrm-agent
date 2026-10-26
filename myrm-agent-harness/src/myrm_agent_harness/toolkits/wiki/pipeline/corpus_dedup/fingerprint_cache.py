"""Per-file fingerprint cache that lets an incremental dedup scan rehash only the files that changed.

[INPUT]
- corpus_dedup.types::RawFileFingerprint (POS: fingerprints collected for one raw file)

[OUTPUT]
- FINGERPRINT_SCHEMA: DDL the store creates together with the rest of ``.raw_dedup.db``
- FingerprintCache: load every cached fingerprint at once, upsert a batch, prune the vanished, keyed by raw-relative path

[POS]
Storage detail of ``CorpusDedupScanner``. It borrows the store's connection factory, so one vault keeps one SQLite
file. A cached entry is valid while the file's size and mtime are unchanged; simhash is stored as a signed 64-bit
integer because SQLite has no unsigned type. Reads and writes move whole batches per call: a scan looks at every raw
file, and a connection per file would cost more than hashing the files that did not change.
"""

from __future__ import annotations

import sqlite3
from collections.abc import Callable, Sequence
from contextlib import AbstractContextManager

from myrm_agent_harness.toolkits.wiki.pipeline.corpus_dedup.types import RawFileFingerprint

FINGERPRINT_SCHEMA = """
CREATE TABLE IF NOT EXISTS file_fingerprints (
    relative_path TEXT PRIMARY KEY,
    size_bytes INTEGER NOT NULL,
    mtime_ns INTEGER NOT NULL,
    exact_hash TEXT NOT NULL,
    normalized_hash TEXT NOT NULL,
    simhash INTEGER NOT NULL
);
"""

_SIMHASH_MASK = (1 << 64) - 1


def _simhash_to_sqlite(value: int) -> int:
    normalized = value & _SIMHASH_MASK
    if normalized >= (1 << 63):
        return normalized - (1 << 64)
    return normalized


def _simhash_from_sqlite(value: int) -> int:
    if value < 0:
        return value + (1 << 64)
    return value


def _fingerprint_from_row(row: sqlite3.Row) -> RawFileFingerprint:
    return RawFileFingerprint(
        relative_path=str(row["relative_path"]),
        exact_hash=str(row["exact_hash"]),
        normalized_hash=str(row["normalized_hash"]),
        simhash=_simhash_from_sqlite(int(row["simhash"])),
        size_bytes=int(row["size_bytes"]),
        mtime_ns=int(row["mtime_ns"]),
    )


class FingerprintCache:
    """Cached fingerprints of raw files, one row per raw-relative path."""

    def __init__(self, connect: Callable[[], AbstractContextManager[sqlite3.Connection]]) -> None:
        self._connect = connect

    def load_all(self) -> dict[str, RawFileFingerprint]:
        """Every cached fingerprint by raw-relative path, read in one query."""
        with self._connect() as conn:
            rows = conn.execute(
                "SELECT relative_path, size_bytes, mtime_ns, exact_hash, normalized_hash, simhash FROM file_fingerprints"
            ).fetchall()
        return {fingerprint.relative_path: fingerprint for fingerprint in map(_fingerprint_from_row, rows)}

    def upsert_many(self, fingerprints: Sequence[RawFileFingerprint]) -> None:
        """Store the batch in one transaction, replacing any entry the same path already has."""
        if not fingerprints:
            return
        with self._connect() as conn:
            conn.executemany(
                """
                INSERT INTO file_fingerprints
                    (relative_path, size_bytes, mtime_ns, exact_hash, normalized_hash, simhash)
                VALUES (?, ?, ?, ?, ?, ?)
                ON CONFLICT(relative_path) DO UPDATE SET
                    size_bytes = excluded.size_bytes,
                    mtime_ns = excluded.mtime_ns,
                    exact_hash = excluded.exact_hash,
                    normalized_hash = excluded.normalized_hash,
                    simhash = excluded.simhash
                """,
                [
                    (
                        item.relative_path,
                        item.size_bytes,
                        item.mtime_ns,
                        item.exact_hash,
                        item.normalized_hash,
                        _simhash_to_sqlite(item.simhash),
                    )
                    for item in fingerprints
                ],
            )

    def prune(self, active_paths: set[str]) -> int:
        """Forget every cached file that is not in ``active_paths``; return how many entries went.

        The stale paths are picked out here, not by a ``NOT IN`` over the live ones: that statement binds one variable
        per live file and fails outright on a corpus larger than SQLite's bound-variable limit.
        """
        with self._connect() as conn:
            cached = [str(row["relative_path"]) for row in conn.execute("SELECT relative_path FROM file_fingerprints")]
            stale = [(path,) for path in cached if path not in active_paths]
            conn.executemany("DELETE FROM file_fingerprints WHERE relative_path = ?", stale)
        return len(stale)
