"""[INPUT]
- .context_health_cache / .context_health_restore (POS: cache + restore health layers)

[OUTPUT]
- HealthStatus, health thresholds and the four health DTOs

[POS]
Statistics context-health builder: health DTOs, the HealthStatus vocabulary and warning thresholds.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Literal

from ..context_health_cache import CacheHealth
from ..context_health_restore import RestoreBlockEventHealth

HealthStatus = Literal["inactive", "healthy", "warning", "critical"]


_STATUS_RANK: dict[HealthStatus, int] = {
    "inactive": 0,
    "healthy": 1,
    "warning": 2,
    "critical": 3,
}


_RESTORE_COST_RATIO_WARNING = 0.5


_RESTORE_ROI_RATIO_WARNING = 0.5


_REFETCH_RATIO_BACKOFF_WARNING = 0.5


_BACKOFF_NEGATIVE_NET_SAVINGS = "negative_net_savings"


_BACKOFF_HIGH_REFETCH_RATIO = "high_refetch_ratio"


_BACKOFF_HIGH_RESTORE_COST_RATIO = "high_restore_cost_ratio"


_BACKOFF_LOW_RESTORE_ROI_RATIO = "low_restore_roi_ratio"


@dataclass(frozen=True, slots=True)
class ChatCompactionSnapshot:
    summary_persisted: bool
    last_compacted_at: str | None
    cumulative_tokens_saved: int


@dataclass(frozen=True, slots=True)
class CompactionHealth:
    status: HealthStatus
    active: bool
    count: int
    tokens_saved: int
    net_tokens_saved: int
    efficiency: float
    refetch_count: int
    refetch_ratio: float
    dedup_tokens_saved: int
    integrity_skipped: int
    summary_persisted: bool
    last_compacted_at: str | None
    avg_elapsed_ms: int
    last_elapsed_ms: int


@dataclass(frozen=True, slots=True)
class PruningHealth:
    status: HealthStatus
    active: bool
    archived: int
    soft_trimmed: int
    offload_failed: int
    archive_written_count: int
    archive_reused_count: int
    archive_bytes_written: int
    archive_bytes_reused: int
    deferred_count: int
    deferred_reasons: dict[str, int]
    archive_deferred_count: int
    archive_deferred_reasons: dict[str, int]
    archive_deferred_soft_trimmed_count: int
    archive_deferred_soft_trimmed_reasons: dict[str, int]
    archive_refetch_count: int
    archive_refetch_tokens: int
    archive_restore_requested_count: int
    archive_restore_allowed_count: int
    archive_restore_blocked_count: int
    archive_restore_blocked_ratio: float
    archive_restore_result_count: int
    archive_restore_result_tokens: int
    archive_restore_result_lines: int
    archive_restore_result_bytes: int
    pruning_restore_cost_ratio: float
    pruning_restore_roi_ratio: float
    archive_restore_block_events: list[RestoreBlockEventHealth]
    offload_failure_kinds: dict[str, int]
    original_tokens: int
    tokens_saved: int
    net_tokens_saved: int
    refetch_ratio: float
    backoff_applied: bool
    backoff_reasons: dict[str, int]
    effective_soft_trim_ratio: float
    effective_hard_clear_ratio: float
    effective_min_prunable_tokens: int
    backoff_sample_count: int
    backoff_bad_signal_count: int
    backoff_recovery_sample_count: int
    archive_summary_queued_count: int
    archive_summary_succeeded_count: int
    archive_summary_failed_count: int
    archive_summary_skipped_count: int
    archive_summary_skipped_reasons: dict[str, int]


@dataclass(frozen=True, slots=True)
class ContextHealth:
    status: HealthStatus
    compaction: CompactionHealth
    pruning: PruningHealth
    cache: CacheHealth

    def to_dict(self) -> dict[str, object]:
        return asdict(self)
