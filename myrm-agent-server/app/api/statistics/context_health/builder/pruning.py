"""[INPUT]
- .context_health_cache / .context_health_restore (POS: cache + restore health layers)

[OUTPUT]
- _build_pruning_health

[POS]
Statistics context-health builder: context pruning health.
"""

from __future__ import annotations

from collections.abc import Mapping

from ..context_health_restore import to_restore_block_events
from .coercion import (
    _ensure_count,
    _increment_count,
    _restore_counts_from_outcomes,
    _restore_result_totals_from_events,
    _to_bool,
    _to_count_map,
    _to_int,
    _to_non_negative_int,
    _to_ratio,
    _to_string_list,
)
from .models import (
    _BACKOFF_HIGH_REFETCH_RATIO,
    _BACKOFF_HIGH_RESTORE_COST_RATIO,
    _BACKOFF_LOW_RESTORE_ROI_RATIO,
    _BACKOFF_NEGATIVE_NET_SAVINGS,
    _REFETCH_RATIO_BACKOFF_WARNING,
    _RESTORE_COST_RATIO_WARNING,
    _RESTORE_ROI_RATIO_WARNING,
    HealthStatus,
    PruningHealth,
)


def _build_pruning_health(task_metrics: Mapping[str, object]) -> PruningHealth:
    archive_summary_raw = task_metrics.get("archive_summary")
    archive_summary_queued_count = 0
    archive_summary_succeeded_count = 0
    archive_summary_failed_count = 0
    archive_summary_skipped_count = 0
    archive_summary_skipped_reasons: dict[str, int] = {}
    if isinstance(archive_summary_raw, dict):
        archive_summary_queued_count = _to_non_negative_int(archive_summary_raw.get("queued_count"))
        archive_summary_succeeded_count = _to_non_negative_int(archive_summary_raw.get("succeeded_count"))
        archive_summary_failed_count = _to_non_negative_int(archive_summary_raw.get("failed_count"))
        archive_summary_skipped_count = _to_non_negative_int(archive_summary_raw.get("skipped_count"))
        archive_summary_skipped_reasons = _to_count_map(archive_summary_raw.get("skipped_reasons"))

    archived = _to_non_negative_int(task_metrics.get("archive_count"))
    soft_trimmed = _to_non_negative_int(task_metrics.get("soft_trimmed_count"))
    offload_failed = _to_non_negative_int(task_metrics.get("offload_failed_count"))
    archive_written_count = _to_non_negative_int(task_metrics.get("archive_written_count"))
    archive_reused_count = _to_non_negative_int(task_metrics.get("archive_reused_count"))
    archive_bytes_written = _to_non_negative_int(task_metrics.get("archive_bytes_written"))
    archive_bytes_reused = _to_non_negative_int(task_metrics.get("archive_bytes_reused"))
    archive_refetch_count = _to_non_negative_int(task_metrics.get("archive_refetch_count"))
    archive_refetch_tokens = _to_non_negative_int(task_metrics.get("archive_refetch_tokens"))
    archive_restore_requested_count = _to_non_negative_int(task_metrics.get("archive_restore_requested_count"))
    archive_restore_allowed_count = _to_non_negative_int(task_metrics.get("archive_restore_allowed_count"))
    deferred_count = _to_non_negative_int(task_metrics.get("prune_deferred_count"))
    deferred_reasons = _to_count_map(task_metrics.get("prune_deferred_reasons"))
    archive_deferred_count = _to_non_negative_int(task_metrics.get("archive_deferred_count"))
    archive_deferred_reasons = _to_count_map(task_metrics.get("archive_deferred_reasons"))
    archive_deferred_soft_trimmed_count = _to_non_negative_int(task_metrics.get("archive_deferred_soft_trimmed_count"))
    archive_deferred_soft_trimmed_reasons = _to_count_map(task_metrics.get("archive_deferred_soft_trimmed_reasons"))
    archive_restore_blocked_count = _to_non_negative_int(task_metrics.get("archive_restore_blocked_count"))
    archive_restore_block_events = to_restore_block_events(task_metrics.get("archive_restore_block_events"))
    restore_outcome_counts = _restore_counts_from_outcomes(task_metrics.get("archive_restore_outcome_events"))
    if restore_outcome_counts is not None:
        (
            archive_restore_requested_count,
            archive_restore_allowed_count,
            archive_restore_blocked_count,
        ) = restore_outcome_counts
    restore_result_totals = _restore_result_totals_from_events(task_metrics.get("archive_restore_result_events"))
    if restore_result_totals is None:
        archive_restore_result_count = _to_non_negative_int(task_metrics.get("archive_restore_result_count"))
        archive_restore_result_tokens = _to_non_negative_int(task_metrics.get("archive_restore_result_tokens"))
        archive_restore_result_lines = _to_non_negative_int(task_metrics.get("archive_restore_result_lines"))
        archive_restore_result_bytes = _to_non_negative_int(task_metrics.get("archive_restore_result_bytes"))
    else:
        (
            archive_restore_result_count,
            archive_restore_result_tokens,
            archive_restore_result_lines,
            archive_restore_result_bytes,
        ) = restore_result_totals
    archive_restore_blocked_ratio = (
        archive_restore_blocked_count / archive_restore_requested_count if archive_restore_requested_count > 0 else 0.0
    )
    offload_failure_kinds = _to_count_map(task_metrics.get("offload_failure_kinds"))
    original_tokens = _to_non_negative_int(task_metrics.get("archived_original_tokens"))
    tokens_saved = _to_non_negative_int(task_metrics.get("pruning_tokens_saved"))
    net_tokens_saved = _to_int(task_metrics.get("pruning_net_tokens_saved"))
    backoff_applied = _to_bool(task_metrics.get("pruning_backoff_applied"))
    backoff_reasons = _to_count_map(task_metrics.get("pruning_backoff_reasons"))
    effective_soft_trim_ratio = _to_ratio(task_metrics.get("pruning_effective_soft_trim_ratio"))
    effective_hard_clear_ratio = _to_ratio(task_metrics.get("pruning_effective_hard_clear_ratio"))
    effective_min_prunable_tokens = _to_non_negative_int(task_metrics.get("pruning_effective_min_prunable_tokens"))
    backoff_sample_count = _to_non_negative_int(task_metrics.get("pruning_backoff_sample_count"))
    backoff_bad_signal_count = _to_non_negative_int(task_metrics.get("pruning_backoff_bad_signal_count"))
    backoff_recovery_sample_count = _to_non_negative_int(task_metrics.get("pruning_backoff_recovery_sample_count"))
    has_explicit_backoff_contract = (
        "pruning_backoff_applied" in task_metrics
        or "pruning_backoff_reasons" in task_metrics
        or "pruning_backoff_sample_count" in task_metrics
    )

    compression_events = task_metrics.get("compression_events")
    use_prune_event_counts = archived == 0 and soft_trimmed == 0 and offload_failed == 0
    use_event_deferred_counts = deferred_count == 0 and not deferred_reasons
    use_event_archive_deferred_counts = archive_deferred_count == 0 and not archive_deferred_reasons
    use_event_archive_deferred_soft_trimmed_counts = (
        archive_deferred_soft_trimmed_count == 0 and not archive_deferred_soft_trimmed_reasons
    )
    if isinstance(compression_events, list):
        for raw_event in compression_events:
            if not isinstance(raw_event, dict):
                continue
            if raw_event.get("compression_type") != "cache_ttl_prune":
                continue
            has_explicit_backoff_contract = has_explicit_backoff_contract or any(
                key in raw_event
                for key in (
                    "backoff_applied",
                    "backoff_reasons",
                    "backoff_sample_count",
                )
            )
            if _to_bool(raw_event.get("backoff_applied")):
                backoff_applied = True
            for reason in _to_string_list(raw_event.get("backoff_reasons")):
                _increment_count(backoff_reasons, reason)
            event_soft_trim_ratio = _to_ratio(raw_event.get("effective_soft_trim_ratio"))
            event_hard_clear_ratio = _to_ratio(raw_event.get("effective_hard_clear_ratio"))
            event_min_prunable_tokens = _to_non_negative_int(raw_event.get("effective_min_prunable_tokens"))
            if event_soft_trim_ratio > 0:
                effective_soft_trim_ratio = event_soft_trim_ratio
            if event_hard_clear_ratio > 0:
                effective_hard_clear_ratio = event_hard_clear_ratio
            if event_min_prunable_tokens > 0:
                effective_min_prunable_tokens = event_min_prunable_tokens
            event_sample_count = _to_non_negative_int(raw_event.get("backoff_sample_count"))
            event_bad_signal_count = _to_non_negative_int(raw_event.get("backoff_bad_signal_count"))
            event_recovery_sample_count = _to_non_negative_int(raw_event.get("backoff_recovery_sample_count"))
            if event_sample_count > 0:
                backoff_sample_count = event_sample_count
            if event_bad_signal_count > 0:
                backoff_bad_signal_count = event_bad_signal_count
            if event_recovery_sample_count > 0:
                backoff_recovery_sample_count = event_recovery_sample_count
            for kind, count in _to_count_map(raw_event.get("offload_failure_kinds")).items():
                if kind in offload_failure_kinds:
                    continue
                offload_failure_kinds[kind] = count
            if use_event_deferred_counts:
                for reason, count in _to_count_map(raw_event.get("deferred_reasons")).items():
                    deferred_reasons[reason] = deferred_reasons.get(reason, 0) + count
                deferred_count += _to_non_negative_int(raw_event.get("deferred_count"))
            if use_event_archive_deferred_counts:
                for reason, count in _to_count_map(raw_event.get("archive_deferred_reasons")).items():
                    archive_deferred_reasons[reason] = archive_deferred_reasons.get(reason, 0) + count
                archive_deferred_count += _to_non_negative_int(raw_event.get("archive_deferred_count"))
            if use_event_archive_deferred_soft_trimmed_counts:
                for reason, count in _to_count_map(raw_event.get("archive_deferred_soft_trimmed_reasons")).items():
                    archive_deferred_soft_trimmed_reasons[reason] = archive_deferred_soft_trimmed_reasons.get(reason, 0) + count
                archive_deferred_soft_trimmed_count += _to_non_negative_int(raw_event.get("archive_deferred_soft_trimmed_count"))
            if use_prune_event_counts:
                archived += _to_non_negative_int(raw_event.get("archive_count"))
                soft_trimmed += _to_non_negative_int(raw_event.get("soft_trimmed_count"))
                offload_failed += _to_non_negative_int(raw_event.get("offload_failed_count"))
                archive_written_count += _to_non_negative_int(raw_event.get("archive_written_count"))
                archive_reused_count += _to_non_negative_int(raw_event.get("archive_reused_count"))
                archive_bytes_written += _to_non_negative_int(raw_event.get("archive_bytes_written"))
                archive_bytes_reused += _to_non_negative_int(raw_event.get("archive_bytes_reused"))
                original_tokens += _to_non_negative_int(raw_event.get("original_tokens"))
                tokens_saved += _to_non_negative_int(raw_event.get("tokens_saved"))

    if net_tokens_saved == 0 and (tokens_saved > 0 or archive_refetch_tokens > 0 or archive_restore_result_tokens > 0):
        net_tokens_saved = tokens_saved - archive_refetch_tokens - archive_restore_result_tokens
    pruning_restore_cost_ratio = archive_restore_result_tokens / tokens_saved if tokens_saved > 0 else 0.0
    pruning_restore_roi_ratio = net_tokens_saved / tokens_saved if tokens_saved > 0 else 0.0
    if not has_explicit_backoff_contract:
        if net_tokens_saved < 0:
            _ensure_count(backoff_reasons, _BACKOFF_NEGATIVE_NET_SAVINGS)
        if archive_restore_result_count > 0 and tokens_saved > 0:
            if pruning_restore_cost_ratio >= _RESTORE_COST_RATIO_WARNING:
                _ensure_count(backoff_reasons, _BACKOFF_HIGH_RESTORE_COST_RATIO)
            if pruning_restore_roi_ratio < _RESTORE_ROI_RATIO_WARNING:
                _ensure_count(backoff_reasons, _BACKOFF_LOW_RESTORE_ROI_RATIO)
    restore_cost_warning = archive_restore_result_count > 0 and (
        tokens_saved <= 0
        or pruning_restore_cost_ratio >= _RESTORE_COST_RATIO_WARNING
        or pruning_restore_roi_ratio < _RESTORE_ROI_RATIO_WARNING
    )

    active = (
        archived > 0
        or soft_trimmed > 0
        or offload_failed > 0
        or archive_refetch_count > 0
        or archive_restore_requested_count > 0
        or archive_restore_blocked_count > 0
        or archive_restore_result_count > 0
        or deferred_count > 0
        or archive_deferred_count > 0
        or archive_summary_succeeded_count > 0
        or archive_summary_queued_count > 0
    )
    pruned_count = archived + soft_trimmed
    refetch_ratio = archive_refetch_count / pruned_count if pruned_count > 0 else 0.0
    if refetch_ratio >= _REFETCH_RATIO_BACKOFF_WARNING:
        if not has_explicit_backoff_contract:
            _ensure_count(backoff_reasons, _BACKOFF_HIGH_REFETCH_RATIO)
    backoff_applied = backoff_applied or (bool(backoff_reasons) and not has_explicit_backoff_contract)
    active = active or tokens_saved > 0 or backoff_applied
    if not active:
        status: HealthStatus = "inactive"
    elif (
        offload_failed > 0
        or deferred_count > 0
        or archive_deferred_count > archive_deferred_soft_trimmed_count
        or archive_restore_blocked_count > 0
        or net_tokens_saved < 0
        or restore_cost_warning
        or backoff_applied
    ):
        status = "warning"
    elif refetch_ratio >= _REFETCH_RATIO_BACKOFF_WARNING:
        status = "warning"
    else:
        status = "healthy"

    return PruningHealth(
        status=status,
        active=active,
        archived=archived,
        soft_trimmed=soft_trimmed,
        offload_failed=offload_failed,
        archive_written_count=archive_written_count,
        archive_reused_count=archive_reused_count,
        archive_bytes_written=archive_bytes_written,
        archive_bytes_reused=archive_bytes_reused,
        deferred_count=deferred_count,
        deferred_reasons=deferred_reasons,
        archive_deferred_count=archive_deferred_count,
        archive_deferred_reasons=archive_deferred_reasons,
        archive_deferred_soft_trimmed_count=archive_deferred_soft_trimmed_count,
        archive_deferred_soft_trimmed_reasons=archive_deferred_soft_trimmed_reasons,
        archive_refetch_count=archive_refetch_count,
        archive_refetch_tokens=archive_refetch_tokens,
        archive_restore_requested_count=archive_restore_requested_count,
        archive_restore_allowed_count=archive_restore_allowed_count,
        archive_restore_blocked_count=archive_restore_blocked_count,
        archive_restore_blocked_ratio=archive_restore_blocked_ratio,
        archive_restore_result_count=archive_restore_result_count,
        archive_restore_result_tokens=archive_restore_result_tokens,
        archive_restore_result_lines=archive_restore_result_lines,
        archive_restore_result_bytes=archive_restore_result_bytes,
        pruning_restore_cost_ratio=pruning_restore_cost_ratio,
        pruning_restore_roi_ratio=pruning_restore_roi_ratio,
        archive_restore_block_events=archive_restore_block_events,
        offload_failure_kinds=offload_failure_kinds,
        original_tokens=original_tokens,
        tokens_saved=tokens_saved,
        net_tokens_saved=net_tokens_saved,
        refetch_ratio=refetch_ratio,
        backoff_applied=backoff_applied,
        backoff_reasons=backoff_reasons,
        effective_soft_trim_ratio=effective_soft_trim_ratio,
        effective_hard_clear_ratio=effective_hard_clear_ratio,
        effective_min_prunable_tokens=effective_min_prunable_tokens,
        backoff_sample_count=backoff_sample_count,
        backoff_bad_signal_count=backoff_bad_signal_count,
        backoff_recovery_sample_count=backoff_recovery_sample_count,
        archive_summary_queued_count=archive_summary_queued_count,
        archive_summary_succeeded_count=archive_summary_succeeded_count,
        archive_summary_failed_count=archive_summary_failed_count,
        archive_summary_skipped_count=archive_summary_skipped_count,
        archive_summary_skipped_reasons=archive_summary_skipped_reasons,
    )
