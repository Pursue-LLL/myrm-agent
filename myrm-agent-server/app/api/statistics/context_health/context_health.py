"""Session context-health aggregation.

[INPUT]
- .builder (POS: aggregate builders) / .context_health_cache (POS: cache-health layer) / .context_health_restore (POS: restore-health normalisation)

[OUTPUT]
- build_context_health, build_chat_compaction_snapshot, the health DTOs, CacheHealth and RetentionObservationState

[POS]
Statistics context-health facade: converts usage, pruning, restore, backoff and prompt-cache metrics into stable API health signals.
"""

from __future__ import annotations

from .builder import (
    ChatCompactionSnapshot,
    CompactionHealth,
    ContextHealth,
    HealthStatus,
    PruningHealth,
    build_chat_compaction_snapshot,
    build_context_health,
)
from .context_health_cache import (
    CacheHealth,
    RetentionObservationState,
)

__all__ = [
    "CacheHealth",
    "ChatCompactionSnapshot",
    "CompactionHealth",
    "ContextHealth",
    "HealthStatus",
    "PruningHealth",
    "RetentionObservationState",
    "build_chat_compaction_snapshot",
    "build_context_health",
]
