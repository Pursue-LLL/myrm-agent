"""Chat message loading and backup helpers for compaction.

[INPUT]
- app.database.models::Chat, Message (POS: ORM load + incremental anchor)
- myrm_agent_harness...summary_parser::parse_structured_summary_json (POS: full-field summary deserialization across DB boundary)

[OUTPUT]
- load_chat / load_compactable_messages: incremental compactable slice
- db_messages_to_langchain / parse_existing_summary: summarize inputs
- backup_context: workspace JSONL backup before persist

[POS]
Message IO for ``compact_chat``; incremental ``compacted_before_id`` anchor aware.
"""

from __future__ import annotations

import json
import logging
from datetime import datetime, timezone
from typing import TYPE_CHECKING

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.database.models import Chat, Message

if TYPE_CHECKING:
    from langchain_core.messages import BaseMessage

logger = logging.getLogger(__name__)


async def load_chat(db: AsyncSession, chat_id: str) -> Chat | None:
    result = await db.execute(select(Chat).where(Chat.id == chat_id))
    return result.scalar_one_or_none()


async def load_compactable_messages(db: AsyncSession, chat: Chat) -> list[Message]:
    """Load messages that should be included in compaction (incremental-aware)."""
    query = select(Message).where(Message.chat_id == chat.id)
    if chat.compacted_before_id:
        anchor = await db.execute(
            select(Message.created_at).where(Message.id == chat.compacted_before_id)
        )
        anchor_ts = anchor.scalar_one_or_none()
        if anchor_ts:
            query = query.where(Message.created_at > anchor_ts)
    result = await db.execute(query.order_by(Message.created_at.asc()))
    return list(result.scalars().all())


def db_messages_to_langchain(messages: list[Message]) -> list[BaseMessage]:
    """Convert DB Message records to LangChain message objects."""
    from langchain_core.messages import AIMessage, HumanMessage

    lc_messages: list[BaseMessage] = []
    for msg in messages:
        if msg.role == "user":
            lc_messages.append(HumanMessage(content=msg.content or ""))
        elif msg.role == "assistant":
            lc_messages.append(AIMessage(content=msg.content or ""))
    return lc_messages


def parse_existing_summary(summary_json: str) -> StructuredSummary | None:
    """Parse JSON summary into StructuredSummary object.

    Delegates to the harness shared parser (``parse_structured_summary_json``)
    so all 14 ``StructuredSummary`` fields survive the DB persistence boundary —
    a hand-written partial mapping here would silently drop 9 fields on every
    incremental compaction. Returns None on unparseable input so callers fall
    back to full-mode summarisation.
    """
    from myrm_agent_harness.agent.context_management.strategies.summary.summary_parser import (
        parse_structured_summary_json,
    )

    return parse_structured_summary_json(summary_json)


async def backup_context(chat: Chat, messages: list[Message]) -> str | None:
    """Backup full context to workspace filesystem before compaction."""
    try:
        from app.platform_utils import get_storage_provider

        storage = get_storage_provider()

        timestamp = datetime.now(timezone.utc).strftime("%Y%m%d_%H%M%S")
        backup_path = f".myrm/chat_backups/{chat.id}/{timestamp}.jsonl"

        lines: list[str] = []
        if chat.compacted_summary:
            lines.append(
                json.dumps(
                    {"type": "previous_summary", "content": chat.compacted_summary}
                )
            )
        for msg in messages:
            lines.append(
                json.dumps(
                    {
                        "id": msg.id,
                        "role": msg.role,
                        "content": msg.content,
                        "created_at": (
                            msg.created_at.isoformat() if msg.created_at else None
                        ),
                    }
                )
            )

        content = "\n".join(lines)
        await storage.write(backup_path, content.encode())
        return backup_path
    except Exception as exc:
        logger.warning("Context backup failed for chat %s: %s", chat.id, exc)
        return None
