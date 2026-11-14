"""Pending-record (approval queue) operations of SQLiteRelationalStore.

[INPUT]
- relational._converters::now_iso, row_to_pending (POS: timestamp and row-to-model converters)
- relational._store_host::SQLiteStoreHost (POS: typed contract of the connection, error and scope helpers)
- relational.exceptions::RelationalQueryError (POS: query failure)
- toolkits.memory.types::PendingRecord (POS: Memory type definitions)

[OUTPUT]
- SQLitePendingMixin: submit_pending, get_pending, mark_pending, list_pending, count_pending,
  batch_mark_pending, delete_pending_by_source_chat_id, count_pending_by_source_chat_id

[POS]
Approval-queue persistence of SQLiteRelationalStore: a record stays pending until it is marked with a resolution status.
One memory type and content has at most one pending record: the queue itself refuses an identical second proposal,
whichever store on the database raised it (a resolved record does not count), and the refusal raises the waiting
record again: it moves to the front of the queue and, when its payload carries a creation time, takes the
repeated proposal's.
A record is linked to a chat when it was written from it (its ``source_chat_id`` column) or built from it among others
(the ``source_chat_ids`` of the memory it carries); a resolved record keeps the proposed text and stays linked.
"""

import json

from myrm_agent_harness.toolkits.memory.relational._converters import now_iso, row_to_pending
from myrm_agent_harness.toolkits.memory.relational._store_host import SQLiteStoreHost
from myrm_agent_harness.toolkits.memory.relational.exceptions import RelationalQueryError
from myrm_agent_harness.toolkits.memory.types import PendingRecord

_DELETE_CHUNK = 500


def _like_pattern_for_json_string(value: str) -> str:
    """LIKE pattern for ``value`` as a JSON string anywhere in a payload; a candidate filter, verified afterwards."""
    escaped = json.dumps(value).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
    return f"%{escaped}%"


def _built_from(memory_data_json: str, chat_id: str) -> bool:
    """Whether the proposed memory lists the chat among the chats it was built from."""
    try:
        chat_ids = json.loads(memory_data_json).get("source_chat_ids")
    except (ValueError, AttributeError):
        return False
    return isinstance(chat_ids, list) and chat_id in chat_ids


class SQLitePendingMixin(SQLiteStoreHost):
    """Approval-queue reads and writes of SQLiteRelationalStore."""

    async def submit_pending(self, record: PendingRecord) -> str:
        """Queue the record and return its id; ``""`` when an identical open proposal already waits.

        The conflict target is the unique index over open proposals, so only that duplicate is turned away quietly:
        any other constraint failure, a reused id included, is still an error. The proposal that waits is raised
        again by the duplicate: it moves to the front of the queue and, once approved, ranks by the later proposal's
        date, so a preference the user changed and then changed back is the newest one.
        """
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        now = now_iso()
        try:
            cursor = await conn.execute(
                """INSERT INTO pending_records
                   (id, user_id, memory_type, content, memory_data, source_chat_id, source_message_id, status, created_at, resolution_action, target_memory_id, target_content, built_from_chats)
                   VALUES (?, ?, ?, ?, ?, ?, ?, 'pending', ?, ?, ?, ?, ?)
                   ON CONFLICT (memory_type, content) WHERE status = 'pending' DO NOTHING""",
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
                    int(bool(record.memory_data.get("source_chat_ids"))),
                ),
            )
            queued = cursor.rowcount == 1
            if not queued:
                await self._raise_open_proposal(record, now)
            await conn.commit()
            return record.id if queued else ""
        except Exception as e:
            await self._handle_query_error("submit_pending", e)
            return ""

    async def _raise_open_proposal(self, record: PendingRecord, now: str) -> None:
        """Move the open proposal identical to ``record`` to the front of the queue, dated as ``record`` is."""
        conn = await self._get_connection()
        async with conn.execute(
            "SELECT id, memory_data FROM pending_records WHERE memory_type = ? AND content = ? AND status = 'pending'",
            (record.memory_type.value, record.content),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:  # resolved between the refused insert and this read
            return
        memory_data = json.loads(str(row[1])) if row[1] else {}
        proposed_at = record.memory_data.get("created_at")
        if proposed_at is not None and "created_at" in memory_data:
            memory_data["created_at"] = proposed_at
        await conn.execute(
            "UPDATE pending_records SET created_at = ?, memory_data = ? WHERE id = ?",
            (now, json.dumps(memory_data), row[0]),
        )

    async def get_pending(self, pending_id: str) -> PendingRecord | None:
        conn = await self._get_connection()
        try:
            async with conn.execute("SELECT * FROM pending_records WHERE id = ?", (pending_id,)) as cursor:
                row = await cursor.fetchone()
            return row_to_pending(tuple(row)) if row else None
        except Exception as e:
            await self._handle_query_error("get_pending", e)
            return None

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
            await self._handle_query_error("mark_pending", e)

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
            await self._handle_query_error("batch_mark_pending", e)
            return 0

    async def _pending_ids_linked_to_chat(self, chat_id: str) -> list[str]:
        """Ids of the records written from the chat or built from it among others, whatever their status.

        Only the records that list the chats they were built from are read for the second link, through a partial
        index, so the lookup does not grow with the history of resolved records.
        """
        conn = await self._get_connection()
        async with conn.execute("SELECT id FROM pending_records WHERE source_chat_id = ?", (chat_id,)) as cursor:
            written_from = [str(row[0]) for row in await cursor.fetchall()]
        async with conn.execute(
            "SELECT id, memory_data FROM pending_records WHERE built_from_chats = 1 AND memory_data LIKE ? ESCAPE '\\'",
            (_like_pattern_for_json_string(chat_id),),
        ) as cursor:
            built_from = [str(row[0]) for row in await cursor.fetchall() if _built_from(str(row[1] or ""), chat_id)]
        return list(dict.fromkeys([*written_from, *built_from]))

    async def delete_pending_by_source_chat_id(self, source_chat_id: str) -> int:
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        try:
            ids = await self._pending_ids_linked_to_chat(source_chat_id)
            deleted = 0
            for start in range(0, len(ids), _DELETE_CHUNK):
                chunk = ids[start : start + _DELETE_CHUNK]
                cursor = await conn.execute(
                    f"DELETE FROM pending_records WHERE id IN ({','.join('?' for _ in chunk)})", chunk
                )
                deleted += cursor.rowcount or 0
            await conn.commit()
            return deleted
        except Exception as e:
            await self._handle_query_error("delete_pending_by_source_chat_id", e)
            return 0

    async def count_pending_by_source_chat_id(self, source_chat_id: str) -> int:
        try:
            return len(await self._pending_ids_linked_to_chat(source_chat_id))
        except Exception as e:
            raise RelationalQueryError(f"count_pending_by_source_chat_id failed: {e}") from e
