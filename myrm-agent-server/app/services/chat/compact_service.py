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

from myrm_agent_harness.utils.text_utils import get_token_count
from app.services.chat.compact._lock import get_compaction_lock as _get_compaction_lock
from app.services.chat.compact._types import CompactResult
from app.services.chat.compact.archive import get_archived_messages
from app.services.chat.compact.idle_estimate import (
    estimate_compactable_context_tokens,
    estimate_idle_compact_request_tokens,
    resolve_idle_compact_token_floor,
    resolve_min_messages_to_compact,
)
from app.services.chat.compact.llm_config import get_llm_for_user as _get_llm_for_user
from app.services.chat.compact.message_io import (
    backup_context as _backup_context,
    db_messages_to_langchain as _db_messages_to_langchain,
    load_chat as _load_chat,
    load_compactable_messages as _load_compactable_messages,
    parse_existing_summary as _parse_existing_summary,
)
from app.services.chat.compact.persist import (
    do_persist_to_db as _do_persist_to_db,
    is_compaction_failure_cooldown_active,
    persist_compaction,
    record_compaction_failure_cooldown as _record_compaction_failure_cooldown,
)
from app.services.chat.compact.service import compact_chat
from app.services.chat.compact.summarize_guard import guarded_compact_summarize as _guarded_compact_summarize

# Idle estimate internal helper kept for tests patching compact_service namespace.
from app.services.chat.compact.idle_estimate import (
    estimate_idle_compact_request_overhead as _estimate_idle_compact_request_overhead,
)

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
