"""Statistics context-health domain: compaction/pruning/cache/restore aggregates.

[INPUT]
- Task metrics (compaction outcomes, prune events) from session analytics.
- Message stats (provider/model buckets) for cache-health sample selection.
- Restore task outcomes/events for restore-health counters.

[OUTPUT]
- Aggregate facade re-exporting every public name of the ``context_health``
  subpackage:
  - context_health: ChatCompactionSnapshot / CompactionHealth / PruningHealth /
    ContextHealth + build_context_health / build_chat_compaction_snapshot
  - context_health_cache: CacheHealth + build_cache_health (provider/model
    sample selection)
  - context_health_restore: RestoreBlockEventHealth + to_restore_block_events
    (restore-outcome normalization)

[POS]
Server business layer (Statistics API). Single context-health domain: the
aggregate, its cache layer and restore normalizer are always consumed together
by ``api.statistics.session_analytics``, so they stay co-located under one
facade.
"""

from app.api.statistics.context_health.context_health import (
    CacheHealth,
    ChatCompactionSnapshot,
    CompactionHealth,
    ContextHealth,
    HealthStatus,
    PruningHealth,
    RetentionObservationState,
    build_chat_compaction_snapshot,
    build_context_health,
)
from app.api.statistics.context_health.context_health_cache import build_cache_health
from app.api.statistics.context_health.context_health_restore import (
    RestoreBlockEventHealth,
    RestoreContentFeatureHealth,
    RestoreRangeHintHealth,
    to_restore_block_events,
)

__all__ = [
    "CacheHealth",
    "ChatCompactionSnapshot",
    "CompactionHealth",
    "ContextHealth",
    "HealthStatus",
    "PruningHealth",
    "RestoreBlockEventHealth",
    "RestoreContentFeatureHealth",
    "RestoreRangeHintHealth",
    "RetentionObservationState",
    "build_cache_health",
    "build_chat_compaction_snapshot",
    "build_context_health",
    "to_restore_block_events",
]
