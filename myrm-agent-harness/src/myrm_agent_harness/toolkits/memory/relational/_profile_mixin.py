"""Profile operations of SQLiteRelationalStore.

[INPUT]
- relational._converters::now_iso, parse_dt, row_to_profile (POS: timestamp and row-to-model converters)
- relational._store_host::SQLiteStoreHost (POS: typed contract of the connection, error and scope helpers)
- relational.exceptions::RelationalQueryError (POS: query failure)
- toolkits.memory.types::MemoryScope, ProfileAttributeSnapshot, ProfileEntry (POS: Memory type definitions)

[OUTPUT]
- SQLiteProfileMixin: get_profile, get_profile_snapshot, set_profile, delete_profile, list_profiles, count_profiles,
  delete_profiles_by_source_chat_id, count_profiles_by_source_chat_id

[POS]
Profile key-value persistence of SQLiteRelationalStore, scoped by namespace. Listings and counts skip the
maintenance code's ``_system.`` bookkeeping rows. ``get_profile_snapshot`` returns the value together with a
revision hash of its key, value and update time. A row may name the chat it was written from (``source_chat_id``);
every write replaces that link, so a value written without one is never taken away with a chat.
"""

import hashlib
from uuid import uuid4

from myrm_agent_harness.toolkits.memory.relational._converters import now_iso, parse_dt, row_to_profile
from myrm_agent_harness.toolkits.memory.relational._store_host import SQLiteStoreHost
from myrm_agent_harness.toolkits.memory.relational.exceptions import RelationalQueryError
from myrm_agent_harness.toolkits.memory.types import MemoryScope, ProfileAttributeSnapshot, ProfileEntry


