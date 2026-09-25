"""[INPUT]
- app.services.repair.models::RepairAction, RepairActionId, RepairActionExecuteRequest, RepairActionExecuteResult, RepairRiskLevel, RepairScope (POS: 修复动作数据契约与模型定义)
- app.database.operations.backup::get_sqlite_backup_manager (POS: SQLite 备份管理器获取)

[OUTPUT]
- get_sqlite_backup_manager: 获取 SQLite 备份管理器
- build_sqlite_backup_action: 构建 SQLite 备份推荐动作
- execute_sqlite_backup: 执行 SQLite 备份动作
- execute_sqlite_restore: 执行 SQLite 恢复动作

[POS]
Server 业务层 SQLite 热备份与还原自愈动作具体执行逻辑。
"""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path
from typing import TYPE_CHECKING

from .models import (
    RepairAction,
    RepairActionExecuteRequest,
    RepairActionExecuteResult,
    RepairActionId,
    RepairRiskLevel,
    RepairScope,
)

if TYPE_CHECKING:
    from myrm_agent_harness.infra.sqlite_backup import SQLiteBackupManager


def get_sqlite_backup_manager() -> SQLiteBackupManager | None:
    from app.database.operations.backup import get_sqlite_backup_manager as _get_mgr

    return _get_mgr()


def _resolve_manager(
    manager: SQLiteBackupManager | None = None,
    manager_getter: Callable[[], SQLiteBackupManager | None] | None = None,
) -> SQLiteBackupManager | None:
    if manager is not None:
        return manager
    if manager_getter is not None:
        return manager_getter()
    return get_sqlite_backup_manager()


def build_sqlite_backup_action() -> RepairAction | None:
    try:
        from app.config.settings import settings

        db_path = Path(settings.database.sqlite_path)
        if not db_path.exists():
            return None
    except Exception:
        return None

    return RepairAction(
        action_id=RepairActionId.SQLITE_BACKUP_NOW,
        title="Create SQLite backup",
        description="Create a hot-backup of the SQLite database for disaster recovery.",
        component="Database",
        layer="server",
        scope=RepairScope.CURRENT_WORKSPACE,
        risk_level=RepairRiskLevel.LOW,
        requires_approval=False,
        executable=True,
        method="POST",
        endpoint=f"/health/repair-actions/{RepairActionId.SQLITE_BACKUP_NOW.value}/execute",
        reason="Periodic backup ensures data can be recovered after corruption.",
        expected_effect="Creates a verified backup snapshot with SHA-256 checksum.",
        does_not_do=[
            "Does not modify the live database.",
            "Does not block agent execution.",
        ],
    )


def execute_sqlite_backup(
    request: RepairActionExecuteRequest,
    manager: SQLiteBackupManager | None = None,
    manager_getter: Callable[[], SQLiteBackupManager | None] | None = None,
) -> RepairActionExecuteResult:
    if request.dry_run:
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_BACKUP_NOW,
            status="dry_run",
            changed=False,
            dry_run=True,
            message="Would create a hot-backup of the SQLite database.",
        )

    try:
        mgr = _resolve_manager(manager=manager, manager_getter=manager_getter)
        if mgr is None:
            return RepairActionExecuteResult(
                action_id=RepairActionId.SQLITE_BACKUP_NOW,
                status="failed",
                changed=False,
                dry_run=False,
                message="Cannot backup: database is in-memory or file not found",
            )
        record = mgr.create_backup()
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_BACKUP_NOW,
            status="completed",
            changed=True,
            dry_run=False,
            message=f"Backup created: {record.file_name} ({record.size_bytes} bytes)",
            details={
                "backup_id": record.backup_id,
                "file_name": record.file_name,
                "size_bytes": record.size_bytes,
                "checksum": record.checksum_sha256[:16] + "…",
            },
        )
    except Exception as exc:
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_BACKUP_NOW,
            status="failed",
            changed=False,
            dry_run=False,
            message=f"Backup failed: {exc}",
        )


def execute_sqlite_restore(
    request: RepairActionExecuteRequest,
    manager: SQLiteBackupManager | None = None,
    manager_getter: Callable[[], SQLiteBackupManager | None] | None = None,
) -> RepairActionExecuteResult:
    if request.dry_run:
        try:
            mgr = _resolve_manager(manager=manager, manager_getter=manager_getter)
            backups = mgr.list_backups() if mgr else []
        except Exception:
            backups = []
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_RESTORE_LATEST,
            status="dry_run",
            changed=False,
            dry_run=True,
            message=f"Would restore from latest backup ({len(backups)} available).",
            details={"available_backups": len(backups)},
        )

    if not request.confirm:
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_RESTORE_LATEST,
            status="confirmation_required",
            changed=False,
            dry_run=False,
            message="Database restore requires confirm=true. This will replace the current database.",
        )

    try:
        mgr = _resolve_manager(manager=manager, manager_getter=manager_getter)
        if mgr is None:
            return RepairActionExecuteResult(
                action_id=RepairActionId.SQLITE_RESTORE_LATEST,
                status="failed",
                changed=False,
                dry_run=False,
                message="Cannot restore: database is in-memory or file not found",
            )
        result = mgr.restore_latest()
        if result.restored:
            return RepairActionExecuteResult(
                action_id=RepairActionId.SQLITE_RESTORE_LATEST,
                status="completed",
                changed=True,
                dry_run=False,
                message=f"Database restored from {result.snapshot_file}",
                details={
                    "snapshot": result.snapshot_file,
                    "quarantine": result.quarantine_dir,
                },
            )
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_RESTORE_LATEST,
            status="failed",
            changed=False,
            dry_run=False,
            message=f"Restore failed: {result.error}",
        )
    except Exception as exc:
        return RepairActionExecuteResult(
            action_id=RepairActionId.SQLITE_RESTORE_LATEST,
            status="failed",
            changed=False,
            dry_run=False,
            message=f"Restore failed: {exc}",
        )
