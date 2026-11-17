"""Conversation Recall visibility lookup repository.

[INPUT]
- app.database.repositories.conversation_recall.sql::filter_sql, visible_document_sql (POS: Conversation Recall SQL 契约层)
- sqlalchemy.ext.asyncio::AsyncSession (POS: async database session)

[OUTPUT]
ConversationRecallLookupRepository: Read-only prior-chat document lookup, visibility-checked message window queries,
    and lookup of the stored text a search snippet was cut from, which a chat the model may not read does not give.
WindowContext: Stored text around a snippet window, with the offset where the window starts in it.

[POS]
Conversation Recall 可见性查找仓储。为 Server 召回服务按统一 scope/exclusion 策略补齐可核验证据。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall.sql import filter_sql, visible_document_sql


@dataclass(frozen=True, slots=True)
class PriorChatDocumentRow:
    """Recall document fields needed for prior_chat mention injection."""

    title: str
    summary: str
    snippet: str
    is_excluded: bool


@dataclass(frozen=True, slots=True)
class ExpandedSegmentRow:
    """One message row in an expanded conversation window."""

    message_id: str
    role: str
    segment_text: str


@dataclass(frozen=True, slots=True)
class WindowContext:
    """Stored text around a snippet window, with the offset where the window starts in it."""

    text: str
    offset: int


# The stored texts an FTS5 snippet is cut from, in the order they are tried: the message itself, then the chat
# transcript (a window can span messages), then the latest message the chat is listed by. A window inside the
# title or the summary is found in memory by the caller. Identifiers are constants, never caller input.
_WINDOW_SOURCES = (
    ("conversation_recall_segments", "segment_text", "chat_id = :chat_id AND message_id = :message_id"),
    ("conversation_recall_documents", "searchable_text", "chat_id = :chat_id"),
    ("conversation_recall_documents", "snippet", "chat_id = :chat_id"),
)
# Scope and agent filters were applied by the search that ranked the hit. Whether the chat is excluded or incognito is
# state a user can flip after that, so visibility is checked again here, for every source alike.
_WINDOW_CONTEXT_SQL = """
    SELECT substr({column}, MAX(1, instr({column}, :window) - :radius), :span) AS context,
           instr({column}, :window) - MAX(1, instr({column}, :window) - :radius) AS window_offset
    FROM {table}
    WHERE {scope}
      AND EXISTS (SELECT 1 FROM conversation_recall_documents v WHERE v.chat_id = {table}.chat_id AND {visible})
      AND instr({column}, :window) > 0
    LIMIT 1
"""
_VISIBLE_DOCUMENT = visible_document_sql("v")


class ConversationRecallLookupRepository:
    """Read-only helpers for visible recall documents and source snippets."""

    @staticmethod
    async def fetch_prior_chat_document(
        db: AsyncSession,
        *,
        chat_id: str,
    ) -> PriorChatDocumentRow | None:
        row = (
            (
                await db.execute(
                    text(
                        """
                        SELECT title, summary, snippet, is_excluded
                        FROM conversation_recall_documents
                        WHERE chat_id = :chat_id
                        LIMIT 1
                    """
                    ),
                    {"chat_id": chat_id},
                )
            )
            .mappings()
            .first()
        )
        if row is None:
            return None
        return PriorChatDocumentRow(
            title=str(row["title"] or ""),
            summary=str(row["summary"] or ""),
            snippet=str(row["snippet"] or ""),
            is_excluded=int(row.get("is_excluded") or 0) == 1,
        )

    @staticmethod
    async def fetch_message_window(
        db: AsyncSession,
        *,
        chat_id: str,
        message_id: str,
        window: int,
        current_chat_id: str | None,
        agent_id: str | None,
        scope: str,
    ) -> list[ExpandedSegmentRow]:
        filters, filter_params = filter_sql(
            current_chat_id=current_chat_id,
            agent_id=agent_id,
            current_source=None,
            scope=scope,
            lineage_chat_ids=[],
            since=None,
            until=None,
        )
        window = max(1, min(window, 20))
        rows = (
            (
                await db.execute(
                    text(
                        f"""
                    WITH anchor AS (
                        SELECT sent_at
                        FROM conversation_recall_segments
                        WHERE chat_id = :chat_id AND message_id = :message_id
                        LIMIT 1
                    ),
                    visible AS (
                        SELECT d.chat_id AS chat_id
                        FROM conversation_recall_documents d
                        WHERE d.chat_id = :chat_id
                          AND {filters}
                    ),
                    before_rows AS (
                        SELECT s.message_id, s.role, s.segment_text, s.sent_at
                        FROM conversation_recall_segments s
                        JOIN visible v ON v.chat_id = s.chat_id
                        JOIN anchor a ON 1 = 1
                        WHERE s.chat_id = :chat_id
                          AND s.sent_at <= a.sent_at
                        ORDER BY s.sent_at DESC
                        LIMIT :before_limit
                    ),
                    after_rows AS (
                        SELECT s.message_id, s.role, s.segment_text, s.sent_at
                        FROM conversation_recall_segments s
                        JOIN visible v ON v.chat_id = s.chat_id
                        JOIN anchor a ON 1 = 1
                        WHERE s.chat_id = :chat_id
                          AND s.sent_at > a.sent_at
                        ORDER BY s.sent_at ASC
                        LIMIT :after_limit
                    )
                    SELECT message_id, role, segment_text, sent_at FROM before_rows
                    UNION ALL
                    SELECT message_id, role, segment_text, sent_at FROM after_rows
                    ORDER BY sent_at ASC
                """
                    ),
                    {
                        "chat_id": chat_id,
                        "message_id": message_id,
                        "before_limit": window + 1,
                        "after_limit": window,
                        **filter_params,
                    },
                )
            )
            .mappings()
            .all()
        )
        return [
            ExpandedSegmentRow(
                message_id=str(row["message_id"]),
                role=str(row["role"]),
                segment_text=str(row["segment_text"] or ""),
            )
            for row in rows
        ]

    @staticmethod
    async def fetch_window_context(
        db: AsyncSession,
        *,
        chat_id: str,
        message_id: str | None,
        window: str,
        radius: int,
    ) -> WindowContext | None:
        """The stored text holding ``window`` verbatim, or None if none does or the model may not read the chat.

        The text starts ``radius`` chars before the window (at the start of the stored text if that comes first) and runs
        for the window's length plus ``2 * radius`` chars. The substring search and the cut both run in SQLite, so a long
        transcript never leaves the database whole.
        """
        # Without a message id there is no segment to look in.
        sources = _WINDOW_SOURCES if message_id is not None else _WINDOW_SOURCES[1:]
        params: dict[str, str | int | None] = {
            "chat_id": chat_id,
            "message_id": message_id,
            "window": window,
            "radius": radius,
            "span": len(window) + 2 * radius,
        }
        for table, column, scope in sources:
            statement = text(_WINDOW_CONTEXT_SQL.format(table=table, column=column, scope=scope, visible=_VISIBLE_DOCUMENT))
            row = (await db.execute(statement, params)).mappings().first()
            if row is not None:
                return WindowContext(text=str(row["context"]), offset=int(row["window_offset"]))
        return None
