"""数据库容灾与恢复模块

提供底层 SQLite 数据库损坏时的抢救、备份与恢复机制。

[INPUT]
- (无)

[OUTPUT]
- rescue_database: 尝试通过 dump 机制抢救损坏的 SQLite 数据库。
- restore_from_backup: 尝试从最后已知良好备份恢复。
- backup_database: 创建最后已知良好备份。

[POS]
数据库容灾层。负责在数据库文件损坏时进行抢救和恢复。
"""

import logging
import shutil
import sqlite3
from pathlib import Path

logger = logging.getLogger(__name__)


def _cleanup_wal_files(base_path: Path) -> None:
    """清理 SQLite 的 WAL 和 SHM 文件"""
    wal_path = base_path.with_name(f"{base_path.name}-wal")
    shm_path = base_path.with_name(f"{base_path.name}-shm")
    if wal_path.exists():
        wal_path.unlink()
    if shm_path.exists():
        shm_path.unlink()


def _move_db_with_wal(src: Path, dst: Path) -> None:
    """移动数据库文件及其 WAL/SHM 附属文件"""
    if src.exists():
        shutil.move(str(src), str(dst))

    src_wal = src.with_name(f"{src.name}-wal")
    dst_wal = dst.with_name(f"{dst.name}-wal")
    if src_wal.exists():
        shutil.move(str(src_wal), str(dst_wal))

    src_shm = src.with_name(f"{src.name}-shm")
    dst_shm = dst.with_name(f"{dst.name}-shm")
    if src_shm.exists():
        shutil.move(str(src_shm), str(dst_shm))


def rescue_database(db_path: str) -> bool:
    """尝试通过 dump 机制抢救损坏的 SQLite 数据库

    将旧库中能读出的数据逐行导出并导入到新库中。
    """
    path = Path(db_path)
    if not path.exists():
        return False

    corrupted_path = path.with_suffix(".db.corrupted")
    try:
        # 如果已经存在 corrupted，先删除
        if corrupted_path.exists():
            corrupted_path.unlink()
            _cleanup_wal_files(corrupted_path)

        _move_db_with_wal(path, corrupted_path)

        logger.info("Attempting to rescue corrupted database: %s", corrupted_path)
        # 尝试 dump
        with sqlite3.connect(str(corrupted_path)) as old_conn:
            with sqlite3.connect(str(path)) as new_conn:
                # 开启外层大事务
                new_conn.execute("BEGIN TRANSACTION;")
                for line in old_conn.iterdump():
                    # 过滤掉 dump 内部的事务控制语句，避免破坏外层事务
                    if line.startswith("BEGIN") or line.startswith("COMMIT") or line.startswith("ROLLBACK"):
                        continue
                    try:
                        new_conn.execute(line)
                    except sqlite3.Error as e:
                        logger.warning("Skipped malformed line during rescue: %s", e)
                new_conn.execute("COMMIT;")
        logger.info("Database rescue completed successfully.")
        return True
    except Exception as e:
        logger.error("Database rescue failed: %s", e)
        # 恢复现场
        if path.exists():
            path.unlink()
            _cleanup_wal_files(path)
        if corrupted_path.exists():
            _move_db_with_wal(corrupted_path, path)
        return False


def restore_from_backup(db_path: str) -> bool:
    """尝试从最后已知良好备份恢复"""
    path = Path(db_path)
    bak_path = path.with_suffix(".db.bak")
    if not bak_path.exists():
        return False

    try:
        if path.exists():
            corrupted_path = path.with_suffix(".db.corrupted_before_restore")
            if corrupted_path.exists():
                corrupted_path.unlink()
                _cleanup_wal_files(corrupted_path)
            _move_db_with_wal(path, corrupted_path)

        shutil.copy2(str(bak_path), str(path))
        # 备份恢复后，确保没有旧的 WAL 文件干扰
        _cleanup_wal_files(path)

        logger.info("Restored database from backup: %s", bak_path)
        return True
    except Exception as e:
        logger.error("Restore from backup failed: %s", e)
        return False


def backup_database(db_path: str) -> None:
    """创建最后已知良好备份"""
    path = Path(db_path)
    if not path.exists():
        return

    bak_path = path.with_suffix(".db.bak")
    try:
        # 使用 sqlite3 的 backup API 进行安全备份（避免文件锁问题）
        with sqlite3.connect(str(path)) as src:
            with sqlite3.connect(str(bak_path)) as dst:
                src.backup(dst)
        logger.info("Created last-known-good backup: %s", bak_path)
    except Exception as e:
        logger.error("Failed to create database backup: %s", e)
