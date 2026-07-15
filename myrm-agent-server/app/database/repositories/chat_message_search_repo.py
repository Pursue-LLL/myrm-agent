"""Chat message FTS search repository.

[INPUT]
app.database.models::Message (POS: 会话与消息域模型。管理聊天会话、消息记录和对话分支)
sqlalchemy.ext.asyncio::AsyncSession (POS: async database session)

[OUTPUT]
ChatMessageSearchRepository: FTS5 search over active chat messages, and chat-id-level FTS matching for sidebar search.
MessageFtsSearchRow: Typed result row for message search.

[POS]
聊天消息全文检索仓储。封装消息级 FTS5 查询，并复用 Conversation Recall 的排除策略。
"""

from __future__ import annotations

from datetime import datetime
from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession


class MessageFtsSearchRow(TypedDict):
    id: str
    chat_id: str
    role: str
    content: str
    sent_at: datetime | str | None
    chat_title: str | None
    highlight_snippet: str | None


class ChatMessageSearchRepository:
    """Read-only FTS5 search for chat messages."""

    @staticmethod
    async def get_matching_chat_ids(db: AsyncSession, safe_query: str, *, limit: int = 200) -> list[str]:
        """Return distinct chat IDs whose messages match *safe_query* via FTS5."""
        if not safe_query:
            return []
        sql = text(
            """
            SELECT DISTINCT m.chat_id
            FROM messages_fts fts
            JOIN messages m ON m.rowid = fts.rowid
            JOIN chats c   ON c.id = m.chat_id
            WHERE messages_fts MATCH :query
              AND m.is_active = 1
              AND c.is_incognito = 0
              AND c.deleted_at IS NULL
            LIMIT :limit
            """
        )
        result = await db.execute(sql, {"query": safe_query, "limit": limit})
        return [row[0] for row in result.fetchall()]

    @staticmethod
    async def search_messages_fts(
        db: AsyncSession,
        safe_query: str,
        limit: int,
        offset: int,
        since: datetime | None,
        until: datetime | None,
    ) -> tuple[list[MessageFtsSearchRow], int]:
        time_clause = ""
        params: dict[str, object] = {"query": safe_query}
        if since is not None:
            time_clause += " AND m.sent_at >= :since"
            params["since"] = since
        if until is not None:
            time_clause += " AND m.sent_at <= :until"
            params["until"] = until

        sql = text(
            f"""
            SELECT
                m.id,
                m.chat_id,
                m.role,
                m.content,
                m.sent_at,
                c.title as chat_title,
                snippet(messages_fts, 0, '<mark>', '</mark>', '...', 40) as highlight_snippet
            FROM messages_fts fts
            JOIN messages m ON m.rowid = fts.rowid
            JOIN chats c ON c.id = m.chat_id
            LEFT JOIN conversation_recall_documents d ON d.chat_id = m.chat_id
            WHERE messages_fts MATCH :query
              AND m.is_active = 1
              AND c.is_incognito = 0
              AND COALESCE(d.is_excluded, 0) = 0
              {time_clause}
            ORDER BY fts.rank
            LIMIT :limit OFFSET :offset
        """
        )

        count_sql = text(
            f"""
            SELECT COUNT(*)
            FROM messages_fts fts
            JOIN messages m ON m.rowid = fts.rowid
            JOIN chats c ON c.id = m.chat_id
            LEFT JOIN conversation_recall_documents d ON d.chat_id = m.chat_id
            WHERE messages_fts MATCH :query
              AND m.is_active = 1
              AND c.is_incognito = 0
              AND COALESCE(d.is_excluded, 0) = 0
              {time_clause}
        """
        )

        count_result = await db.execute(count_sql, params)
        total = int(count_result.scalar() or 0)
        if total == 0:
            return [], 0

        result = await db.execute(sql, {**params, "limit": limit, "offset": offset})
        rows = result.fetchall()
        messages: list[MessageFtsSearchRow] = []
        for row in rows:
            messages.append(
                {
                    "id": row.id,
                    "chat_id": row.chat_id,
                    "role": row.role,
                    "content": row.content,
                    "sent_at": row.sent_at,
                    "chat_title": row.chat_title,
                    "highlight_snippet": row.highlight_snippet,
                }
            )
        return messages, total
