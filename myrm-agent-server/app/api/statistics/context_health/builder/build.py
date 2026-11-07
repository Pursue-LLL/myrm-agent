"""[INPUT]
- .context_health_cache / .context_health_restore (POS: cache + restore health layers)

[OUTPUT]
- build_context_health, build_chat_compaction_snapshot

[POS]
Statistics context-health builder: the two public builders that compose the aggregate.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime

from ..context_health_cache import build_cache_health
from .coercion import (
    _max_status,
)
from .compaction import _build_compaction_health
from .models import (
    ChatCompactionSnapshot,
    ContextHealth,
)
from .pruning import _build_pruning_health


def build_context_health(
    *,
    message_stats: Mapping[str, object],
    task_metrics: Mapping[str, object],
    chat_compaction: ChatCompactionSnapshot,
    model_name: str | None = None,
) -> ContextHealth:
    compaction = _build_compaction_health(task_metrics, chat_compaction)
    pruning = _build_pruning_health(task_metrics)
    cache = build_cache_health(message_stats, model_name=model_name)
    status = _max_status(_max_status(compaction.status, pruning.status), cache.status)
    return ContextHealth(status=status, compaction=compaction, pruning=pruning, cache=cache)


def build_chat_compaction_snapshot(
    *,
    compacted_at: datetime | None,
    compacted_tokens_saved: int | None,
) -> ChatCompactionSnapshot:
    return ChatCompactionSnapshot(
        summary_persisted=compacted_at is not None,
        last_compacted_at=compacted_at.isoformat() if compacted_at is not None else None,
        cumulative_tokens_saved=max(compacted_tokens_saved or 0, 0),
    )
