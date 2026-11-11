"""ROI ledger of the cache-TTL prune: what a pass saved is recorded, and how the recent passes paid off sets the next one.

[INPUT]
- infra.schemas::CacheTtlPruneConfig (POS: pruning thresholds and the ROI backoff knobs)
- tracking.task_metrics::TaskMetrics, get_task_metrics (POS: per-chat compression, refetch and archive restore events)
- processors.cache_ttl_prune_helpers::EffectivePrunePolicy, PruneStats (POS: session-adjusted thresholds and per-pass counters)

[OUTPUT]
- effective_prune_policy: the thresholds of one decision, raised while recent prunes cost more than they saved
- record_prune_metrics: write one pass's outcome into the chat's task metrics

[POS]
Feedback loop of the TTL prune. ``record_prune_metrics`` writes the passes into the task metrics; ``effective_prune_policy``
reads the recent ones back together with the restores and refetches of what they archived, and backs off while they did
not pay off, releasing only after enough healthy samples.
"""

from dataclasses import dataclass

from ...infra.schemas import CacheTtlPruneConfig
from ...tracking.task_metrics import TaskMetrics, get_task_metrics
from .cache_ttl_prune_helpers import EffectivePrunePolicy, PruneStats

_BACKOFF_NEGATIVE_NET_SAVINGS = "negative_net_savings"
_BACKOFF_HIGH_REFETCH_RATIO = "high_refetch_ratio"
_BACKOFF_HIGH_RESTORE_COST_RATIO = "high_restore_cost_ratio"
_BACKOFF_LOW_RESTORE_ROI_RATIO = "low_restore_roi_ratio"
_BACKOFF_RECOVERY_HYSTERESIS = "recovery_hysteresis"


@dataclass(frozen=True, slots=True)
class _BackoffWindow:
    reasons: tuple[str, ...] = ()
    sample_count: int = 0
    bad_signal_count: int = 0
    recovery_sample_count: int = 0


def effective_prune_policy(config: CacheTtlPruneConfig, chat_id: str | None) -> EffectivePrunePolicy:
    """Back off pruning when previous archive restores made ROI poor."""
    policy = EffectivePrunePolicy(
        soft_trim_ratio=config.soft_trim_ratio,
        hard_clear_ratio=config.hard_clear_ratio,
        min_prunable_tokens=config.min_prunable_tokens,
    )
    if not chat_id:
        return policy

    metrics = get_task_metrics(chat_id)
    if metrics is None:
        return policy

    backoff_window = _evaluate_backoff(config, metrics)
    reasons = backoff_window.reasons

    if not reasons:
        return EffectivePrunePolicy(
            soft_trim_ratio=policy.soft_trim_ratio,
            hard_clear_ratio=policy.hard_clear_ratio,
            min_prunable_tokens=policy.min_prunable_tokens,
            backoff_sample_count=backoff_window.sample_count,
            backoff_bad_signal_count=backoff_window.bad_signal_count,
            backoff_recovery_sample_count=backoff_window.recovery_sample_count,
        )

    bump = max(config.roi_soft_trim_ratio_bump, 0.0)
    return EffectivePrunePolicy(
        soft_trim_ratio=min(policy.soft_trim_ratio + bump, 1.0),
        hard_clear_ratio=min(policy.hard_clear_ratio + bump, 1.0),
        min_prunable_tokens=max(policy.min_prunable_tokens * 2, policy.min_prunable_tokens),
        backoff_applied=True,
        backoff_reasons=reasons,
        backoff_sample_count=backoff_window.sample_count,
        backoff_bad_signal_count=backoff_window.bad_signal_count,
        backoff_recovery_sample_count=backoff_window.recovery_sample_count,
    )


