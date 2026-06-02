"""Conversation recall repository DTOs and row mappers.

[INPUT]
- sqlalchemy.engine.row::RowMapping (POS: SQLAlchemy row mapping contract)

[OUTPUT]
- ConversationRecallRow: Typed conversation recall search row.
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
from datetime import datetime
from typing import Mapping, TypeAlias

from sqlalchemy.engine import RowMapping

RecallMapping: TypeAlias = Mapping[str, object] | RowMapping


@dataclass(frozen=True, slots=True)
class ConversationRecallRow:
    chat_id: str
    title: str | None
    agent_id: str | None
    source: str
    message_id: str | None
    snippet: str
    summary: str | None
    last_message_at: datetime | None
    created_at: datetime | None
    updated_at: datetime | None
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
    created_at: datetime | None
    updated_at: datetime | None
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
    return ConversationRecallRow(
        chat_id=required_str(row, "chat_id"),
        title=optional_str(row, "title"),
        agent_id=optional_str(row, "agent_id"),
        source=required_str(row, "source"),
        message_id=optional_str(row, "message_id"),
        snippet=required_str(row, "snippet"),
        summary=optional_str(row, "summary"),
        last_message_at=optional_datetime(row, "last_message_at"),
        created_at=optional_datetime(row, "created_at"),
        updated_at=optional_datetime(row, "updated_at"),
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
        created_at=optional_datetime(row, "created_at"),
        updated_at=optional_datetime(row, "updated_at"),
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
    value = row.get(key)
    return value if isinstance(value, datetime) else None


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