class SQLiteProfileMixin(SQLiteStoreHost):
    """Profile reads and writes of SQLiteRelationalStore."""

    async def get_profile(self, key: str, *, namespaces: list[str] | None = None) -> str | None:
        conn = await self._get_connection()
        scope_sql, scope_params = self._scope_filter_sql(namespaces)
        try:
            async with conn.execute(
                f"SELECT value FROM profiles WHERE key = ?{scope_sql} ORDER BY updated_at DESC LIMIT 1",
                (key, *scope_params),
            ) as cursor:
                row = await cursor.fetchone()
            return row[0] if row else None
        except Exception as e:
            raise RelationalQueryError(f"get_profile failed: {e}") from e

    async def get_profile_snapshot(self, key: str, *, namespaces: list[str] | None = None) -> ProfileAttributeSnapshot:
        conn = await self._get_connection()
        scope_sql, scope_params = self._scope_filter_sql(namespaces)
        try:
            async with conn.execute(
                f"""SELECT key, value, updated_at
                    FROM profiles
                    WHERE key = ?{scope_sql}
                    ORDER BY updated_at DESC
                    LIMIT 1""",
                (key, *scope_params),
            ) as cursor:
                row = await cursor.fetchone()
            if row is None:
                return ProfileAttributeSnapshot(key=key, exists=False, revision=f"missing:{key}")
            value = str(row[1])
            updated_at = parse_dt(str(row[2]))
            revision = _profile_revision(str(row[0]), value, updated_at.isoformat())
            return ProfileAttributeSnapshot(
                key=str(row[0]),
                value=value,
                exists=True,
                revision=revision,
                updated_at=updated_at,
            )
        except Exception as e:
            raise RelationalQueryError(f"get_profile_snapshot failed: {e}") from e

    async def set_profile(
        self, key: str, value: str, *, scope: MemoryScope | None = None, source_chat_id: str | None = None
    ) -> None:
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        now = now_iso()
        (
            primary_namespace,
            namespaces_json,
            agent_id,
            channel_id,
            conversation_id,
            task_id,
        ) = self._scope_values(scope)
        try:
            # The chat link is replaced on every write: a value is linked only to the chat that wrote it last.
            await conn.execute(
                """INSERT INTO profiles (
                       id, user_id, key, value, primary_namespace, namespaces, agent_id,
                       channel_id, conversation_id, task_id, source_chat_id, created_at, updated_at
                   )
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                   ON CONFLICT(user_id, key, primary_namespace) DO UPDATE SET
                       value = excluded.value,
                       namespaces = excluded.namespaces,
                       agent_id = excluded.agent_id,
                       channel_id = excluded.channel_id,
                       conversation_id = excluded.conversation_id,
                       task_id = excluded.task_id,
                       source_chat_id = excluded.source_chat_id,
                       updated_at = excluded.updated_at""",
                (
                    str(uuid4()),
                    "default",
                    key,
                    value,
                    primary_namespace,
                    namespaces_json,
                    agent_id,
                    channel_id,
                    conversation_id,
                    task_id,
                    source_chat_id,
                    now,
                    now,
                ),
            )
            await conn.commit()
        except Exception as e:
            await self._handle_query_error("set_profile", e)

    async def delete_profiles_by_source_chat_id(self, source_chat_id: str) -> int:
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        try:
            cursor = await conn.execute("DELETE FROM profiles WHERE source_chat_id = ?", (source_chat_id,))
            await conn.commit()
            return cursor.rowcount or 0
        except Exception as e:
            await self._handle_query_error("delete_profiles_by_source_chat_id", e)
            return 0

    async def count_profiles_by_source_chat_id(self, source_chat_id: str) -> int:
        conn = await self._get_connection()
        try:
            async with conn.execute(
                "SELECT COUNT(*) FROM profiles WHERE source_chat_id = ?", (source_chat_id,)
            ) as cursor:
                row = await cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            raise RelationalQueryError(f"count_profiles_by_source_chat_id failed: {e}") from e

    async def delete_profile(self, key: str, *, namespaces: list[str] | None = None) -> bool:
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        scope_sql, scope_params = self._scope_filter_sql(namespaces)
        try:
            cursor = await conn.execute(
                f"DELETE FROM profiles WHERE (key = ? OR id = ?){scope_sql}",
                (key, key, *scope_params),
            )
            await conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            await self._handle_query_error("delete_profile", e)
            return False

    async def list_profiles(
        self, *, limit: int = 1000, offset: int = 0, namespaces: list[str] | None = None
    ) -> list[ProfileEntry]:
        conn = await self._get_connection()
        scope_sql, scope_params = self._scope_filter_sql(namespaces)
        try:
            # Keys under "_system." are the maintenance code's own bookkeeping, never user data.
            async with conn.execute(
                """SELECT id, user_id, key, value, primary_namespace, namespaces, agent_id,
                          channel_id, conversation_id, task_id, created_at, updated_at
                   FROM profiles
                   WHERE 1=1
                     AND substr(key, 1, 8) != '_system.'"""
                + scope_sql
                + " ORDER BY updated_at DESC LIMIT ? OFFSET ?",
                (*scope_params, limit, offset),
            ) as cursor:
                rows = list(await cursor.fetchall())
            return [row_to_profile(tuple(r)) for r in rows]
        except Exception as e:
            raise RelationalQueryError(f"list_profiles failed: {e}") from e

    async def count_profiles(self, *, namespaces: list[str] | None = None) -> int:
        conn = await self._get_connection()
        scope_sql, scope_params = self._scope_filter_sql(namespaces)
        try:
            # Keys under "_system." are the maintenance code's own bookkeeping, never user data.
            async with conn.execute(
                f"SELECT COUNT(*) FROM profiles WHERE 1=1 AND substr(key, 1, 8) != '_system.' {scope_sql}",
                scope_params,
            ) as cursor:
                row = await cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            raise RelationalQueryError(f"count_profiles failed: {e}") from e


def _profile_revision(key: str, value: str, updated_at: str) -> str:
    payload = "\x00".join((key, value, updated_at))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()
