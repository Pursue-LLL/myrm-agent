"""Context-health builders.

[INPUT]
- .models / .coercion / .compaction / .pruning / .build (POS: builder stages)

[OUTPUT]
- build_context_health, build_chat_compaction_snapshot and the four health DTOs

[POS]
Aggregate exit of the context-health builder package.
"""

from __future__ import annotations

from .build import build_chat_compaction_snapshot, build_context_health
from .models import (
    ChatCompactionSnapshot,
    CompactionHealth,
    ContextHealth,
    HealthStatus,
    PruningHealth,
)

__all__ = [
    "ChatCompactionSnapshot",
    "CompactionHealth",
    "ContextHealth",
    "HealthStatus",
    "PruningHealth",
    "build_chat_compaction_snapshot",
    "build_context_health",
]
