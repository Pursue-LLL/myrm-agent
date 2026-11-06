"""[INPUT]
- app.database.repositories.conversation_recall.sql / .types (POS: SQL + row types)

[OUTPUT]
- WritesMixin

[POS]
ConversationRecallRepository mixin: rebuild, message/segment append, exclusion and delete.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.repositories.conversation_recall.sql import (
    CONVERSATION_RECALL_BOOTSTRAP_SQL,
    CONVERSATION_RECALL_SEGMENT_BOOTSTRAP_SQL,
    DELETE_SEGMENTS_FOR_CHAT_SQL,
    UPSERT_REBUILD_SQL,
    UPSERT_SEGMENT_SQL,
    UPSERT_SEGMENTS_FOR_CHAT_SQL,
)


class WritesMixin:
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
    async def append_salient_tool_segment(
        db: AsyncSession,
        *,
        chat_id: str,
        message_id: str,
        tool_name: str,
        command: str,
        exit_code: int | None,
        snippet: str,
        sent_at: datetime,
    ) -> None:
        """Persist salient verbatim tool execution evidence into recall index before compaction."""
        # The header must stay on one line: readers locate `exit=N` on the first line of the segment.
        single_line_command = " ".join(command.split())
        cmd_part = f" cmd={single_line_command}" if single_line_command else ""
        exit_part = f" exit={exit_code}" if exit_code is not None else ""
        header = f"Tool[{tool_name}]{cmd_part}{exit_part}"
        segment_text = f"{header}\n{snippet}"
        line = f"tool: {segment_text}"

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
                    searchable_text = CASE
                        WHEN conversation_recall_documents.searchable_text = '' THEN excluded.searchable_text
                        ELSE conversation_recall_documents.searchable_text || char(10) || excluded.searchable_text
                    END,
                    updated_at = CURRENT_TIMESTAMP
            """),
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "snippet": snippet[:200],
                "line": line,
                "sent_at": sent_at,
            },
        )
        await db.execute(
            text(UPSERT_SEGMENT_SQL),
            {
                "chat_id": chat_id,
                "message_id": message_id,
                "role": "tool",
                "content": segment_text,
                "sent_at": sent_at,
            },
        )

    @staticmethod
    async def set_excluded(db: AsyncSession, chat_id: str, excluded: bool) -> bool:
        await WritesMixin.rebuild_chat(db, chat_id)
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
