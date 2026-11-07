"""[INPUT]
- .context_health_cache / .context_health_restore (POS: cache + restore health layers)

[OUTPUT]
- _build_compaction_health

[POS]
Statistics context-health builder: chat compaction health.
"""

from __future__ import annotations

from collections.abc import Mapping

from .coercion import (
    _to_non_negative_int,
    _to_ratio,
)
from .models import (
    ChatCompactionSnapshot,
    CompactionHealth,
    HealthStatus,
)


def _build_compaction_health(
    task_metrics: Mapping[str, object],
    chat_compaction: ChatCompactionSnapshot,
) -> CompactionHealth:
    count = _to_non_negative_int(task_metrics.get("compression_count"))
    tokens_saved = _to_non_negative_int(task_metrics.get("total_tokens_saved"))
    net_tokens_saved = _to_non_negative_int(task_metrics.get("net_tokens_saved"))
    refetch_count = _to_non_negative_int(task_metrics.get("refetch_count"))
    refetch_ratio = _to_ratio(task_metrics.get("refetch_ratio"))
    efficiency = _to_ratio(task_metrics.get("compression_efficiency"))

    dedup_tokens_saved = 0
    integrity_skipped = 0
    compression_events = task_metrics.get("compression_events")
    has_runtime_metrics = count > 0
    if isinstance(compression_events, list):
        has_runtime_metrics = has_runtime_metrics or len(compression_events) > 0
        for raw_event in compression_events:
            if not isinstance(raw_event, dict):
                continue
            dedup_tokens_saved += _to_non_negative_int(raw_event.get("dedup_tokens_saved"))
            integrity_skipped += _to_non_negative_int(raw_event.get("integrity_skipped"))

    if tokens_saved <= 0 and chat_compaction.cumulative_tokens_saved > 0:
        tokens_saved = chat_compaction.cumulative_tokens_saved
        if net_tokens_saved <= 0:
            net_tokens_saved = chat_compaction.cumulative_tokens_saved

    active = count > 0 or tokens_saved > 0 or chat_compaction.summary_persisted or chat_compaction.cumulative_tokens_saved > 0
    status: HealthStatus
    if not active:
        status = "inactive"
    elif not has_runtime_metrics and chat_compaction.summary_persisted:
        status = "healthy"
    elif integrity_skipped > 0 or refetch_ratio >= 0.5:
        status = "critical"
    elif refetch_count > 0 or refetch_ratio > 0.0 or efficiency < 0.05:
        status = "warning"
    else:
        status = "healthy"

    avg_elapsed_ms = _to_non_negative_int(task_metrics.get("avg_compression_elapsed_ms"))
    last_elapsed_ms = _to_non_negative_int(task_metrics.get("last_compression_elapsed_ms"))

    return CompactionHealth(
        status=status,
        active=active,
        count=count,
        tokens_saved=tokens_saved,
        net_tokens_saved=net_tokens_saved,
        efficiency=efficiency,
        refetch_count=refetch_count,
        refetch_ratio=refetch_ratio,
        dedup_tokens_saved=dedup_tokens_saved,
        integrity_skipped=integrity_skipped,
        summary_persisted=chat_compaction.summary_persisted,
        last_compacted_at=chat_compaction.last_compacted_at,
        avg_elapsed_ms=avg_elapsed_ms,
        last_elapsed_ms=last_elapsed_ms,
    )
