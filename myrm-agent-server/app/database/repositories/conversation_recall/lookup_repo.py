"""Conversation Recall visibility lookup repository.

[INPUT]
- app.database.repositories.conversation_recall.sql::filter_sql (POS: Conversation Recall SQL 契约层)
- app.database.repositories.conversation_recall.types::ConversationRecallRow (POS: Conversation Recall 类型转换层)
- sqlalchemy.ext.asyncio::AsyncSession (POS: async database session)

[OUTPUT]
ConversationRecallLookupRepository: Read-only visibility and source hydration queries for recall hits.

[POS]
Conversation Recall 可见性查找仓储。为 Server 召回服务按统一 scope/exclusion/lineage 策略补齐可核验证据。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall.sql import filter_sql
from app.database.repositories.conversation_recall.types import ConversationRecallRow, recall_row


class ConversationRecallLookupRepository:
    """Read-only helpers for visible recall documents and source snippets."""

    @staticmethod
    async def hydrate_visible_rows(
        db: AsyncSession,
        *,
        chat_message_ids: dict[str, str | None],
        current_chat_id: str | None,
        agent_id: str | None,
        current_source: str | None,
        scope: str,
        lineage_chat_ids: list[str],
        since: datetime | None,
        until: datetime | None,
    ) -> dict[str, ConversationRecallRow]:
        if not chat_message_ids:
            return {}

        target_sql, target_params = _target_table_sql(chat_message_ids)
        filters, filter_params = filter_sql(
            current_chat_id=current_chat_id,
            agent_id=agent_id,
            current_source=current_source,
            scope=scope,
            lineage_chat_ids=lineage_chat_ids,
            since=since,
            until=until,
        )
        rows = (
            (
                await db.execute(
                    text(f"""
                    WITH target(chat_id, source_message_id) AS (
                        {target_sql}
                    )
                    SELECT
                        d.chat_id AS chat_id,
                        d.title AS title,
                        d.agent_id AS agent_id,
                        d.source AS source,
                        COALESCE(s.message_id, d.last_message_id) AS message_id,
                        COALESCE(s.segment_text, d.snippet, '') AS snippet,
                        d.summary AS summary,
                        d.last_message_at AS last_message_at,
                        d.created_at AS created_at,
                        d.updated_at AS updated_at,
                        0.0 AS rank,
                        f.parent_chat_id AS fork_parent_id
                    FROM target t
                    JOIN conversation_recall_documents d ON d.chat_id = t.chat_id
                    LEFT JOIN conversation_recall_segments s
                      ON s.chat_id = d.chat_id
                     AND s.message_id = t.source_message_id
                     AND s.segment_ordinal = 0
                    LEFT JOIN conversation_forks f ON f.child_chat_id = d.chat_id
                    WHERE d.is_excluded = 0
                      {filters}
                """),
                    {**target_params, **filter_params},
                )
            )
            .mappings()
            .all()
        )
        return {str(row["chat_id"]): recall_row(row) for row in rows}


def _target_table_sql(chat_message_ids: dict[str, str | None]) -> tuple[str, dict[str, object]]:
    selects: list[str] = []
    params: dict[str, object] = {}
    for index, (chat_id, message_id) in enumerate(chat_message_ids.items()):
        chat_key = f"target_chat_{index}"
        message_key = f"target_message_{index}"
        selects.append(f"SELECT :{chat_key} AS chat_id, :{message_key} AS source_message_id")
        params[chat_key] = chat_id
        params[message_key] = message_id
    return "\n                        UNION ALL\n                        ".join(selects), params
