"""数据库工厂

创建 SQLite 数据库引擎和会话工厂。
所有部署模式统一使用 SQLite (aiosqlite)，配置 WAL、synchronous=FULL、异步连接池、PRAGMA busy_timeout 等。
Sandbox 模式下 SQLite 文件存储在沙箱持久化卷上。
"""

import logging
import os
import sqlite3
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.config.system_status import system_status

logger = logging.getLogger(__name__)


def get_sqlite_busy_timeout_ms() -> int:
    """Milliseconds for SQLite ``PRAGMA busy_timeout`` (bounded by DatabaseSettings validator)."""
    return settings.database.sqlite_busy_timeout_ms


def get_database_url() -> str:
    """获取 SQLite 数据库连接 URL"""
    db_path = os.path.expanduser(settings.database.sqlite_path)
    Path(db_path).parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite+aiosqlite:///{db_path}"


def set_sqlite_pragma(dbapi_conn: sqlite3.Connection, _connection_record: object) -> None:
    """Apply SQLite PRAGMAs when a pooled connection is opened.

    Supports automatic journal_mode=WAL gracefully degraded fallback on network shared disk (NFS/SMB/FUSE).
    """
    from myrm_agent_harness.utils.db.sqlite import should_fallback_to_delete

    cursor = dbapi_conn.cursor()
    cursor.execute("PRAGMA foreign_keys=ON")
    cursor.execute("PRAGMA cell_size_check=ON")  # detect torn B-tree writes early

    db_file = Path(os.path.expanduser(settings.database.sqlite_path))
    is_degraded = False
    # WAL mode fallback logic for NFS/SMB/FUSE shared network storage.
    # A transient I/O error must never permanently downgrade WAL (nor flip the
    # global degraded flag); only a definitive filesystem incompatibility does.
    try:
        cursor.execute("PRAGMA journal_mode=WAL")
    except sqlite3.OperationalError as exc:
        if should_fallback_to_delete(exc, db_file):
            logger.warning(
                "SQLite PRAGMA journal_mode=WAL failed: %s. "
                "Detected network shared storage (NFS/SMB/FUSE). "
                "Gracefully falling back to journal_mode=DELETE with adaptive settings.",
                exc,
            )
            cursor.execute("PRAGMA journal_mode=DELETE")
            is_degraded = True
            # Propagate degradation status to global system_status for platform/SaaS readiness probes
            system_status.database_degraded = True
        else:
            raise

    # Adapt timeout and synchronization to mitigate NFS exclusive DELETE lock contentions
    base_timeout_ms = get_sqlite_busy_timeout_ms()
    if is_degraded:
        # Boost busy_timeout by 3x on network shared storage to prevent locking timeout under exclusive DELETE locks
        busy_timeout_ms = base_timeout_ms * 3
        # Mitigate NFS sync latency by reducing write synchronization to NORMAL (highly safe on transactional DELETE)
        synchronous_mode = "NORMAL"
    else:
        busy_timeout_ms = base_timeout_ms
        synchronous_mode = "FULL"

    cursor.execute(f"PRAGMA busy_timeout={busy_timeout_ms}")
    cursor.execute(f"PRAGMA synchronous={synchronous_mode}")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA mmap_size=268435456")  # 256MB
    cursor.close()


def create_engine() -> AsyncEngine:
    """创建 SQLite 数据库引擎

    配置 WAL 模式、busy_timeout、mmap 等性能优化 PRAGMA。
    """
    from myrm_agent_harness.utils.db.sqlite import cleanup_orphan_wal

    url = get_database_url()
    echo = settings.database.database_echo
    pool_size = settings.database.sqlite_pool_size

    # Crash recovery: drop orphaned WAL/SHM of an empty main DB before connecting.
    cleanup_orphan_wal(Path(os.path.expanduser(settings.database.sqlite_path)))

    engine = create_async_engine(
        url,
        echo=echo,
        future=True,
        connect_args={"check_same_thread": False},
        pool_size=pool_size,
        max_overflow=settings.database.sqlite_pool_max_overflow,
    )

    # Register database setting pragmas when connection is established
    event.listen(engine.sync_engine, "connect", set_sqlite_pragma)

    @event.listens_for(engine.sync_engine, "begin")
    def do_begin(conn: Connection) -> None:
        """Execute BEGIN IMMEDIATE to take the SQLite write lock eagerly.

        Lock-contention waits are governed by the ``busy_timeout`` PRAGMA and
        happen on the aiosqlite connection worker thread, so the asyncio event
        loop is never blocked. A previous implementation retried with
        ``time.sleep(jitter)`` in this sync callback, which froze the whole
        event loop during write contention and cascaded into multi-second
        health-check latency (and loadMessages fetch timeouts) under parallel
        E2E load. SQLite's built-in busy handler already applies its own
        backoff, so the manual jitter retry was redundant.
        """
        conn.exec_driver_sql("BEGIN IMMEDIATE")

    logger.info(
        "SQLite engine: WAL + mmap, pool_size=%s, busy_timeout_ms=%s",
        pool_size,
        get_sqlite_busy_timeout_ms(),
    )
    return engine


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """创建会话工厂"""
    return async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


__all__ = [
    "get_database_url",
    "get_sqlite_busy_timeout_ms",
    "create_engine",
    "create_session_factory",
    "set_sqlite_pragma",
]
