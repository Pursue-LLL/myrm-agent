"""Conversation Recall visibility lookup repository.

[INPUT]
- app.database.repositories.conversation_recall.sql::filter_sql (POS: Conversation Recall SQL 契约层)
- sqlalchemy.ext.asyncio::AsyncSession (POS: async database session)

[OUTPUT]
ConversationRecallLookupRepository: Read-only prior-chat document lookup and visibility-checked message window queries.

[POS]
Conversation Recall 可见性查找仓储。为 Server 召回服务按统一 scope/exclusion 策略补齐可核验证据。
"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall.sql import filter_sql


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
                          AND d.is_excluded = 0
                          {filters}
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
