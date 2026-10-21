"""Lossless context compaction service (public facade).

Stable import path for server callers. Implementation lives under ``compact/``.

[INPUT]
- compact.service, compact.persist, compact.idle_estimate, compact.archive (POS: submodules)

[OUTPUT]
- Re-exports: compact_chat, persist_compaction, CompactResult, idle estimate helpers, archive API

[POS]
Chat context compaction facade. Preserves ``app.services.chat.compact_service`` import path.
"""

from __future__ import annotations

from app.services.chat.compact._types import CompactResult
from app.services.chat.compact.archive import get_archived_messages
from app.services.chat.compact.idle_estimate import (
    estimate_compactable_context_tokens,
    estimate_idle_compact_request_tokens,
    resolve_idle_compact_token_floor,
    resolve_min_messages_to_compact,
)

# Idle estimate internal helper kept for tests patching compact_service namespace.
from app.services.chat.compact.persist import (
    is_compaction_failure_cooldown_active,
    persist_compaction,
)
from app.services.chat.compact.service import compact_chat

__all__ = [
    "CompactResult",
    "compact_chat",
    "estimate_compactable_context_tokens",
    "estimate_idle_compact_request_tokens",
    "get_archived_messages",
    "is_compaction_failure_cooldown_active",
    "persist_compaction",
    "resolve_idle_compact_token_floor",
    "resolve_min_messages_to_compact",
]
