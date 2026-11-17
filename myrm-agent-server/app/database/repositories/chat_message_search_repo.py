"""Chat message FTS search repository.

[INPUT]
app.database.models::Message (POS: 会话与消息域模型。管理聊天会话、消息记录和对话分支)
app.database.repositories.like_pattern::typed_needle, like_contains_pattern (POS: 聊天检索的子串通道：键入查询的 needle 与 LIKE 模式)
sqlalchemy.ext.asyncio::AsyncSession (POS: async database session)

[OUTPUT]
ChatMessageSearchRepository: FTS5 search over active chat messages, chat-id-level FTS matching for sidebar search,
    and the preview window of a message the substring fallback found.
MessageFtsSearchRow: Typed result row for message search.

[POS]
聊天消息全文检索仓储。封装消息级 FTS5 查询，并复用 Conversation Recall 的排除策略；FTS 无命中时按键入文本（raw_query）做子串回退，
回退命中的预览是以匹配为中心、匹配处高亮的窗口，宽度与标记同 FTS5 `snippet()`。
"""

from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import TypedDict

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.like_pattern import LIKE_ESCAPE_CLAUSE, like_contains_pattern, typed_needle

logger = logging.getLogger(__name__)

# FTS5 ``snippet()`` counts trigram tokens, and N overlapping trigrams span N + 2 characters. The substring fallback cuts a
# window of the same width with the same markers and ellipsis; where the window starts is its own rule (``substring_snippet``).
_MARK_OPEN = "<mark>"
_MARK_CLOSE = "</mark>"
_ELLIPSIS = "..."
_SNIPPET_TOKENS = 40
_SNIPPET_CHARS = _SNIPPET_TOKENS + 2


class MessageFtsSearchRow(TypedDict):
    id: str
    chat_id: str
    role: str
    content: str
    sent_at: datetime | str | None
    chat_title: str | None
    highlight_snippet: str | None
    is_relaxed: bool


