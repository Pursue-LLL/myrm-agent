"""数据库容灾与恢复模块

提供底层 SQLite 数据库严重损坏时的非破坏性 B-Tree 坏页跳跃行级抢救机制。
底层算法由 Harness 基础设施层 ``myrm_agent_harness.infra.sqlite_salvage.SQLiteRowidSalvageEngine`` 驱动。

常规热备份与快照恢复由 ``myrm_agent_harness.infra.sqlite_backup.SQLiteBackupManager`` 负责。

[INPUT]
- db_path: str SQLite 数据库文件绝对路径
- myrm_agent_harness.utils.db.sqlite::validate_sqlite_header/check_page_count_invariant/quick_check_sync (POS: 文件级损坏判据)

[OUTPUT]
- database_is_damaged: 文件本身是否损坏（只有确凿的损坏证据才返回 True）；救援会重写文件，只有它为 True 时才该调用 rescue_database。
- reports_corruption: 一次失败本身是否带有 SQLite 的损坏报告（SQLITE_CORRUPT / SQLITE_NOTADB，含 SQLAlchemy 的 orig 与异常链）。
- rescue_database: 尝试通过 B-Tree 坏页二分跳跃与 Schema 重放抢救数据库，返回是否成功。
- rescue_database_detailed: 返回包含各表恢复行数、跳过坏页范围与 SHA-256 审计指标的完整 SalvageResult。

[POS]
Server 业务数据库容灾层。数据库初始化失败后，由 lifespan 先用 reports_corruption 与 database_is_damaged 判断是否真的损坏，再触发自愈。
"""

from __future__ import annotations

import logging
import shutil
import sqlite3
from contextlib import closing
from pathlib import Path

from myrm_agent_harness.infra.sqlite_salvage import (
    SalvageResult,
    SQLiteRowidSalvageEngine,
)
from myrm_agent_harness.utils.db.sqlite import (
    SQLiteIntegrityError,
    check_page_count_invariant,
    quick_check_sync,
    validate_sqlite_header,
)

logger = logging.getLogger(__name__)

_CORRUPTION_ERROR_CODES = frozenset({sqlite3.SQLITE_CORRUPT, sqlite3.SQLITE_NOTADB})
_PROBE_LOCK_TIMEOUT_SECONDS = 5.0


def _is_corruption_error(exc: sqlite3.DatabaseError) -> bool:
    code = getattr(exc, "sqlite_errorcode", None)
    return code is not None and (code & 0xFF) in _CORRUPTION_ERROR_CODES


def reports_corruption(error: BaseException) -> bool:
    """Whether SQLite itself called the file corrupt anywhere in the chain of causes behind ``error``.

    SQLAlchemy keeps the driver's error in ``orig``. A start that failed on such an error met the damage first-hand,
    so a later integrity probe that reads clean cannot overrule it.
    """
    pending: list[BaseException] = [error]
    seen: set[int] = set()
    while pending:
        current = pending.pop()
        if id(current) in seen:
            continue
        seen.add(id(current))
        if isinstance(current, sqlite3.DatabaseError) and _is_corruption_error(current):
            return True
        pending.extend(
            linked
            for linked in (getattr(current, "orig", None), current.__cause__, current.__context__)
            if isinstance(linked, BaseException)
        )
    return False


def database_is_damaged(db_path: str) -> bool:
    """Whether the file itself is corrupt, the one failure ``rescue_database`` can repair.

    Runs the harness's file-level guards (header, truncation) and a read-only ``quick_check``. Only positive evidence
    of damage answers True: a missing file, a lock or a read error says nothing about the pages, so it answers False
    and the caller leaves the file alone.
    """
    path = Path(db_path)
    if not path.is_file():
        return False
    try:
        validate_sqlite_header(path)
        check_page_count_invariant(path)
        read_only_uri = f"{path.resolve().as_uri()}?mode=ro"
        with closing(sqlite3.connect(read_only_uri, uri=True, timeout=_PROBE_LOCK_TIMEOUT_SECONDS)) as conn:
            quick_check_sync(conn)
    except SQLiteIntegrityError:
        return True
    except sqlite3.DatabaseError as exc:
        return _is_corruption_error(exc)
    return False


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
                "Database salvage succeeded: recovered %d rows across %d tables, %d orphan sessions reconstructed in %.1fms",
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