def _evaluate_backoff(config: CacheTtlPruneConfig, metrics: TaskMetrics) -> _BackoffWindow:
    """Evaluate recent cache-TTL prune ROI with minimum samples and release hysteresis."""
    window_size = max(config.roi_backoff_window_size, 1)
    recent_prunes = [
        event
        for event in metrics.compression_events
        if event.compression_type == "cache_ttl_prune" and event.tokens_saved > 0
    ][-window_size:]
    sample_count = len(recent_prunes)
    if sample_count == 0:
        return _BackoffWindow()

    minimum_samples = max(config.roi_backoff_min_samples, 1)
    recovery_samples = max(config.roi_backoff_recovery_samples, minimum_samples)
    if sample_count < minimum_samples:
        if metrics.pruning_backoff_applied and sample_count < recovery_samples:
            return _BackoffWindow(
                reasons=(_BACKOFF_RECOVERY_HYSTERESIS,),
                sample_count=sample_count,
                recovery_sample_count=sample_count,
            )
        return _BackoffWindow(sample_count=sample_count)

    window_start = recent_prunes[0].timestamp
    tokens_saved = sum(event.tokens_saved for event in recent_prunes)
    window_refetch_events = [
        event
        for event in metrics.refetch_events
        if event.timestamp >= window_start and event.reason == "archive_reference_read"
    ]
    window_restore_events = [
        event for event in metrics.archive_restore_result_events if event.timestamp >= window_start
    ]
    refetch_ratio = len(window_refetch_events) / sample_count if sample_count > 0 else 0.0
    restore_tokens = sum(event.estimated_tokens for event in window_restore_events)
    net_tokens_saved = tokens_saved - sum(event.estimated_tokens for event in window_refetch_events) - restore_tokens
    restore_cost_ratio = restore_tokens / tokens_saved if tokens_saved > 0 else 0.0
    restore_roi_ratio = net_tokens_saved / tokens_saved if tokens_saved > 0 else 0.0

    bad_reasons: list[str] = []
    if net_tokens_saved < 0:
        bad_reasons.append(_BACKOFF_NEGATIVE_NET_SAVINGS)
    if refetch_ratio >= config.roi_refetch_ratio_backoff:
        bad_reasons.append(_BACKOFF_HIGH_REFETCH_RATIO)
    if window_restore_events:
        if restore_cost_ratio >= config.roi_restore_cost_ratio_backoff:
            bad_reasons.append(_BACKOFF_HIGH_RESTORE_COST_RATIO)
        if restore_roi_ratio < config.roi_restore_roi_ratio_backoff:
            bad_reasons.append(_BACKOFF_LOW_RESTORE_ROI_RATIO)

    recovery_sample_count = sample_count if not bad_reasons else 0
    if not bad_reasons and metrics.pruning_backoff_applied and recovery_sample_count < recovery_samples:
        return _BackoffWindow(
            reasons=(_BACKOFF_RECOVERY_HYSTERESIS,),
            sample_count=sample_count,
            recovery_sample_count=recovery_sample_count,
        )

    return _BackoffWindow(
        reasons=tuple(bad_reasons),
        sample_count=sample_count,
        bad_signal_count=len(bad_reasons),
        recovery_sample_count=recovery_sample_count,
    )


def record_prune_metrics(
    chat_id: str | None,
    tokens_saved: int,
    stats: PruneStats,
    policy: EffectivePrunePolicy,
    *,
    elapsed_ms: int = 0,
) -> None:
    """Record task-level pruning metrics when a chat-scoped metrics object exists."""
    if not chat_id:
        return
    if tokens_saved <= 0 and stats.deferred == 0 and stats.offload_failed == 0 and stats.archive_deferred == 0:
        return
    metrics = get_task_metrics(chat_id)
    if metrics is None:
        return
    metrics.record_compression(
        tokens_saved=tokens_saved,
        compression_type="cache_ttl_prune",
        details=(
            f"Cache TTL prune archived={stats.archived}, "
            f"soft_trimmed={stats.soft_trimmed}, offload_failed={stats.offload_failed}, "
            f"archive_written={stats.archive_written}, archive_reused={stats.archive_reused}, "
            f"unmodified_deferred={stats.deferred}, archive_deferred={stats.archive_deferred}, "
            f"archive_deferred_soft_trimmed={stats.archive_deferred_soft_trimmed}, "
            f"original_tokens={stats.original_tokens}, backoff={policy.backoff_applied}, "
            f"backoff_reasons={','.join(policy.backoff_reasons)}, "
            f"backoff_samples={policy.backoff_sample_count}, "
            f"backoff_bad_signals={policy.backoff_bad_signal_count}, "
            f"backoff_recovery_samples={policy.backoff_recovery_sample_count}"
        ),
        group_count=stats.archived + stats.soft_trimmed,
        archive_count=stats.archived,
        soft_trimmed_count=stats.soft_trimmed,
        offload_failed_count=stats.offload_failed,
        offload_failure_kinds=stats.offload_failure_kinds,
        deferred_count=stats.deferred,
        deferred_reasons=stats.deferred_reasons,
        archive_deferred_count=stats.archive_deferred,
        archive_deferred_reasons=stats.archive_deferred_reasons,
        archive_deferred_soft_trimmed_count=stats.archive_deferred_soft_trimmed,
        archive_deferred_soft_trimmed_reasons=stats.archive_deferred_soft_trimmed_reasons,
        original_tokens=stats.original_tokens,
        archive_written_count=stats.archive_written,
        archive_reused_count=stats.archive_reused,
        archive_bytes_written=stats.archive_bytes_written,
        archive_bytes_reused=stats.archive_bytes_reused,
        backoff_applied=policy.backoff_applied,
        backoff_reasons=list(policy.backoff_reasons),
        effective_soft_trim_ratio=policy.soft_trim_ratio,
        effective_hard_clear_ratio=policy.hard_clear_ratio,
        effective_min_prunable_tokens=policy.min_prunable_tokens,
        backoff_sample_count=policy.backoff_sample_count,
        backoff_bad_signal_count=policy.backoff_bad_signal_count,
        backoff_recovery_sample_count=policy.backoff_recovery_sample_count,
        elapsed_ms=elapsed_ms,
    )
