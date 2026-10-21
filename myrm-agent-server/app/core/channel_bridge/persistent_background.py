"""Persistent background work metadata helpers (Kanban /btw + voice spawn SSOT).

[INPUT]
- (none — pure constants and predicates)

[OUTPUT]
- BACKGROUND_SOURCE_BTW, BACKGROUND_SOURCE_VOICE: metadata source literals
- is_persistent_background(): predicate for Kanban-backed background tasks

[POS]
Server business layer. Shared by ChannelBackgroundTaskHandler, KanbanTaskRunner,
and event publishers.
"""

from __future__ import annotations

from typing import Final

BACKGROUND_SOURCE_BTW: Final = "btw"
BACKGROUND_SOURCE_VOICE: Final = "voice"

_PERSISTENT_BACKGROUND_SOURCES: frozenset[str] = frozenset({BACKGROUND_SOURCE_BTW, BACKGROUND_SOURCE_VOICE})

__all__ = [
    "BACKGROUND_SOURCE_BTW",
    "BACKGROUND_SOURCE_VOICE",
    "is_persistent_background",
]


def is_persistent_background(metadata: dict[str, object] | None) -> bool:
    """Return True when task metadata marks a Kanban-backed background work item."""
    if not metadata:
        return False
    source = metadata.get("background_source")
    return isinstance(source, str) and source in _PERSISTENT_BACKGROUND_SOURCES
