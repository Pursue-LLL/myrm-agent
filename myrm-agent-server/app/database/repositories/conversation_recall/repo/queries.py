"""[INPUT]
- app.database.repositories.conversation_recall.sql / .types (POS: SQL + row types)

[OUTPUT]
- QueriesMixin

[POS]
ConversationRecallRepository mixin: context, lineage, recent rows and health probing.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall.sql import (
    filter_sql,
)
from app.database.repositories.conversation_recall.types import (
    ConversationRecallContext,
    ConversationRecallHealth,
    ConversationRecallRow,
    int_value,
    optional_datetime,
    optional_str,
    recall_row,
    required_str,
)


class QueriesMixin:
    @staticmethod
    async def get_context(db: AsyncSession, chat_id: str) -> ConversationRecallContext | None:
        row = (
            (
                await db.execute(
                    text("""
                    SELECT c.id AS chat_id, c.agent_id AS agent_id, c.source AS source
                    FROM chats c
                    WHERE c.id = :chat_id
                    LIMIT 1
                """),
                    {"chat_id": chat_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return ConversationRecallContext(
            chat_id=required_str(row, "chat_id"),
            agent_id=optional_str(row, "agent_id"),
            source=optional_str(row, "source"),
        )

    @staticmethod
    async def get_lineage_chat_ids(db: AsyncSession, chat_id: str, lineage: str) -> list[str]:
        if lineage == "all":
            return []
        rows = (
            await db.execute(
                text("""
                    WITH RECURSIVE
                    ancestors(chat_id) AS (
                        SELECT parent_chat_id
                        FROM conversation_forks
                        WHERE child_chat_id = :chat_id
                        UNION
                        SELECT f.parent_chat_id
                        FROM conversation_forks f
                        JOIN ancestors a ON f.child_chat_id = a.chat_id
                    ),
                    descendants(chat_id) AS (
                        SELECT child_chat_id
                        FROM conversation_forks
                        WHERE parent_chat_id = :chat_id
                        UNION
                        SELECT f.child_chat_id
                        FROM conversation_forks f
                        JOIN descendants d ON f.parent_chat_id = d.chat_id
                    )
                    SELECT chat_id FROM ancestors WHERE :lineage IN ('ancestors', 'related')
                    UNION
                    SELECT chat_id FROM descendants WHERE :lineage IN ('descendants', 'related')
                """),
                {"chat_id": chat_id, "lineage": lineage},
            )
        ).fetchall()
        return [str(row[0]) for row in rows if row[0]]

    @staticmethod
    async def recent(
        db: AsyncSession,
        *,
        limit: int,
        current_chat_id: str | None,
        agent_id: str | None,
        current_source: str | None,
        scope: str,
        lineage_chat_ids: list[str],
        since: datetime | None,
        until: datetime | None,
    ) -> list[ConversationRecallRow]:
        filters, params = filter_sql(
            current_chat_id=current_chat_id,
            agent_id=agent_id,
            current_source=current_source,
            scope=scope,
            lineage_chat_ids=lineage_chat_ids,
            since=since,
            until=until,
        )
        params["limit"] = limit
        rows = (
            (
                await db.execute(
                    text(f"""
                    SELECT
                        d.chat_id AS chat_id,
                        d.title AS title,
                        d.agent_id AS agent_id,
                        d.source AS source,
                        d.last_message_id AS message_id,
                        d.snippet AS snippet,
                        d.summary AS summary,
                        d.last_message_at AS last_message_at,
                        d.created_at AS created_at,
                        d.updated_at AS updated_at,
                        0.0 AS rank,
                        f.parent_chat_id AS fork_parent_id
                    FROM conversation_recall_documents d
                    LEFT JOIN conversation_forks f ON f.child_chat_id = d.chat_id
                    WHERE d.is_excluded = 0
                      {filters}
                    ORDER BY d.last_message_at DESC, d.updated_at DESC
                    LIMIT :limit
                """),
                    params,
                )
            )
            .mappings()
            .all()
        )
        return [recall_row(row) for row in rows]

    @staticmethod
    async def health(db: AsyncSession) -> ConversationRecallHealth:
        row = (
            (
                await db.execute(
                    text("""
                    SELECT
                        COUNT(*) AS indexed_conversations,
                        SUM(CASE WHEN is_excluded = 1 THEN 1 ELSE 0 END) AS excluded_conversations,
                        MAX(updated_at) AS last_indexed_at
                    FROM conversation_recall_documents
                """)
                )
            )
            .mappings()
            .one()
        )
        missing = (
            await db.execute(
                text("""
                    SELECT COUNT(*)
                    FROM chats c
                    LEFT JOIN conversation_recall_documents d ON d.chat_id = c.id
                    WHERE d.chat_id IS NULL
                """)
            )
        ).scalar_one()
        segment_count = (await db.execute(text("SELECT COUNT(*) FROM conversation_recall_segments"))).scalar_one()
        missing_segments = (
            await db.execute(
                text("""
                    SELECT COUNT(*)
                    FROM messages m
                    LEFT JOIN conversation_recall_segments s
                      ON s.chat_id = m.chat_id
                     AND s.message_id = m.id
                     AND s.segment_ordinal = 0
                    WHERE m.is_active = 1
                      AND s.message_id IS NULL
                """)
            )
        ).scalar_one()
        fts_ready = (
            await db.execute(
                text("""
                    SELECT COUNT(*)
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'conversation_recall_fts'
                """)
            )
        ).scalar_one()
        segments_fts_ready = (
            await db.execute(
                text("""
                    SELECT COUNT(*)
                    FROM sqlite_master
                    WHERE type = 'table' AND name = 'conversation_recall_segments_fts'
                """)
            )
        ).scalar_one()

        fts_intact = bool(fts_ready)
        segments_fts_intact = bool(segments_fts_ready)
        if fts_intact:
            try:
                await db.execute(text("INSERT INTO conversation_recall_fts(conversation_recall_fts) VALUES('integrity-check')"))
            except Exception:
                fts_intact = False
        if segments_fts_intact:
            try:
                await db.execute(
                    text(
                        "INSERT INTO conversation_recall_segments_fts(conversation_recall_segments_fts) VALUES('integrity-check')"
                    )
                )
            except Exception:
                segments_fts_intact = False

        return ConversationRecallHealth(
            indexed_conversations=int_value(row, "indexed_conversations"),
            indexed_segments=int(segment_count or 0),
            excluded_conversations=int_value(row, "excluded_conversations"),
            missing_conversations=int(missing or 0),
            missing_segments=int(missing_segments or 0),
            fts_ready=fts_intact,
            segments_fts_ready=segments_fts_intact,
            last_indexed_at=optional_datetime(row, "last_indexed_at"),
        )