class ChatMessageSearchRepository:
    """Read-only chat message search: FTS5, with a substring scan when the trigram index has nothing."""

    @staticmethod
    def substring_snippet(content: str, needle: str) -> str:
        """The preview of ``content`` for a message the substring fallback found: a window as wide as FTS5 ``snippet()`` cuts.

        The window is centred on the first ``needle`` (pinned to the start or the end of the text when the match is near
        it) with every ``needle`` in it marked, and ``...`` shows where the text goes on. FTS5 chooses its window by its own
        rules, so one message can preview from a different start: FTS5 begins at the head of the text for a match that
        starts within the first 40 characters, just after a ``". "`` that keeps the match in view, and wherever its scoring
        prefers when several matches share a window (for a single match the two starts are up to about 20 characters
        apart). It also marks adjacent or overlapping matches as one span. ``LIKE`` folds ASCII case and ``re`` folds
        Unicode case, so every row the fallback selects has a match to centre on; a ``needle`` that has none still
        previews the head of the text, unmarked.
        """
        pattern = re.compile(re.escape(needle), re.IGNORECASE)
        match = pattern.search(content)
        if match is None:
            start, end = 0, min(len(content), _SNIPPET_CHARS)
        else:
            span = match.end() - match.start()
            width = max(_SNIPPET_CHARS, span)
            start = min(max(0, match.start() - (width - span) // 2), max(0, len(content) - width))
            end = min(len(content), start + width)
        window = pattern.sub(lambda hit: f"{_MARK_OPEN}{hit.group()}{_MARK_CLOSE}", content[start:end])
        return f"{_ELLIPSIS if start > 0 else ''}{window}{_ELLIPSIS if end < len(content) else ''}"

    @staticmethod
    async def get_matching_chat_ids(db: AsyncSession, safe_query: str, *, raw_query: str, limit: int = 200) -> list[str]:
        """Distinct chat ids whose messages match ``safe_query`` via FTS5, else contain the text typed in ``raw_query``.

        The substring fallback answers what the trigram index cannot (a query under three characters, or one the FTS
        expression flattens), so it reads the typed text and not the FTS expression.
        """
        if not safe_query:
            return []

        # 1. First attempt via FTS5 virtual table
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
        try:
            result = await db.execute(sql, {"query": safe_query, "limit": limit})
            chat_ids = [row[0] for row in result.fetchall()]
            if chat_ids:
                return chat_ids
        except Exception as exc:
            logger.warning("FTS5 chat-id match failed; falling back to the substring scan: %s", exc)

        # 2. Short-word / CJK fallback when trigram FTS yields 0 hits (e.g. query < 3 characters)
        pattern = like_contains_pattern(raw_query)
        if pattern is None:
            return []
        fallback_sql = text(
            f"""
            SELECT DISTINCT m.chat_id
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            WHERE m.content LIKE :pattern {LIKE_ESCAPE_CLAUSE}
              AND m.is_active = 1
              AND c.is_incognito = 0
              AND c.deleted_at IS NULL
            LIMIT :limit
            """
        )
        fallback_result = await db.execute(fallback_sql, {"pattern": pattern, "limit": limit})
        return [row[0] for row in fallback_result.fetchall()]

    @staticmethod
    async def search_messages_fts(
        db: AsyncSession,
        safe_query: str,
        limit: int,
        offset: int,
        since: datetime | None,
        until: datetime | None,
        *,
        raw_query: str,
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
                snippet(messages_fts, 0, '{_MARK_OPEN}', '{_MARK_CLOSE}', '{_ELLIPSIS}', {_SNIPPET_TOKENS}) as highlight_snippet
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
        if total > 0:
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
                        "is_relaxed": False,
                    }
                )
            return messages, total

        # The trigram index has nothing: a query under three characters, or one the FTS expression flattened.
        needle = typed_needle(raw_query)
        if needle is None:
            return [], 0
        fb_time_clause = ""
        # The needle is already trimmed and unquoted, so its pattern always exists.
        fb_params: dict[str, object] = {"pattern": like_contains_pattern(needle)}
        if since is not None:
            fb_time_clause += " AND m.sent_at >= :since"
            fb_params["since"] = since
        if until is not None:
            fb_time_clause += " AND m.sent_at <= :until"
            fb_params["until"] = until

        fb_count_sql = text(
            f"""
            SELECT COUNT(*)
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            LEFT JOIN conversation_recall_documents d ON d.chat_id = m.chat_id
            WHERE m.content LIKE :pattern {LIKE_ESCAPE_CLAUSE}
              AND m.is_active = 1
              AND c.is_incognito = 0
              AND COALESCE(d.is_excluded, 0) = 0
              {fb_time_clause}
            """
        )
        fb_count_result = await db.execute(fb_count_sql, fb_params)
        fb_total = int(fb_count_result.scalar() or 0)
        if fb_total == 0:
            return [], 0

        fb_sql = text(
            f"""
            SELECT
                m.id,
                m.chat_id,
                m.role,
                m.content,
                m.sent_at,
                c.title as chat_title
            FROM messages m
            JOIN chats c ON c.id = m.chat_id
            LEFT JOIN conversation_recall_documents d ON d.chat_id = m.chat_id
            WHERE m.content LIKE :pattern {LIKE_ESCAPE_CLAUSE}
              AND m.is_active = 1
              AND c.is_incognito = 0
              AND COALESCE(d.is_excluded, 0) = 0
              {fb_time_clause}
            ORDER BY m.sent_at DESC
            LIMIT :limit OFFSET :offset
            """
        )
        fb_result = await db.execute(fb_sql, {**fb_params, "limit": limit, "offset": offset})
        fb_rows = fb_result.fetchall()
        fb_messages: list[MessageFtsSearchRow] = []
        for row in fb_rows:
            fb_messages.append(
                {
                    "id": row.id,
                    "chat_id": row.chat_id,
                    "role": row.role,
                    "content": row.content,
                    "sent_at": row.sent_at,
                    "chat_title": row.chat_title,
                    "highlight_snippet": ChatMessageSearchRepository.substring_snippet(row.content, needle),
                    "is_relaxed": True,
                }
            )
        return fb_messages, fb_total
