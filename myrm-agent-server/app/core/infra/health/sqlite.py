"""SQLite health checker with integrity verification and backup-based recovery.

[INPUT]
- myrm_agent_harness.infra.health::HealthChecker (POS: 健康检查抽象基类)
- myrm_agent_harness.infra.sqlite_backup::SQLiteBackupManager (POS: SQLite 热备份工具)
- app.config.settings::settings (POS: 应用配置)

[OUTPUT]
- SQLiteHealthChecker: SQLite 健康检查 + PRAGMA quick_check + 备份恢复

[POS]
SQLite 健康检查器。执行 SELECT 1 探活 + PRAGMA quick_check 完整性检测。
检测到损坏时自动从备份恢复（quarantine 损坏文件 → 恢复最新有效快照）。
遵循零数据丢失底线原则：依靠 SQLite 原生 WAL 恢复 + 备份兜底。
"""

from __future__ import annotations

import logging
import sqlite3
from pathlib import Path

from myrm_agent_harness.infra.health.health_checker import (
    HealthChecker,
    HealthCheckResult,
    HealthStatus,
    RecoveryResult,
    RecoveryStatus,
)
from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager

from app.config.settings import settings

logger = logging.getLogger(__name__)

_BACKUP_SUBDIR = "sqlite_backups"


def _get_backup_manager() -> SQLiteBackupManager:
    db_path = Path(settings.database.sqlite_path)
    backup_dir = db_path.parent / _BACKUP_SUBDIR
    return SQLiteBackupManager(db_path=db_path, backup_dir=backup_dir)


class SQLiteHealthChecker(HealthChecker):
    """Health checker for SQLite database with integrity verification.

    Two-layer probe:
      1. ``SELECT 1`` — connection liveness (catches locked / missing)
      2. ``PRAGMA quick_check`` — B-tree structural integrity (catches corruption)

    Recovery:
      Uses ``SQLiteBackupManager.restore_latest()`` to quarantine the corrupted
      database and restore from the most recent valid backup snapshot.

    Safety:
      Never deletes WAL/SHM files or kills processes. Relies on SQLite's
      native WAL recovery for stale journal files.
    """

    def __init__(self, force_wal_cleanup: bool = False) -> None:
        self.sqlite_path = Path(settings.database.sqlite_path)
        if force_wal_cleanup:
            logger.warning(
                "force_wal_cleanup is ignored. Manual WAL deletion is "
                "prohibited to prevent data loss."
            )

    async def check(self) -> HealthCheckResult:
        """Check SQLite database health via SELECT 1 + PRAGMA quick_check."""
        if not self.sqlite_path.exists():
            return HealthCheckResult(
                status=HealthStatus.HEALTHY,
                message="SQLite database does not exist yet (first start)",
                details={"path": str(self.sqlite_path)},
            )

        wal_file = self.sqlite_path.with_name(self.sqlite_path.name + "-wal")
        shm_file = self.sqlite_path.with_name(self.sqlite_path.name + "-shm")
        has_wal = wal_file.exists()
        has_shm = shm_file.exists()

        try:
            conn = sqlite3.connect(
                str(self.sqlite_path), timeout=5.0, check_same_thread=False
            )
        except sqlite3.Error as err:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Database connection failed: {err}",
                details={
                    "path": str(self.sqlite_path),
                    "error": str(err),
                    "has_wal": has_wal,
                    "has_shm": has_shm,
                },
            )

        try:
            conn.execute("SELECT 1")

            qc_row = conn.execute("PRAGMA quick_check").fetchone()
            qc_result = qc_row[0] if qc_row else ""

            if qc_result == "ok":
                return HealthCheckResult(
                    status=HealthStatus.HEALTHY,
                    message="SQLite database is healthy (quick_check passed)",
                    details={
                        "path": str(self.sqlite_path),
                        "has_wal": has_wal,
                        "has_shm": has_shm,
                        "quick_check": "ok",
                    },
                )

            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message="Database corruption detected by PRAGMA quick_check",
                details={
                    "path": str(self.sqlite_path),
                    "quick_check": qc_result,
                    "has_wal": has_wal,
                    "has_shm": has_shm,
                },
            )

        except sqlite3.Error as err:
            return HealthCheckResult(
                status=HealthStatus.UNHEALTHY,
                message=f"Database integrity check failed: {err}",
                details={
                    "path": str(self.sqlite_path),
                    "error": str(err),
                    "has_wal": has_wal,
                    "has_shm": has_shm,
                },
            )
        finally:
            conn.close()

    async def recover(self) -> RecoveryResult:
        """Recover SQLite database from the latest valid backup.

        Quarantines the corrupted database files and restores from the most
        recent snapshot that passes ``PRAGMA integrity_check``.
        """
        manager = _get_backup_manager()
        result = manager.restore_latest()

        if result.restored:
            actions = [
                f"Quarantined corrupted database to {result.quarantine_dir}"
                if result.quarantine_dir
                else "No quarantine needed",
                f"Restored from backup snapshot: {result.snapshot_file}",
            ]
            logger.info(
                "[SQLiteHealth] Database recovered from snapshot %s",
                result.snapshot_file,
            )
            return RecoveryResult(
                status=RecoveryStatus.SUCCESS,
                message=f"Database restored from backup: {result.snapshot_file}",
                actions_taken=actions,
                details={
                    "snapshot": result.snapshot_file,
                    "quarantine": result.quarantine_dir,
                },
            )

        logger.error(
            "[SQLiteHealth] Recovery failed: %s",
            result.error or "no backups available",
        )
        return RecoveryResult(
            status=RecoveryStatus.FAILED,
            message=f"Recovery failed: {result.error or 'no backups available'}",
            actions_taken=[
                f"Quarantined corrupted database to {result.quarantine_dir}"
                if result.quarantine_dir
                else "No backup snapshots found",
            ],
            details={"error": result.error, "quarantine": result.quarantine_dir},
        )
