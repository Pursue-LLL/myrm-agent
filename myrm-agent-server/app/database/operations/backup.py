"""SQLite backup manager factory.

Provides a single entry-point to obtain a configured
``SQLiteBackupManager`` for the application database.

[INPUT]
- myrm_agent_harness.infra.sqlite_backup::SQLiteBackupManager (POS: SQLite 热备份工具)
- app.config.settings::settings (POS: 应用配置)

[OUTPUT]
- get_sqlite_backup_manager: Returns a configured SQLiteBackupManager, or None
  when the database is in-memory or the file does not exist.

[POS]
业务层 SQLite 备份工厂。将 db_path 解析、:memory: 安全检查、backup_dir 路径约定
集中到一处，所有调用方统一使用。
"""

from __future__ import annotations

from pathlib import Path

from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager

from app.config.settings import settings

_BACKUP_SUBDIR = "sqlite_backups"


def get_sqlite_backup_manager() -> SQLiteBackupManager | None:
    """Return a configured ``SQLiteBackupManager`` for the app database.

    Returns ``None`` when the database is ``:memory:`` or the file does not
    exist on disk, signalling that backup operations should be skipped.
    """
    db_path_str = settings.database.sqlite_path
    if db_path_str == ":memory:":
        return None

    db_path = Path(db_path_str)
    if not db_path.exists():
        return None

    backup_dir = db_path.parent / _BACKUP_SUBDIR
    return SQLiteBackupManager(db_path=db_path, backup_dir=backup_dir)
