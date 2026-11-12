"""Procedural-rule operations of SQLiteRelationalStore.

[INPUT]
- relational._converters::PROCEDURAL_COLUMNS, now_iso, row_to_procedural (POS: column list, timestamp and row-to-model converters)
- relational._store_host::SQLiteStoreHost (POS: typed contract of the connection, error and scope helpers)
- relational.exceptions::RelationalNotFoundError, RelationalQueryError (POS: missing rule, query failure)
- toolkits.memory.types::ProceduralMemory (POS: Memory type definitions)

[OUTPUT]
- SQLiteRuleMixin: create_rule, get_rule, search_rules, list_rules, count_rules, update_rule, delete_rule

[POS]
Procedural-rule persistence of SQLiteRelationalStore; trigger keywords and extra metadata are stored as JSON columns,
the metadata one also carrying the rule's error fingerprint, resolution steps and chat links. Rules are read newest
first (``created_at DESC, id DESC``); ``create_rule`` stores the creation time the rule carries, in UTC, because the
column is ordered as text and offsets would misorder it.
"""

import json
from datetime import UTC
from uuid import uuid4

from myrm_agent_harness.toolkits.memory.relational._converters import PROCEDURAL_COLUMNS, now_iso, row_to_procedural
from myrm_agent_harness.toolkits.memory.relational._store_host import SQLiteStoreHost
from myrm_agent_harness.toolkits.memory.relational.exceptions import RelationalNotFoundError, RelationalQueryError
from myrm_agent_harness.toolkits.memory.types import ProceduralMemory


