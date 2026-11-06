"""SQLite Relational Store — zero-dependency relational backend using aiosqlite.


[INPUT]
myrm_agent_harness.toolkits.memory.relational._exact_fact_store (POS: Exact fact storage and FTS5 inverted search)
myrm_agent_harness.toolkits.memory.relational._pending_mixin (POS: Pending-record operations)
myrm_agent_harness.toolkits.memory.relational._profile_mixin (POS: Profile operations)
myrm_agent_harness.toolkits.memory.relational._rule_mixin (POS: Procedural-rule operations)
myrm_agent_harness.toolkits.memory.relational._schema (POS: Table DDL, scope migration and indexes)
myrm_agent_harness.toolkits.memory.relational.base (POS: Relational store abstraction layer)
myrm_agent_harness.toolkits.memory.relational.exceptions
myrm_agent_harness.toolkits.memory.types (POS: Memory type definitions)

[OUTPUT]
SQLiteRelationalStore: Async SQLite relational store with WAL mode,
                       connection reuse, and JSON column support.

[POS]
Lightweight relational store backed by aiosqlite. WAL mode + connection reuse for
high-performance async I/O. Owns the connection, integrity checks, exact-fact search and
lifecycle; Profile, Procedural, and Pending CRUD come from the operation mixins.
"""

import asyncio
import json
import logging
from datetime import datetime
from pathlib import Path

import aiosqlite

from myrm_agent_harness.toolkits.memory.relational._exact_fact_store import (
    delete_exact_fact,
    save_exact_fact,
    search_exact_facts,
)
from myrm_agent_harness.toolkits.memory.relational._pending_mixin import SQLitePendingMixin
from myrm_agent_harness.toolkits.memory.relational._profile_mixin import SQLiteProfileMixin
from myrm_agent_harness.toolkits.memory.relational._rule_mixin import SQLiteRuleMixin
from myrm_agent_harness.toolkits.memory.relational._schema import init_relational_schema
from myrm_agent_harness.toolkits.memory.relational.base import RelationalStore
from myrm_agent_harness.toolkits.memory.relational.exceptions import (
    CorruptedMemoryIndexError,
    RelationalConnectionError,
    RelationalQueryError,
    RelationalStoreError,
)
from myrm_agent_harness.toolkits.memory.types import MemoryScope, MemorySearchResult

logger = logging.getLogger(__name__)


