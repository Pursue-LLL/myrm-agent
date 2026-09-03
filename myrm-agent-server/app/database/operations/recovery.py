"""数据库容灾与恢复模块

提供底层 SQLite 数据库严重损坏时的非破坏性 B-Tree 坏页跳跃行级抢救机制。
底层算法由 Harness 基础设施层 ``myrm_agent_harness.infra.sqlite_salvage.SQLiteRowidSalvageEngine`` 驱动。

常规热备份与快照恢复由 ``myrm_agent_harness.infra.sqlite_backup.SQLiteBackupManager`` 负责。

[INPUT]
- db_path: str 损坏的 SQLite 数据库文件绝对路径

[OUTPUT]
- rescue_database: 尝试通过 B-Tree 坏页二分跳跃与 Schema 重放抢救数据库，返回是否成功。
- rescue_database_detailed: 返回包含各表恢复行数、跳过坏页范围与 SHA-256 审计指标的完整 SalvageResult。

[POS]
Server 业务数据库容灾层。在系统启动（lifespan）捕获 malformed 崩溃时触发自愈。
"""

from __future__ import annotations

import logging
import shutil
from pathlib import Path

from myrm_agent_harness.infra.sqlite_salvage import (
    SalvageResult,
    SQLiteRowidSalvageEngine,
)

logger = logging.getLogger(__name__)


def _cleanup_wal_files(base_path: Path) -> None:
    """清理 SQLite 的 WAL 和 SHM 文件"""
    for suffix in ("-wal", "-shm"):
        companion = base_path.with_name(f"{base_path.name}{suffix}")
        if companion.exists():
            try:
                companion.unlink()
            except OSError:
                pass


def _move_db_with_wal(src: Path, dst: Path) -> None:
    """移动数据库文件及其 WAL/SHM 附属文件"""
    if src.exists():
        shutil.move(str(src), str(dst))

    for suffix in ("-wal", "-shm"):
        src_companion = src.with_name(f"{src.name}{suffix}")
        dst_companion = dst.with_name(f"{dst.name}{suffix}")
        if src_companion.exists():
            try:
                shutil.move(str(src_companion), str(dst_companion))
            except OSError:
                pass


def rescue_database(db_path: str) -> bool:
    """尝试通过 B-Tree 坏页跳跃机制抢救损坏的 SQLite 数据库。

    在独立沙箱中保留原始损坏副本，逐表通过二分搜索隔离坏页并抢救幸存数据。
    """
    result = rescue_database_detailed(db_path)
    return result.success


def rescue_database_detailed(db_path: str) -> SalvageResult:
    """执行深度数据抢救并返回结构化审计指标。"""
    path = Path(db_path)
    if not path.exists():
        return SalvageResult(
            source_path=str(path),
            recovered_path=str(path),
            success=False,
            total_recovered_rows=0,
            table_stats={},
            orphans_reconstructed=0,
            fts_rebuilt=[],
            elapsed_ms=0.0,
            source_sha256="",
            recovered_sha256="",
            error=f"Database file does not exist: {path}",
        )

    corrupted_path = path.with_suffix(".db.corrupted")
    try:
        if corrupted_path.exists():
            corrupted_path.unlink()
            _cleanup_wal_files(corrupted_path)

        _move_db_with_wal(path, corrupted_path)
        logger.warning(
            "Isolated corrupted database to %s for B-Tree page-skipping salvage",
            corrupted_path,
        )

        engine = SQLiteRowidSalvageEngine()
        result = engine.salvage_database(
            source_path=corrupted_path,
            output_path=path,
            isolate_sandbox=True,
        )

        if result.success:
            logger.info(
                "Database salvage succeeded: recovered %d rows across %d tables, "
                "%d orphan sessions reconstructed in %.1fms",
                result.total_recovered_rows,
                len(result.table_stats),
                result.orphans_reconstructed,
                result.elapsed_ms,
            )
            return result

        logger.error("Database salvage engine reported failure: %s", result.error)
        _rollback_corrupted_state(path, corrupted_path)
        return result
    except Exception as exc:
        logger.error("Unexpected exception during database rescue: %s", exc)
        _rollback_corrupted_state(path, corrupted_path)
        return SalvageResult(
            source_path=str(corrupted_path),
            recovered_path=str(path),
            success=False,
            total_recovered_rows=0,
            table_stats={},
            orphans_reconstructed=0,
            fts_rebuilt=[],
            elapsed_ms=0.0,
            source_sha256="",
            recovered_sha256="",
            error=str(exc),
        )


def _rollback_corrupted_state(original_path: Path, corrupted_path: Path) -> None:
    """恢复原始损坏现场以允许后续快照还原重试。"""
    if original_path.exists():
        original_path.unlink()
        _cleanup_wal_files(original_path)
    if corrupted_path.exists():
        _move_db_with_wal(corrupted_path, original_path)
