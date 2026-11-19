"""Conversation recall repository DTOs and row mappers.

[INPUT]
- sqlalchemy.engine.row::RowMapping (POS: SQLAlchemy row mapping contract)
- app.database.repositories.conversation_recall.sql::HIGHLIGHT_OPEN, HIGHLIGHT_CLOSE (POS: Conversation Recall SQL 契约层)

[OUTPUT]
- ConversationRecallRow: Typed conversation recall search row; its snippet is for display, its window for a model.
- ConversationRecallDocumentRow: Typed conversation recall management row.
- ConversationRecallContext: Current chat context for scoped recall.
- ConversationRecallHealth: Opaque health summary for the recall index.
- recall_row: Convert SQLAlchemy mappings into typed recall rows.
- recall_document_row: Convert SQLAlchemy mappings into typed management rows.

[POS]
Conversation Recall 类型转换层。集中维护索引仓储返回值 DTO 和数据库行到领域对象的安全转换。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from typing import Mapping, TypeAlias

from sqlalchemy.engine import RowMapping

from app.database.repositories.conversation_recall.sql import HIGHLIGHT_CLOSE, HIGHLIGHT_OPEN

RecallMapping: TypeAlias = Mapping[str, object] | RowMapping


@dataclass(frozen=True, slots=True)
class ConversationRecallRow:
    """One recall hit. The snippet wraps matched terms in ``<mark>`` for display; the window is the same text without them.

    ``last_message_at`` is when the message the row names (``message_id``) was sent: the message a segment matched, or
    the conversation's last message for a row about the conversation as a whole. ``created_at`` is when the chat was
    created. Each is an aware UTC instant, or None when the index holds no readable time.
    """

    chat_id: str
    title: str | None
    agent_id: str | None
    source: str
    message_id: str | None
    snippet: str
    window: str
    summary: str | None
    last_message_at: datetime | None
    created_at: datetime | None
    rank: float
    fork_parent_id: str | None


@dataclass(frozen=True, slots=True)
class ConversationRecallContext:
    chat_id: str
    agent_id: str | None
    source: str | None


@dataclass(frozen=True, slots=True)
class ConversationRecallDocumentRow:
    chat_id: str
    title: str | None
    agent_id: str | None
    source: str
    snippet: str
    summary: str | None
    last_message_at: datetime | None
    is_excluded: bool


@dataclass(frozen=True, slots=True)
class ConversationRecallHealth:
    indexed_conversations: int
    indexed_segments: int
    excluded_conversations: int
    missing_conversations: int
    missing_segments: int
    fts_ready: bool
    segments_fts_ready: bool
    last_indexed_at: datetime | None


def recall_row(row: RecallMapping) -> ConversationRecallRow:
    marked = required_str(row, "snippet")
    return ConversationRecallRow(
        chat_id=required_str(row, "chat_id"),
        title=optional_str(row, "title"),
        agent_id=optional_str(row, "agent_id"),
        source=required_str(row, "source"),
        message_id=optional_str(row, "message_id"),
        snippet=marked.replace(HIGHLIGHT_OPEN, "<mark>").replace(HIGHLIGHT_CLOSE, "</mark>"),
        window=marked.replace(HIGHLIGHT_OPEN, "").replace(HIGHLIGHT_CLOSE, ""),
        summary=optional_str(row, "summary"),
        last_message_at=optional_datetime(row, "last_message_at"),
        created_at=optional_datetime(row, "created_at"),
        rank=float_value(row, "rank"),
        fork_parent_id=optional_str(row, "fork_parent_id"),
    )


def recall_document_row(row: RecallMapping) -> ConversationRecallDocumentRow:
    return ConversationRecallDocumentRow(
        chat_id=required_str(row, "chat_id"),
        title=optional_str(row, "title"),
        agent_id=optional_str(row, "agent_id"),
        source=required_str(row, "source"),
        snippet=required_str(row, "snippet"),
        summary=optional_str(row, "summary"),
        last_message_at=optional_datetime(row, "last_message_at"),
        is_excluded=bool(int_value(row, "is_excluded")),
    )


def required_str(row: RecallMapping, key: str) -> str:
    value = row.get(key)
    return "" if value is None else str(value)


def optional_str(row: RecallMapping, key: str) -> str | None:
    value = row.get(key)
    if value is None:
        return None
    text_value = str(value).strip()
    return text_value or None


def optional_datetime(row: RecallMapping, key: str) -> datetime | None:
    """Read a timestamp column as an aware UTC instant, or None when it holds no time.

    The index is read with raw SQL, so SQLite returns a timestamp as the text it stored: UTC without an offset when the
    database stamped it or a rebuild copied a message's time, with an offset when an append bound an aware datetime.
    """
    value = row.get(key)
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if not isinstance(value, datetime):
        return None
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value.astimezone(UTC)


def float_value(row: RecallMapping, key: str) -> float:
    value = row.get(key)
    if isinstance(value, int | float):
        return float(value)
    try:
        return float(str(value))
    except (TypeError, ValueError):
        return 0.0


def int_value(row: RecallMapping, key: str) -> int:
    value = row.get(key)
    if isinstance(value, int):
        return value
    try:
        return int(str(value))
    except (TypeError, ValueError):
        return 0
