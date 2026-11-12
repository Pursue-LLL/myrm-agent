"""Row-to-model converters for SQLiteRelationalStore.

[INPUT]
- toolkits.memory.types::MemoryScope, MemoryType, MemoryStatus, PendingRecord (POS: Memory type system foundation. Provides type-safe schema definitions for all memory types. ConversationMemory implements verbatim storage with dual-field (raw_exchange + content summary) and dual-embedding (raw + summary vectors) for lossless information preservation and adaptive retrieval optimization.)

[OUTPUT]
- now_iso: Current UTC time as an ISO 8601 string.
- parse_dt: Parse an ISO 8601 timestamp into a datetime, treating a naive value as UTC.
- row_to_profile: Convert a profile row into a ProfileEntry.
- row_to_procedural: Convert a procedural-memory row (``PROCEDURAL_COLUMNS`` order) into a ProceduralMemory.
- row_to_pending: Convert a pending-memory row into a PendingRecord.

[POS]
Row-to-model converters for SQLiteRelationalStore.
"""

from __future__ import annotations

import json
from datetime import UTC, datetime

from myrm_agent_harness.toolkits.memory.types import (
    MemoryScope,
    MemoryStatus,
    MemoryType,
    PendingRecord,
    PendingResolutionAction,
    ProceduralMemory,
    ProfileEntry,
    RuleSource,
    ToolRulePriority,
)

PROCEDURAL_COLUMNS = (
    "id, user_id, content, trigger_text, action_text, "
    "is_active, trigger_keywords, source, metadata, "
    "primary_namespace, namespaces, agent_id, channel_id, conversation_id, task_id, "
    "tool_name, tool_rule_priority, access_count, last_accessed_at, created_at, updated_at, "
    "is_user_locked, expected_valid_days"
)


def now_iso() -> str:
    return datetime.now(UTC).isoformat()


def _json_string_list(raw: object) -> list[str]:
    """A list kept in the flat rule metadata, either as a list or as the JSON text of one.

    Text that is not a JSON list is one entry itself, and anything else is empty.
    """
    if isinstance(raw, list):
        return [str(item) for item in raw]
    if isinstance(raw, str):
        try:
            parsed = json.loads(raw)
        except ValueError:
            return [raw]
        return [str(item) for item in parsed] if isinstance(parsed, list) else [raw]
    return []


def parse_dt(s: str) -> datetime:
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        return dt.replace(tzinfo=UTC)
    return dt


def row_to_profile(row: tuple[object, ...]) -> ProfileEntry:
    """Column order: id, user_id, key, value, primary_namespace, namespaces, agent_id, channel_id, conversation_id, task_id, created_at, updated_at."""
    return ProfileEntry(
        id=str(row[0]),
        user_id=str(row[1]),
        key=str(row[2]),
        value=str(row[3]),
        scope=MemoryScope(
            primary_namespace=str(row[4] or ""),
            namespaces=json.loads(row[5]) if row[5] else [],
            agent_id=str(row[6]) if row[6] else None,
            channel_id=str(row[7]) if row[7] else None,
            conversation_id=str(row[8]) if row[8] else None,
            task_id=str(row[9]) if row[9] else None,
        ),
        created_at=parse_dt(str(row[10])),
        updated_at=parse_dt(str(row[11])),
    )


def row_to_procedural(row: tuple[object, ...]) -> ProceduralMemory:
    """Column order: id, user_id, content, trigger_text, action_text,
    is_active, trigger_keywords, source, metadata, primary_namespace,
    namespaces, agent_id, channel_id, conversation_id, task_id,
    tool_name, tool_rule_priority, access_count, last_accessed_at,
    created_at, updated_at, is_user_locked, expected_valid_days.
    """
    keywords = json.loads(str(row[6])) if row[6] else []
    metadata = json.loads(str(row[8])) if row[8] else {}
    active = bool(row[5])

    tool_name_val = str(row[15]) if row[15] else None
    try:
        tool_priority = ToolRulePriority(row[16]) if row[16] else ToolRulePriority.NORMAL
    except ValueError:
        tool_priority = ToolRulePriority.NORMAL

    is_locked = bool(row[21]) if len(row) > 21 and row[21] else False
    expected_valid_days = int(row[22]) if len(row) > 22 and row[22] is not None else None

    cleaned_metadata = dict(metadata)
    raw_error_fp = cleaned_metadata.pop("error_fingerprint", None)
    raw_steps = cleaned_metadata.pop("resolution_steps", None)
    raw_chat_id = cleaned_metadata.pop("source_chat_id", None)
    raw_chat_ids = cleaned_metadata.pop("source_chat_ids", None)

    error_fp = str(raw_error_fp) if raw_error_fp else None

    return ProceduralMemory(
        id=str(row[0]),
        user_id=str(row[1]),
        content=str(row[2]),
        trigger=str(row[3]),
        action=str(row[4]),
        is_active=active,
        status=MemoryStatus.ACTIVE if active else MemoryStatus.DISABLED,
        trigger_keywords=keywords,
        source=RuleSource(row[7]) if row[7] else RuleSource.USER_EXTRACTED,
        metadata=cleaned_metadata,
        scope=MemoryScope(
            primary_namespace=str(row[9] or ""),
            namespaces=json.loads(row[10]) if row[10] else [],
            agent_id=str(row[11]) if row[11] else None,
            channel_id=str(row[12]) if row[12] else None,
            conversation_id=str(row[13]) if row[13] else None,
            task_id=str(row[14]) if row[14] else None,
        ),
        tool_name=tool_name_val,
        tool_rule_priority=tool_priority,
        access_count=int(row[17]) if row[17] else 0,
        last_accessed_at=parse_dt(str(row[18])) if row[18] else None,
        created_at=parse_dt(str(row[19])),
        updated_at=parse_dt(str(row[20])),
        is_user_locked=is_locked,
        expected_valid_days=expected_valid_days,
        error_fingerprint=error_fp,
        resolution_steps=_json_string_list(raw_steps),
        source_chat_id=str(raw_chat_id) if raw_chat_id else None,
        source_chat_ids=_json_string_list(raw_chat_ids),
    )


def row_to_pending(row: tuple[object, ...]) -> PendingRecord:
    """Column order: id, user_id, memory_type, content, memory_data,
    source_chat_id, source_message_id, status, created_at, resolved_at,
    resolution_action, target_memory_id, target_content.
    """
    memory_data = json.loads(str(row[4])) if row[4] else {}
    try:
        resolution_action = (
            PendingResolutionAction(str(row[10])) if len(row) > 10 and row[10] else PendingResolutionAction.STORE
        )
    except ValueError:
        resolution_action = PendingResolutionAction.STORE
    return PendingRecord(
        id=str(row[0]),
        user_id=str(row[1]),
        memory_type=MemoryType(row[2]),
        content=str(row[3]),
        memory_data=memory_data,
        source_chat_id=str(row[5]) if row[5] else None,
        source_message_id=str(row[6]) if row[6] else None,
        status=str(row[7]),
        created_at=parse_dt(str(row[8])),
        resolved_at=parse_dt(str(row[9])) if row[9] else None,
        resolution_action=resolution_action,
        target_memory_id=str(row[11]) if len(row) > 11 and row[11] else None,
        target_content=str(row[12]) if len(row) > 12 and row[12] else None,
    )
