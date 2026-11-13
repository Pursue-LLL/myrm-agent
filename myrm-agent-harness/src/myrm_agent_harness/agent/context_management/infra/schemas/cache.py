"""[INPUT]
- （无跨模块依赖）

[OUTPUT]
- CacheTtlPruneConfig / CacheUsageFeedback / 默认配置

[POS]
`infra/schemas/` 的缓存 TTL 裁剪配置与 provider 缓存反馈。
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class CacheTtlPruneConfig:
    """Cache-TTL based context pruning configuration.

    When prompt cache TTL expires, old tool results are no longer cached and
    retaining them costs full price. This config controls rule-based pruning
    that trims or archives expired tool results at zero API cost.
    """

    ttl_seconds: float = 300.0
    """Cache TTL in seconds. Default 5min covers Anthropic/Google/DeepSeek."""

    cold_cache_prune_enabled: bool = True
    """Whether a prompt cache that looks cold (idle past ``ttl_seconds``, or a stably low provider hit rate) may start a prune.

    Off for a route that signs its reasoning: the prune lasts one request, but a block signed in that request is bound
    to the pruned prompt and refused against the full one in the next. Context pressure
    (``emergency_prune_ratio``) prunes regardless.
    """

    soft_trim_ratio: float = 0.3
    """Context-to-window ratio at which soft trimming begins."""

    hard_clear_ratio: float = 0.5
    """Context-to-window ratio at which offloaded archival pruning begins."""

    keep_last_assistant_turns: int = 3
    """Number of most recent assistant turns whose tool results are protected."""

    min_prunable_tokens: int = 12_500
    """Minimum prunable tokens required to justify processing overhead."""

    soft_trim_head_chars: int = 1500
    """Characters to keep from the beginning of a tool result during soft trim."""

    soft_trim_tail_chars: int = 1500
    """Characters to keep from the end of a tool result during soft trim."""

    max_archives_per_pass: int = 8
    """Maximum archive offloads attempted by one pruning pass."""

    max_offload_bytes_per_pass: int = 2_000_000
    """Maximum original payload bytes offloaded by one pruning pass."""

    max_prune_wall_ms: int = 200
    """Best-effort wall-clock budget for one pruning pass."""

    large_payload_fast_guard_chars: int = 200_000
    """Payload size above which pruning uses bounded estimators and skips full JSON parsing."""

    roi_refetch_ratio_backoff: float = 0.5
    """Refetch ratio at which session-local pruning thresholds are raised."""

    roi_restore_cost_ratio_backoff: float = 0.5
    """Typed restore cost ratio at which session-local pruning thresholds are raised."""

    roi_restore_roi_ratio_backoff: float = 0.5
    """Retained pruning ROI ratio below which session-local pruning thresholds are raised."""

    roi_soft_trim_ratio_bump: float = 0.1
    """Threshold bump applied after poor pruning ROI."""

    roi_backoff_window_size: int = 6
    """Recent cache-TTL prune events evaluated for adaptive ROI backoff."""

    roi_backoff_min_samples: int = 2
    """Minimum recent prune samples required before activating ROI backoff."""

    roi_backoff_recovery_samples: int = 3
    """Healthy recent prune samples required before releasing prior ROI backoff."""

    emergency_prune_ratio: float = 0.92
    """Context ratio at which bounded prune may run during resume/HITL cache preservation."""

    archive_summary_enabled: bool = True
    """Enable background LLM summaries for high-value archived payloads."""

    archive_summary_min_tokens: int = 4_000
    """Minimum original payload tokens required before scheduling an archive summary."""

    archive_summary_max_input_chars: int = 30_000
    """Maximum archive characters sent to the summary LLM."""

    archive_summary_max_queue_size: int = 8
    """Maximum queued/running archive summary jobs per process."""

    archive_summary_max_concurrency: int = 1
    """Maximum concurrent archive summary LLM calls per process."""

    archive_summary_max_tasks_per_chat: int = 2
    """Maximum queued/running archive summary jobs for one chat."""


DEFAULT_CACHE_TTL_PRUNE_CONFIG = CacheTtlPruneConfig()


def _non_negative_int(value: object) -> int:
    return max(int(value), 0) if isinstance(value, (int, float)) else 0


def _ratio(value: object) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    return min(max(float(value), 0.0), 1.0)


@dataclass(frozen=True, slots=True)
class CacheUsageFeedback:
    """Provider cache usage feedback used by cache-TTL pruning decisions."""

    calls: int
    input_tokens: int
    cached_tokens: int
    cache_hit_rate: float

    @classmethod
    def from_mapping(cls, value: object) -> CacheUsageFeedback | None:
        if isinstance(value, CacheUsageFeedback):
            return value
        if not isinstance(value, dict):
            return None

        calls = _non_negative_int(value.get("calls"))
        input_tokens = _non_negative_int(value.get("input_tokens"))
        cached_tokens = _non_negative_int(value.get("cached_tokens"))
        cache_hit_rate = _ratio(value.get("cache_hit_rate"))
        if calls == 0 and input_tokens == 0 and cached_tokens == 0 and cache_hit_rate == 0.0:
            return None

        return cls(
            calls=calls,
            input_tokens=input_tokens,
            cached_tokens=cached_tokens,
            cache_hit_rate=cache_hit_rate,
        )

    @classmethod
    def from_flat_metadata(cls, metadata: dict[str, object]) -> CacheUsageFeedback | None:
        """Build feedback at the metadata boundary; processors consume the typed object only."""
        return cls.from_mapping(
            {
                "calls": metadata.get("calls"),
                "input_tokens": metadata.get("input_tokens"),
                "cached_tokens": metadata.get("cached_tokens"),
                "cache_hit_rate": metadata.get("cache_hit_rate"),
            }
        )

    def has_stable_sample(self, *, min_calls: int, min_input_tokens: int) -> bool:
        return self.calls >= min_calls or self.input_tokens >= min_input_tokens
