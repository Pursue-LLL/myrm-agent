"""Pending-record (approval queue) operations of SQLiteRelationalStore.

[INPUT]
- relational._converters::now_iso, row_to_pending (POS: timestamp and row-to-model converters)
- relational._store_host::SQLiteStoreHost (POS: typed contract of the connection, error and scope helpers)
- relational.exceptions::RelationalQueryError (POS: query failure)
- toolkits.memory.types::PendingRecord (POS: Memory type definitions)

[OUTPUT]
- SQLitePendingMixin: submit_pending, get_pending, pending_exists, mark_pending, list_pending, count_pending,
  batch_mark_pending, delete_pending_by_source_chat_id, count_pending_by_source_chat_id

[POS]
Approval-queue persistence of SQLiteRelationalStore: a record stays pending until it is marked with a resolution status.
"""

import json

from myrm_agent_harness.toolkits.memory.relational._converters import now_iso, row_to_pending
from myrm_agent_harness.toolkits.memory.relational._store_host import SQLiteStoreHost
from myrm_agent_harness.toolkits.memory.relational.exceptions import RelationalQueryError
from myrm_agent_harness.toolkits.memory.types import PendingRecord


class SQLitePendingMixin(SQLiteStoreHost):
    """Approval-queue reads and writes of SQLiteRelationalStore."""

    async def submit_pending(self, record: PendingRecord) -> str:
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        now = now_iso()
        try:
            await conn.execute(
                """INSERT INTO pending_records
                   (id, user_id, memory_type, content, memory_data, source_chat_id, source_message_id, status, created_at, resolution_action, target_memory_id, target_content)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?)""",
                (
                    record.id,
                    "default",
                    record.memory_type.value,
                    record.content,
                    json.dumps(record.memory_data),
                    record.source_chat_id,
                    record.source_message_id,
                    now,
                    record.resolution_action.value,
                    record.target_memory_id,
                    record.target_content,
                ),
            )
            await conn.commit()
            return record.id
        except Exception as e:
            self._handle_query_error("submit_pending", e)
            return record.id

    async def get_pending(self, pending_id: str) -> PendingRecord | None:
        conn = await self._get_connection()
        try:
            async with conn.execute("SELECT * FROM pending_records WHERE id = ?", (pending_id,)) as cursor:
                row = await cursor.fetchone()
            return row_to_pending(tuple(row)) if row else None
        except Exception as e:
            self._handle_query_error("get_pending", e)
            return None

    async def pending_exists(self, memory_type: str, content: str) -> bool:
        conn = await self._get_connection()
        try:
            async with conn.execute(
                "SELECT 1 FROM pending_records WHERE memory_type = ? AND content = ? AND status = 'pending' LIMIT 1",
                (memory_type, content),
            ) as cursor:
                return await cursor.fetchone() is not None
        except Exception as e:
            self._handle_query_error("pending_exists", e)
            return False

    async def mark_pending(self, pending_id: str, status: str) -> None:
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        now = now_iso()
        try:
            await conn.execute(
                "UPDATE pending_records SET status = ?, resolved_at = ? WHERE id = ?",
                (status, now, pending_id),
            )
            await conn.commit()
        except Exception as e:
            self._handle_query_error("mark_pending", e)

    async def list_pending(self, *, limit: int = 50) -> list[PendingRecord]:
        conn = await self._get_connection()
        try:
            async with conn.execute(
                "SELECT * FROM pending_records WHERE status = 'pending' ORDER BY created_at DESC LIMIT ?",
                (limit,),
            ) as cursor:
                rows = list(await cursor.fetchall())
            return [row_to_pending(tuple(r)) for r in rows]
        except Exception as e:
            raise RelationalQueryError(f"list_pending failed: {e}") from e

    async def count_pending(self) -> int:
        conn = await self._get_connection()
        try:
            async with conn.execute("SELECT COUNT(*) FROM pending_records WHERE status = 'pending'", ()) as cursor:
                row = await cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            raise RelationalQueryError(f"count_pending failed: {e}") from e

    async def batch_mark_pending(self, pending_ids: list[str], status: str) -> int:
        if not pending_ids:
            return 0
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        now = now_iso()
        try:
            placeholders = ",".join("?" for _ in pending_ids)
            cursor = await conn.execute(
                f"UPDATE pending_records SET status = ?, resolved_at = ? WHERE id IN ({placeholders}) AND status = 'pending'",
                [status, now, *pending_ids],
            )
            await conn.commit()
            return cursor.rowcount or 0
        except Exception as e:
            self._handle_query_error("batch_mark_pending", e)
            return 0

    async def delete_pending_by_source_chat_id(self, source_chat_id: str) -> int:
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        try:
            cursor = await conn.execute(
                "DELETE FROM pending_records WHERE source_chat_id = ?",
                (source_chat_id,),
            )
            await conn.commit()
            return cursor.rowcount or 0
        except Exception as e:
            self._handle_query_error("delete_pending_by_source_chat_id", e)
            return 0

    async def count_pending_by_source_chat_id(self, source_chat_id: str) -> int:
        conn = await self._get_connection()
        try:
            async with conn.execute(
                "SELECT COUNT(*) FROM pending_records WHERE source_chat_id = ?",
                (source_chat_id,),
            ) as cursor:
                row = await cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            raise RelationalQueryError(f"count_pending_by_source_chat_id failed: {e}") from e
