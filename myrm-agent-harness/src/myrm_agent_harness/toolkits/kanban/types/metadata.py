"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- 来源会话与完成意图的 metadata 键与读写函数

[POS]
`kanban/types/` 的 metadata 约定；任务与存储层共用同一组键。
"""

from __future__ import annotations

KANBAN_SOURCE_CHAT_METADATA_KEY = "source_chat_id"

KANBAN_COMPLETION_INTENT_KEY = "completion_intent"

def extract_source_chat_id(metadata: dict[str, object] | None) -> str | None:
    """Return trimmed source_chat_id from task metadata, or None."""
    if not metadata:
        return None
    raw = metadata.get(KANBAN_SOURCE_CHAT_METADATA_KEY)
    if not isinstance(raw, str):
        return None
    trimmed = raw.strip()
    return trimmed or None

def inherit_source_chat_metadata(
    parent_metadata: dict[str, object] | None,
) -> dict[str, object] | None:
    """Build metadata patch copying source_chat_id from a parent task."""
    source_chat_id = extract_source_chat_id(parent_metadata)
    if source_chat_id is None:
        return None
    return {KANBAN_SOURCE_CHAT_METADATA_KEY: source_chat_id}

def has_completion_intent(metadata: dict[str, object] | None) -> bool:
    """True when the worker called kanban_complete and verification is pending."""
    if not metadata:
        return False
    return metadata.get(KANBAN_COMPLETION_INTENT_KEY) is True

def clear_completion_intent(metadata: dict[str, object]) -> dict[str, object]:
    """Return metadata with completion_intent removed."""
    if KANBAN_COMPLETION_INTENT_KEY not in metadata:
        return metadata
    return {key: value for key, value in metadata.items() if key != KANBAN_COMPLETION_INTENT_KEY}
