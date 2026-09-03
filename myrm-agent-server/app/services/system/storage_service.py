"""Storage Inspection and Database Optimization Service.

[INPUT]
- app.config.settings::get_settings (POS: System paths & database settings)
- myrm_agent_harness.api.hooks::count_running_background_shell_jobs (POS: Background tasks safety probe)

[OUTPUT]
- DatabaseStorageBreakdown: Physical SQLite file sizes data model
- StorageOptimizePreflightData: Preflight inspection response data model
- StorageService: Core database storage inspection, safe hot backup, and optimization service

[POS]
Core storage inspection, online hot backup, and SQLite database compaction/vacuum optimization service.
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from pathlib import Path
from pydantic import BaseModel

from app.config.settings import get_settings

logger = logging.getLogger(__name__)


class DatabaseStorageBreakdown(BaseModel):
    main_db_bytes: int
    wal_bytes: int
    shm_bytes: int
    total_bytes: int


class SubdirUsage(BaseModel):
    name: str
    bytes: int


class StorageOptimizePreflightData(BaseModel):
    data_dir: str
    db_breakdown: DatabaseStorageBreakdown
    disk_free_bytes: int
    can_deep_optimize: bool
    recommended_mode: str
    active_background_jobs: int
    is_safe_to_optimize: bool
    reason: str | None = None


def dir_size_bytes(path: Path) -> int:
    """Recursively sum file sizes under *path*. Returns 0 if path doesn't exist."""
    if not path.is_dir():
        return 0
    total = 0
    for entry in path.rglob("*"):
        if entry.is_file():
            try:
                total += entry.stat().st_size
            except OSError:
                pass
    return total


def get_sqlite_breakdown(data_dir: Path) -> DatabaseStorageBreakdown:
    """Return physical file sizes for SQLite data.db triplet (data.db, -wal, -shm)."""
    def _size(name: str) -> int:
        p = data_dir / name
        return p.stat().st_size if p.exists() else 0

    main_size = _size("data.db")
    wal_size = _size("data.db-wal")
    shm_size = _size("data.db-shm")
    return DatabaseStorageBreakdown(
        main_db_bytes=main_size,
        wal_bytes=wal_size,
        shm_bytes=shm_size,
        total_bytes=main_size + wal_size + shm_size,
    )


def perform_sqlite_backup(src_db: Path, backup_file: Path) -> None:
    """Perform a clean online backup using sqlite3 backup API.

    Rotates existing backup file by overwriting it to prevent secondary disk bloat.
    """
    if not src_db.exists():
        return
    if backup_file.exists():
        try:
            backup_file.unlink()
        except OSError:
            pass
    src_conn = sqlite3.connect(str(src_db), timeout=10.0)
    dest_conn = sqlite3.connect(str(backup_file), timeout=10.0)
    try:
        src_conn.backup(dest_conn)
    finally:
        dest_conn.close()
        src_conn.close()


def execute_storage_optimization(
    data_dir: Path,
    mode: str,
    create_backup: bool,
) -> tuple[int, int, str | None]:
    """Execute optimization in worker thread: FTS optimize + VACUUM (deep) + WAL TRUNCATE."""
    db_file = data_dir / "data.db"
    if not db_file.exists():
        return 0, 0, None

    before_breakdown = get_sqlite_breakdown(data_dir)
    before_bytes = before_breakdown.total_bytes

    backup_path_str: str | None = None
    if create_backup:
        backup_file = data_dir / "data.db.optimize_backup"
        perform_sqlite_backup(db_file, backup_file)
        backup_path_str = str(backup_file)

    conn = sqlite3.connect(str(db_file), timeout=30.0)
    try:
        cursor = conn.cursor()
        # 1. Optimize FTS5 B-tree segments if table exists
        cursor.execute("SELECT name FROM sqlite_master WHERE type='table' AND name='messages_fts'")
        if cursor.fetchone():
            try:
                cursor.execute("INSERT INTO messages_fts(messages_fts) VALUES('optimize')")
                conn.commit()
            except sqlite3.OperationalError as exc:
                logger.warning("FTS optimize skipped or failed: %s", exc)

        # 2. In deep mode, reclaim freelist pages via VACUUM
        if mode == "deep":
            cursor.execute("VACUUM")

        # 3. Truncate WAL file to reclaim active log storage
        cursor.execute("PRAGMA wal_checkpoint(TRUNCATE)")
        cursor.close()
    finally:
        conn.close()

    after_breakdown = get_sqlite_breakdown(data_dir)
    after_bytes = after_breakdown.total_bytes
    return before_bytes, after_bytes, backup_path_str


def check_storage_preflight(data_dir: Path) -> StorageOptimizePreflightData:
    """Pre-check disk headroom, database sizes, and active background jobs before optimization."""
    try:
        usage = shutil.disk_usage(data_dir if data_dir.exists() else data_dir.parent)
        free_bytes = usage.free
    except OSError:
        free_bytes = 0

    db_breakdown = get_sqlite_breakdown(data_dir)

    from myrm_agent_harness.api.hooks import count_running_background_shell_jobs

    running_jobs = count_running_background_shell_jobs()

    # VACUUM requires roughly a 1.2x copy headroom of the total database size
    required_headroom = int(db_breakdown.total_bytes * 1.2)
    can_deep = free_bytes >= required_headroom

    is_safe = running_jobs == 0
    reason: str | None = None
    if running_jobs > 0:
        reason = f"{running_jobs} active background job(s) running. Wait for completion before optimizing."
    elif not can_deep and free_bytes < db_breakdown.total_bytes:
        reason = "Low disk headroom. Deep VACUUM unavailable; light optimize (FTS + WAL truncate) recommended."

    recommended_mode = "deep" if can_deep else "light"

    return StorageOptimizePreflightData(
        data_dir=str(data_dir),
        db_breakdown=db_breakdown,
        disk_free_bytes=free_bytes,
        can_deep_optimize=can_deep,
        recommended_mode=recommended_mode,
        active_background_jobs=running_jobs,
        is_safe_to_optimize=is_safe,
        reason=reason,
    )