class SQLiteRuleMixin(SQLiteStoreHost):
    """Procedural-rule reads and writes of SQLiteRelationalStore."""

    @staticmethod
    def _encode_rule_metadata(rule: ProceduralMemory) -> str | None:
        meta = dict(rule.metadata) if rule.metadata else {}
        if rule.error_fingerprint and "error_fingerprint" not in meta:
            meta["error_fingerprint"] = rule.error_fingerprint
        if rule.resolution_steps and "resolution_steps" not in meta:
            meta["resolution_steps"] = json.dumps(list(rule.resolution_steps))
        if rule.source_chat_id:
            meta["source_chat_id"] = rule.source_chat_id
        if rule.source_chat_ids:
            meta["source_chat_ids"] = json.dumps(list(rule.source_chat_ids))
        return json.dumps(meta) if meta else None

    async def create_rule(self, rule: ProceduralMemory) -> ProceduralMemory:
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        rule_id = rule.id or str(uuid4())
        now = now_iso()
        # The rule keeps the creation time it carries (an approved proposal keeps the moment it was proposed), in UTC
        # so that the column's text order is its time order.
        created_at = rule.created_at.astimezone(UTC).isoformat()
        (
            primary_namespace,
            namespaces_json,
            agent_id,
            channel_id,
            conversation_id,
            task_id,
        ) = self._scope_values(rule.scope)
        try:
            await conn.execute(
                """INSERT INTO procedural_rules
                   (id, user_id, content, trigger_text, action_text, priority, is_active, trigger_keywords,
                    source, metadata, primary_namespace, namespaces, agent_id, channel_id, conversation_id,
                    task_id, tool_name, tool_rule_priority, access_count, last_accessed_at,
                    created_at, updated_at, is_user_locked, expected_valid_days)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    rule_id,
                    "default",
                    rule.content,
                    rule.trigger,
                    rule.action,
                    rule.priority,
                    int(rule.is_active),
                    json.dumps(rule.trigger_keywords),
                    rule.source.value,
                    self._encode_rule_metadata(rule),
                    primary_namespace,
                    namespaces_json,
                    agent_id,
                    channel_id,
                    conversation_id,
                    task_id,
                    rule.tool_name,
                    rule.tool_rule_priority.value,
                    rule.access_count,
                    (rule.last_accessed_at.isoformat() if rule.last_accessed_at else None),
                    created_at,
                    now,
                    int(rule.is_user_locked),
                    rule.expected_valid_days,
                ),
            )
            await conn.commit()
            rule.id = rule_id
            return rule
        except Exception as e:
            await self._handle_query_error("create_rule", e)
            return rule

    async def get_rule(self, rule_id: str, *, namespaces: list[str] | None = None) -> ProceduralMemory | None:
        conn = await self._get_connection()
        scope_sql, scope_params = self._scope_filter_sql(namespaces)
        try:
            async with conn.execute(
                f"SELECT {PROCEDURAL_COLUMNS} FROM procedural_rules WHERE id = ?{scope_sql}",
                (rule_id, *scope_params),
            ) as cursor:
                row = await cursor.fetchone()
            return row_to_procedural(tuple(row)) if row else None
        except Exception as e:
            await self._handle_query_error("get_rule", e)
            return None

    async def search_rules(
        self, query: str, *, limit: int = 10, namespaces: list[str] | None = None
    ) -> list[ProceduralMemory]:
        conn = await self._get_connection()
        pattern = f"%{query}%"
        scope_sql, scope_params = self._scope_filter_sql(namespaces)
        try:
            async with conn.execute(
                f"""SELECT {PROCEDURAL_COLUMNS} FROM procedural_rules
                   WHERE is_active = 1
                     AND (trigger_text LIKE ? OR action_text LIKE ?)
                """
                + scope_sql
                + " ORDER BY created_at DESC, id DESC LIMIT ?",
                (pattern, pattern, *scope_params, limit),
            ) as cursor:
                rows = list(await cursor.fetchall())
            return [row_to_procedural(tuple(r)) for r in rows]
        except Exception as e:
            raise RelationalQueryError(f"search_rules failed: {e}") from e

    async def list_rules(
        self,
        *,
        active_only: bool = True,
        limit: int = 1000,
        offset: int = 0,
        namespaces: list[str] | None = None,
    ) -> list[ProceduralMemory]:
        conn = await self._get_connection()
        scope_sql, scope_params = self._scope_filter_sql(namespaces)
        try:
            if active_only:
                sql = (
                    f"SELECT {PROCEDURAL_COLUMNS} FROM procedural_rules WHERE is_active = 1"
                    + scope_sql
                    + " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
                )
                params: tuple[str | int, ...] = (*scope_params, limit, offset)
            else:
                sql = (
                    f"SELECT {PROCEDURAL_COLUMNS} FROM procedural_rules WHERE 1=1"
                    + scope_sql
                    + " ORDER BY created_at DESC, id DESC LIMIT ? OFFSET ?"
                )
                params = (*scope_params, limit, offset)
            async with conn.execute(sql, params) as cursor:
                rows = list(await cursor.fetchall())
            return [row_to_procedural(tuple(r)) for r in rows]
        except Exception as e:
            raise RelationalQueryError(f"list_rules failed: {e}") from e

    async def count_rules(self, *, active_only: bool = True, namespaces: list[str] | None = None) -> int:
        conn = await self._get_connection()
        scope_sql, scope_params = self._scope_filter_sql(namespaces)
        try:
            if active_only:
                sql = f"SELECT COUNT(*) FROM procedural_rules WHERE is_active = 1{scope_sql}"
            else:
                sql = f"SELECT COUNT(*) FROM procedural_rules WHERE 1=1 {scope_sql}"

            async with conn.execute(sql, scope_params) as cursor:
                row = await cursor.fetchone()
            return row[0] if row else 0
        except Exception as e:
            raise RelationalQueryError(f"count_rules failed: {e}") from e

    async def update_rule(self, rule_id: str, rule: ProceduralMemory) -> ProceduralMemory:
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        now = now_iso()
        try:
            cursor = await conn.execute(
                """UPDATE procedural_rules
                   SET content = ?, trigger_text = ?, action_text = ?, priority = ?,
                       is_active = ?, trigger_keywords = ?, source = ?, metadata = ?,
                       primary_namespace = ?, namespaces = ?, agent_id = ?, channel_id = ?,
                       conversation_id = ?, task_id = ?, tool_name = ?,
                       tool_rule_priority = ?, access_count = ?, last_accessed_at = ?,
                       is_user_locked = ?, expected_valid_days = ?, updated_at = ?
                   WHERE id = ?""",
                (
                    rule.content,
                    rule.trigger,
                    rule.action,
                    rule.priority,
                    int(rule.is_active),
                    json.dumps(rule.trigger_keywords),
                    rule.source.value,
                    self._encode_rule_metadata(rule),
                    rule.scope.primary_namespace,
                    json.dumps(rule.scope.namespaces),
                    rule.scope.agent_id,
                    rule.scope.channel_id,
                    rule.scope.conversation_id,
                    rule.scope.task_id,
                    rule.tool_name,
                    rule.tool_rule_priority.value,
                    rule.access_count,
                    (rule.last_accessed_at.isoformat() if rule.last_accessed_at else None),
                    int(rule.is_user_locked),
                    rule.expected_valid_days,
                    now,
                    rule_id,
                ),
            )
            await conn.commit()
            if cursor.rowcount == 0:
                raise RelationalNotFoundError(f"Rule {rule_id} not found")
            rule.id = rule_id
            return rule
        except RelationalNotFoundError:
            raise
        except Exception as e:
            await self._handle_query_error("update_rule", e)
            return rule

    async def delete_rule(self, rule_id: str) -> bool:
        await self._ensure_integrity_before_write()
        conn = await self._get_connection()
        try:
            cursor = await conn.execute("DELETE FROM procedural_rules WHERE id = ?", (rule_id,))
            await conn.commit()
            return cursor.rowcount > 0
        except Exception as e:
            await self._handle_query_error("delete_rule", e)
            return False