class SQLiteRelationalStore(SQLiteProfileMixin, SQLiteRuleMixin, SQLitePendingMixin, RelationalStore):
    """SQLite relational store with WAL mode and connection reuse.

    Features:
    - Async I/O via aiosqlite
    - WAL mode for concurrent reads
    - Connection reuse with double-checked locking
    - JSON column support for metadata/keywords
    - Composite index optimization

    Example::

        async with SQLiteRelationalStore("~/.app/relational.db") as store:
            await store.set_profile("u1", "language", "zh")
            lang = await store.get_profile("u1", "language")
    """

    def __init__(self, db_path: str) -> None:
        self._db_path = Path(db_path).expanduser().resolve()
        self._db_path.parent.mkdir(parents=True, exist_ok=True)
        self._connection: aiosqlite.Connection | None = None
        self._connection_lock = asyncio.Lock()
        self._initialized = False
        self._closed = False
        self._fts5_supported = False
        logger.info("SQLiteRelationalStore initialized: %s", self._db_path)

    async def _get_connection(self) -> aiosqlite.Connection:
        if self._closed:
            raise RelationalConnectionError("Store has been closed")
        if self._connection is None:
            async with self._connection_lock:
                if self._closed:
                    raise RelationalConnectionError("Store has been closed")
                if self._connection is None:
                    try:
                        from myrm_agent_harness.utils.db.sqlite import (
                            prepare_database_file,
                        )

                        prepare_database_file(self._db_path)
                        self._connection = await aiosqlite.connect(str(self._db_path))
                        await self._init_connection_settings()
                        await self._init_tables()
                        # Fast quick_check on connection establishment
                        async with self._connection.execute("PRAGMA quick_check(1)") as cursor:
                            rows = list(await cursor.fetchall())
                        if not rows or len(rows) != 1 or str(rows[0][0]).lower() != "ok":
                            await self._connection.close()
                            self._connection = None
                            raise CorruptedMemoryIndexError(
                                f"SQLite store {self._db_path} failed initial quick_check: {rows}",
                                db_path=str(self._db_path),
                                index_type="sqlite_relational",
                                repair_suggestion="Restore from sqlite_backup snapshot or reset memory store.",
                            )
                    except CorruptedMemoryIndexError:
                        self._connection = None
                        raise
                    except Exception as e:
                        err_str = str(e).lower()
                        if any(k in err_str for k in ("malformed", "corrupt", "not a database", "disk i/o error")):
                            self._connection = None
                            raise CorruptedMemoryIndexError(
                                f"Corrupted SQLite store {self._db_path}: {e}",
                                db_path=str(self._db_path),
                                index_type="sqlite_relational",
                                repair_suggestion="Restore from sqlite_backup snapshot or reset memory store.",
                            ) from e
                        raise RelationalConnectionError(f"Failed to connect: {e}") from e
        return self._connection

    async def _init_connection_settings(self) -> None:
        if self._connection is None:
            return
        from myrm_agent_harness.utils.db.sqlite import DURABLE, harden_connection_async

        await harden_connection_async(self._connection, DURABLE, db_path=self._db_path)
        await self._connection.commit()

    async def _quick_check_rows(self) -> list[tuple[object, ...]]:
        """Run ``PRAGMA quick_check(1)``, confirming any failure on a fresh connection.

        A long-lived connection caches each FTS5 table's structure, so while another
        connection (a second manager in this process, or another process) commits
        to the same file, the cached structure goes stale and quick_check reports
        ``malformed inverted index`` for a healthy database. A fresh connection reads
        the current snapshot, so only a failure it reproduces counts as corruption.
        """
        conn = await self._get_connection()
        async with conn.execute("PRAGMA quick_check(1)") as cursor:
            rows = [tuple(row) for row in await cursor.fetchall()]
        if self._quick_check_ok(rows):
            return rows
        async with aiosqlite.connect(str(self._db_path)) as fresh, fresh.execute("PRAGMA quick_check(1)") as cursor:
            confirmed = [tuple(row) for row in await cursor.fetchall()]
        if self._quick_check_ok(confirmed):
            logger.info("quick_check on the long-lived connection was stale; fresh connection reports ok: %s", rows)
        return confirmed

    @staticmethod
    def _quick_check_ok(rows: list[tuple[object, ...]]) -> bool:
        return len(rows) == 1 and str(rows[0][0]).lower() == "ok"

    async def assert_store_integrity(self) -> None:
        """Fast pre-command integrity check using PRAGMA quick_check(1).

        Fails fast if the SQLite database is corrupted, preventing partial/corrupt writes.
        """
        try:
            rows = await self._quick_check_rows()
            if not rows or len(rows) != 1 or str(rows[0][0]).lower() != "ok":
                raise CorruptedMemoryIndexError(
                    f"SQLite store {self._db_path} failed quick_check: {rows}",
                    db_path=str(self._db_path),
                    index_type="sqlite_relational",
                    repair_suggestion="Restore from sqlite_backup snapshot or reset memory store.",
                )
        except CorruptedMemoryIndexError:
            raise
        except Exception as e:
            err_str = str(e).lower()
            if any(k in err_str for k in ("malformed", "corrupt", "not a database", "disk i/o")):
                raise CorruptedMemoryIndexError(
                    f"SQLite store {self._db_path} integrity check query error: {e}",
                    db_path=str(self._db_path),
                    index_type="sqlite_relational",
                    repair_suggestion="Check file permissions or restore database from backup.",
                ) from e
            raise RelationalQueryError(f"SQLite store {self._db_path} integrity check query failed: {e}") from e

    def _handle_query_error(self, op: str, e: Exception) -> None:
        if isinstance(e, (CorruptedMemoryIndexError, RelationalStoreError)):
            raise e
        err_str = str(e).lower()
        if any(k in err_str for k in ("malformed", "corrupt", "not a database", "disk i/o")):
            self._connection = None
            raise CorruptedMemoryIndexError(
                f"SQLite store {self._db_path} corrupted during {op}: {e}",
                db_path=str(self._db_path),
                index_type="sqlite_relational",
                repair_suggestion="Restore from sqlite_backup snapshot or reset memory store.",
            ) from e
        raise RelationalQueryError(f"{op} failed: {e}") from e

    async def _ensure_integrity_before_write(self) -> None:
        """Fail fast before write operations if database is corrupted."""
        await self.assert_store_integrity()

    def _scope_values(
        self, scope: MemoryScope | None
    ) -> tuple[str, str, str | None, str | None, str | None, str | None]:
        if scope is None:
            return "", "[]", None, None, None, None
        return (
            scope.primary_namespace,
            json.dumps(scope.namespaces),
            scope.agent_id,
            scope.channel_id,
            scope.conversation_id,
            scope.task_id,
        )

    def _scope_filter_sql(self, namespaces: list[str] | None) -> tuple[str, list[str]]:
        if not namespaces:
            return "", []
        placeholders = ",".join("?" for _ in namespaces)
        return f" AND primary_namespace IN ({placeholders})", list(namespaces)

    async def _init_tables(self) -> None:
        if self._initialized or self._connection is None:
            return
        try:
            self._fts5_supported = await init_relational_schema(self._connection)
            self._initialized = True
        except Exception as e:
            raise RelationalConnectionError(f"Failed to initialize tables: {e}") from e

    # ── Reset ────────────────────────────────────────────────────────

    async def delete_all(self) -> int:
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        try:
            c1 = await conn.execute("DELETE FROM profiles", ())
            c2 = await conn.execute("DELETE FROM procedural_rules", ())
            c3 = await conn.execute("DELETE FROM pending_records", ())
            await conn.commit()
            return (c1.rowcount or 0) + (c2.rowcount or 0) + (c3.rowcount or 0)
        except Exception as e:
            self._handle_query_error("delete_all", e)
            return 0

    # ── Diagnostics & Integrity ──────────────────────────────────────

    async def check_integrity(self) -> tuple[bool, str]:
        """Check the physical and index integrity of the relational SQLite database."""
        if self._closed:
            return False, "Store has been closed"
        try:
            rows = await self._quick_check_rows()
            if self._quick_check_ok(rows):
                return True, "ok"
            err_msg = "; ".join(str(r[0]) for r in rows)
            return False, f"Integrity check failed: {err_msg}"
        except Exception as e:
            return False, f"Integrity check query error: {e}"

    # ── Exact Fact & FTS5 ───────────────────────────────────────────

    async def record_exact_fact(
        self,
        *,
        memory_id: str,
        user_id: str,
        content: str,
        identifiers: list[str],
        primary_namespace: str = "",
        namespaces: list[str] | None = None,
    ) -> None:
        """Persist exact fact identifiers and synchronize FTS5 inverted index."""
        conn = await self._get_connection()
        await self._ensure_integrity_before_write()
        try:
            await save_exact_fact(
                conn,
                memory_id=memory_id,
                user_id=user_id,
                content=content,
                identifiers=identifiers,
                primary_namespace=primary_namespace,
                namespaces=namespaces,
                fts5_supported=self._fts5_supported,
            )
            await conn.commit()
        except Exception as e:
            self._handle_query_error("record_exact_fact", e)

    async def search_fts5(
        self,
        query: str,
        limit: int = 10,
        since: datetime | None = None,
        until: datetime | None = None,
        *,
        namespaces: list[str] | None = None,
    ) -> list[MemorySearchResult]:
        """Perform exact identifier match and FTS5 inverted search.

        Conforms to FTS5SearcherFunc:
        Callable[[str, int, datetime | None, datetime | None], Awaitable[list[MemorySearchResult]]].
        """
        conn = await self._get_connection()
        try:
            return await search_exact_facts(
                conn,
                query=query,
                limit=limit,
                since=since,
                until=until,
                namespaces=namespaces,
                fts5_supported=self._fts5_supported,
            )
        except Exception as e:
            self._handle_query_error("search_fts5", e)
            return []

    async def delete_exact_fact(self, memory_id: str) -> None:
        """Remove exact fact records and FTS5 virtual table document."""
        conn = await self._get_connection()
        await self._ensure_integrity_before_write()
        try:
            await delete_exact_fact(
                conn,
                memory_id=memory_id,
                fts5_supported=self._fts5_supported,
            )
            await conn.commit()
        except Exception as e:
            self._handle_query_error("delete_exact_fact", e)

    # ── Lifecycle ────────────────────────────────────────────────────

    async def close(self) -> None:
        self._closed = True
        if self._connection is not None:
            from myrm_agent_harness.utils.db.sqlite import checkpoint_truncate_async

            await checkpoint_truncate_async(self._connection)
            await self._connection.close()
            self._connection = None
            logger.info("SQLiteRelationalStore closed")
