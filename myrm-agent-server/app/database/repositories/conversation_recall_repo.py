"""Conversation recall index repository.

[INPUT]
- app.database.models.chat::Chat, Message, ConversationFork (POS: 会话与消息域模型。管理聊天会话、消息记录和对话分支)
- app.database.repositories.conversation_recall_sql (POS: Conversation Recall SQL 契约层)
- app.database.repositories.conversation_recall_types (POS: Conversation Recall 类型转换层)
- sqlalchemy.ext.asyncio::AsyncSession (POS: async database session)

[OUTPUT]
- CONVERSATION_RECALL_SCHEMA_SQL: Conversation Recall schema statements.
- CONVERSATION_RECALL_BOOTSTRAP_SQL: Conversation Recall bootstrap statement.
- CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL: Conversation Recall segment bootstrap statement.
- ConversationRecallRepository: Read/write repository for conversation recall documents and message segments.

[POS]
Conversation Recall 索引仓储。维护会话摘要文档与消息段 SQLite/FTS5 索引，为 Server 业务层提供低延迟历史会话召回。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall_sql import (
    CONVERSATION_RECALL_BOOTSTRAP_SQL,
    CONVERSATION_RECALL_SCHEMA_SQL,
    CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL,
    DELETE_SEGMENTS_FOR_CHAT_SQL,
    UPSERT_REBUILD_SQL,
    UPSERT_SEGMENT_SQL,
    UPSERT_SEGMENTS_FOR_CHAT_SQL,
    filter_sql,
)
from app.database.repositories.conversation_recall_types import (
    ConversationRecallContext,
    ConversationRecallDocumentRow,
    ConversationRecallHealth,
    ConversationRecallRow,
    int_value,
    optional_datetime,
    optional_str,
    recall_document_row,
    recall_row,
    required_str,
)

__all__ = [
    "CONVERSATION_RECALL_BOOTSTRAP_SQL",
    "CONVERSATION_RECALL_SCHEMA_SQL",
    "CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL",
    "ConversationRecallContext",
    "ConversationRecallDocumentRow",
    "ConversationRecallHealth",
    "ConversationRecallRepository",
    "ConversationRecallRow",
]


class ConversationRecallRepository:
    """Read/write repository for the conversation recall index."""

    @staticmethod
    async def bootstrap_missing(db: AsyncSession) -> None:
        await db.execute(text(CONVERSATION_RECALL_BOOTSTRAP_SQL))
        await db.execute(text(CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL))

    @staticmethod
    async def rebuild_chat(db: AsyncSession, chat_id: str) -> None:
        await db.execute(text(UPSERT_REBUILD_SQL), {"chat_id": chat_id})
        await db.execute(text(DELETE_SEGMENTS_FOR_CHAT_SQL), {"chat_id": chat_id})
        await db.execute(text(UPSERT_SEGMENTS_FOR_CHAT_SQL), {"chat_id": chat_id})

    @staticmethod
    async def append_message(
        db: AsyncSession,
        *,
        chat_id: str,
        message_id: str,
        role: str,
        content: str,
        sent_at: datetime,
    ) -> None:
        line = f"{role}: {content}"
        await db.execute(
            text("""
                INSERT INTO conversation_recall_documents (
                    chat_id,
                    agent_id,
                    source,
                    title,
                    summary,
                    snippet,
                    searchable_text,
                    last_message_id,
                    last_message_at,
                    created_at,
                    updated_at
                )
                SELECT
                    c.id,
                    c.agent_id,
                    c.source,
                    c.title,
                    c.compacted_summary,
                    :snippet,
                    :line,
                    :message_id,
                    :sent_at,
                    c.created_at,
                    CURRENT_TIMESTAMP
                FROM chats c
                WHERE c.id = :chat_id
                ON CONFLICT(chat_id) DO UPDATE SET
                    agent_id = excluded.agent_id,
                    source = excluded.source,
                    title = excluded.title,
                    summary = excluded.summary,
                    snippet = excluded.snippet,
                    searchable_text = CASE
                        WHEN conversation_recall_documents.searchable_text = '' THEN excluded.searchable_text
                        ELSE conversation_recall_documents.searchable_text || char(10) || excluded.searchable_text
                    END,
                    last_message_id = excluded.last_message_id,
                    last_message_at = excluded.last_message_at,
                    updated_at = CURRENT_TIMESTAMP
            """),
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "snippet": content,
                "line": line,
                "sent_at": sent_at,
            },
        )
        await db.execute(
            text(UPSERT_SEGMENT_SQL),
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "role": role,
                "content": content,
                "sent_at": sent_at,
            },
        )

    @staticmethod
    async def set_excluded(db: AsyncSession, chat_id: str, excluded: bool) -> bool:
        await ConversationRecallRepository.rebuild_chat(db, chat_id)
        await db.execute(
            text("""
                UPDATE conversation_recall_documents
                SET is_excluded = :is_excluded,
                    updated_at = CURRENT_TIMESTAMP
                WHERE chat_id = :chat_id
            """),
            {"chat_id": chat_id, "is_excluded": 1 if excluded else 0},
        )
        changes = await db.scalar(text("SELECT changes()"))
        return int(changes or 0) > 0

    @staticmethod
    async def delete_chat(db: AsyncSession, chat_id: str) -> None:
        await db.execute(
            text("DELETE FROM conversation_recall_segments WHERE chat_id = :chat_id"),
            {"chat_id": chat_id},
        )
        await db.execute(
            text("DELETE FROM conversation_recall_documents WHERE chat_id = :chat_id"),
            {"chat_id": chat_id},
        )

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
    async def search(
        db: AsyncSession,
        *,
        safe_query: str,
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
        params.update({"query": safe_query, "limit": limit})
        segment_rows = (
            (
                await db.execute(
                    text(f"""
                    SELECT
                        d.chat_id AS chat_id,
                        d.title AS title,
                        d.agent_id AS agent_id,
                        d.source AS source,
                        s.message_id AS message_id,
                        snippet(conversation_recall_segments_fts, 0, '<mark>', '</mark>', '...', 56) AS snippet,
                        d.summary AS summary,
                        s.sent_at AS last_message_at,
                        d.created_at AS created_at,
                        d.updated_at AS updated_at,
                        conversation_recall_segments_fts.rank AS rank,
                        f.parent_chat_id AS fork_parent_id
                    FROM conversation_recall_segments_fts
                    JOIN conversation_recall_segments s ON s.id = conversation_recall_segments_fts.rowid
                    JOIN conversation_recall_documents d ON d.chat_id = s.chat_id
                    LEFT JOIN conversation_forks f ON f.child_chat_id = d.chat_id
                    WHERE conversation_recall_segments_fts MATCH :query
                      AND d.is_excluded = 0
                      {filters}
                    ORDER BY conversation_recall_segments_fts.rank ASC, s.sent_at DESC, d.last_message_at DESC
                    LIMIT :limit
                """),
                    params,
                )
            )
            .mappings()
            .all()
        )
        document_rows = (
            (
                await db.execute(
                    text(f"""
                    SELECT
                        d.chat_id AS chat_id,
                        d.title AS title,
                        d.agent_id AS agent_id,
                        d.source AS source,
                        d.last_message_id AS message_id,
                        snippet(conversation_recall_fts, -1, '<mark>', '</mark>', '...', 56) AS snippet,
                        d.summary AS summary,
                        d.last_message_at AS last_message_at,
                        d.created_at AS created_at,
                        d.updated_at AS updated_at,
                        conversation_recall_fts.rank AS rank,
                        f.parent_chat_id AS fork_parent_id
                    FROM conversation_recall_fts
                    JOIN conversation_recall_documents d ON d.id = conversation_recall_fts.rowid
                    LEFT JOIN conversation_forks f ON f.child_chat_id = d.chat_id
                    WHERE conversation_recall_fts MATCH :query
                      AND d.is_excluded = 0
                      {filters}
                    ORDER BY conversation_recall_fts.rank ASC, d.last_message_at DESC, d.updated_at DESC
                    LIMIT :limit
                """),
                    params,
                )
            )
            .mappings()
            .all()
        )
        return _dedupe_recall_rows(
            [recall_row(row) for row in [*segment_rows, *document_rows]],
            limit=limit,
        )

    @staticmethod
    async def list_documents(
        db: AsyncSession,
        *,
        excluded: bool | None,
        limit: int,
        offset: int,
    ) -> tuple[list[ConversationRecallDocumentRow], int]:
        filters = ""
        params: dict[str, object] = {"limit": limit, "offset": offset}
        if excluded is not None:
            filters = "WHERE is_excluded = :is_excluded"
            params["is_excluded"] = 1 if excluded else 0

        total = (
            await db.execute(
                text(f"""
                    SELECT COUNT(*)
                    FROM conversation_recall_documents
                    {filters}
                """),
                params,
            )
        ).scalar_one()
        rows = (
            (
                await db.execute(
                    text(f"""
                    SELECT
                        chat_id,
                        title,
                        agent_id,
                        source,
                        snippet,
                        summary,
                        last_message_at,
                        created_at,
                        updated_at,
                        is_excluded
                    FROM conversation_recall_documents
                    {filters}
                    ORDER BY is_excluded DESC, last_message_at DESC, updated_at DESC
                    LIMIT :limit OFFSET :offset
                """),
                    params,
                )
            )
            .mappings()
            .all()
        )
        return [recall_document_row(row) for row in rows], int(total or 0)

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
        return ConversationRecallHealth(
            indexed_conversations=int_value(row, "indexed_conversations"),
            indexed_segments=int(segment_count or 0),
            excluded_conversations=int_value(row, "excluded_conversations"),
            missing_conversations=int(missing or 0),
            missing_segments=int(missing_segments or 0),
            fts_ready=bool(fts_ready),
            segments_fts_ready=bool(segments_fts_ready),
            last_indexed_at=optional_datetime(row, "last_indexed_at"),
        )


def _dedupe_recall_rows(rows: list[ConversationRecallRow], *, limit: int) -> list[ConversationRecallRow]:
    ordered = sorted(rows, key=lambda row: (row.rank, -_datetime_sort_value(row.last_message_at)))
    deduped: list[ConversationRecallRow] = []
    seen_chat_ids: set[str] = set()
    for row in ordered:
        if row.chat_id in seen_chat_ids:
            continue
        seen_chat_ids.add(row.chat_id)
        deduped.append(row)
        if len(deduped) >= limit:
            break
    return deduped


def _datetime_sort_value(value: datetime | None) -> float:
    if value is None:
        return 0.0
    return value.timestamp()
