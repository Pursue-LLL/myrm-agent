"""数据库工厂

创建 SQLite 数据库引擎和会话工厂。
所有部署模式统一使用 SQLite (aiosqlite)，配置 WAL、synchronous=FULL、异步连接池、PRAGMA busy_timeout 等。
Sandbox 模式下 SQLite 文件存储在沙箱持久化卷上。
"""

import logging
import os
import re
import sqlite3
from dataclasses import dataclass
from pathlib import Path

from sqlalchemy import event
from sqlalchemy.engine import Connection
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import settings
from app.config.system_status import system_status

logger = logging.getLogger(__name__)

# Statements that mutate the database (DML + DDL). A deferred ``BEGIN`` only
# escalates to a write transaction implicitly; these prefixes let us take the
# write lock eagerly via ``BEGIN IMMEDIATE`` instead of relying on the
# implicit upgrade, which SQLite aborts with SQLITE_BUSY_SNAPSHOT (not covered
# by busy_timeout) whenever a concurrent writer committed meanwhile.
_IMPLICIT_WRITE_RE = re.compile(
    r"^\s*(?:INSERT|UPDATE|DELETE|REPLACE|UPSERT|MERGE|"
    r"CREATE|ALTER|DROP|VACUUM|REINDEX|ATTACH|DETACH)",
    re.IGNORECASE,
)

_TRANSACTION_CTL_WORDS = (
    "BEGIN",
    "COMMIT",
    "END",
    "ROLLBACK",
    "ABORT",
    "SAVEPOINT",
    "RELEASE",
)

_TRANSACTION_STATE_KEY = "myrm_transaction_state"


@dataclass(slots=True)
class _TransactionState:
    """Bookkeeping of the transaction currently open on a pooled connection."""

    write_locked: bool = False  # BEGIN IMMEDIATE was issued: the write lock is held
    read_seen: bool = False  # a statement already read: the deferred snapshot must be kept


def _transaction_state(conn: Connection) -> _TransactionState | None:
    """The open transaction's state, or ``None`` when the engine doesn't run the policy."""
    state = conn.info.get(_TRANSACTION_STATE_KEY)
    return state if isinstance(state, _TransactionState) else None


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
    if not is_degraded:
        cursor.execute("PRAGMA wal_autocheckpoint=1000")
    cursor.execute("PRAGMA cache_size=-64000")  # 64MB
    cursor.execute("PRAGMA temp_store=MEMORY")
    cursor.execute("PRAGMA mmap_size=268435456")  # 256MB
    cursor.close()


def register_sqlite_transaction_events(engine: AsyncEngine) -> None:
    """Wire the deferred-read / immediate-write transaction policy onto ``engine``.

    Start transactions with a plain ``BEGIN`` (WAL snapshot reads never touch
    the write lock) and escalate only genuine writers to ``BEGIN IMMEDIATE``.
    See ``do_begin`` / ``_escalate_write_transaction`` for the rationale.
    """

    @event.listens_for(engine.sync_engine, "begin")
    def do_begin(conn: Connection) -> None:
        """Start transactions deferred; only genuine writers escalate to IMMEDIATE.

        A blanket ``BEGIN IMMEDIATE`` makes every read transaction also grab the
        SQLite write lock, serializing *all* database access. Under parallel E2E
        load this produced ``database is locked`` storms on read-only endpoints
        (GET /messages, Get chat details, Get nav badges, ...), which left the
        frontend on a skeleton and, ultimately, killed the backend. Starting
        deferred keeps WAL snapshot reads completely lock-free; the first write
        statement escalates via ``_escalate_write_transaction`` where lock waits
        are governed by the busy_timeout PRAGMA on the aiosqlite worker thread
        (the event loop is never blocked).
        """
        conn.exec_driver_sql("BEGIN")
        conn.info[_TRANSACTION_STATE_KEY] = _TransactionState()

    @event.listens_for(engine.sync_engine, "before_cursor_execute")
    def _escalate_write_transaction(
        conn: Connection,
        _cursor: object,
        statement: str,
        _parameters: object,
        _context: object,
        _executemany: bool,
    ) -> None:
        state = _transaction_state(conn)
        if state is None or state.write_locked or not conn.in_transaction():
            return
        if _IMPLICIT_WRITE_RE.match(statement):
            # Read-then-write transaction: keep the deferred snapshot so the
            # values already read stay consistent with the upcoming writes.
            # If a concurrent writer committed in between, SQLite aborts the
            # upgrade with SQLITE_BUSY_SNAPSHOT and the registered busy
            # handlers surface a retryable 503 instead of losing the update.
            # Flows that must not lose their write call ``acquire_write_lock``.
            if not state.read_seen:
                _take_write_lock(conn)
        else:
            first_word = statement.lstrip().split(None, 1)[0].upper()
            if first_word not in _TRANSACTION_CTL_WORDS:
                state.read_seen = True


def _take_write_lock(conn: Connection) -> None:
    """Re-enter the still-untouched transaction as ``BEGIN IMMEDIATE``."""
    state = _transaction_state(conn)
    if state is None or state.write_locked:
        return
    if state.read_seen:
        raise RuntimeError("The write lock must be taken before the transaction's first read")
    state.write_locked = True  # set first: the statements below must not re-enter this path
    # A deferred BEGIN is lazy: nothing has touched the database yet, so
    # committing it is a harmless no-op that lets us re-enter with
    # BEGIN IMMEDIATE and take the write lock under busy_timeout.
    conn.exec_driver_sql("COMMIT")
    conn.exec_driver_sql("BEGIN IMMEDIATE")


async def acquire_write_lock(session: AsyncSession) -> None:
    """Take the SQLite write lock before ``session`` reads anything.

    A transaction that reads first keeps its deferred snapshot, so a writer
    committing between that read and the transaction's first write aborts it
    with SQLITE_BUSY_SNAPSHOT ("database is locked", which busy_timeout does not
    cover). A unit of work that always writes, and reads as part of doing so,
    calls this first: it then waits for the lock under busy_timeout and nothing
    can commit between its read and its write. A no-op on engines that do not
    run the transaction policy.

    Raises:
        RuntimeError: the session's transaction already executed a statement.
    """
    connection = await session.connection()
    await connection.run_sync(_take_write_lock)


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
    register_sqlite_transaction_events(engine)

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
    "register_sqlite_transaction_events",
    "acquire_write_lock",
]
