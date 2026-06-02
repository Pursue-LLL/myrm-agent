"""Session context-health aggregation.

[INPUT]
- app.api.statistics.context_health_cache::build_cache_health (POS: Statistics API cache-health layer. Owns provider/model sample selection so the context-health aggregate can stay focused on composition.)
- app.api.statistics.context_health_restore::to_restore_block_events (POS: Statistics API restore-health normalization layer. Converts raw task metrics into small, typed payloads before the main context-health aggregate is serialized.)

[OUTPUT]
- build_context_health: Aggregates message usage, chat compaction metadata, and task metrics into session context-health DTOs.

[POS]
Statistics context-health layer. Converts low-level usage, pruning, archive restore, adaptive backoff,
and prompt-cache metrics into stable API health signals.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import datetime
from typing import Literal

from app.api.statistics.context_health_cache import (
    CacheHealth,
    RetentionObservationState,
    build_cache_health,
)
from app.api.statistics.context_health_restore import (
    RestoreBlockEventHealth,
    to_restore_block_events,
)

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


def _max_status(left: HealthStatus, right: HealthStatus) -> HealthStatus:
    return left if _STATUS_RANK[left] >= _STATUS_RANK[right] else right


def _to_non_negative_int(value: object) -> int:
    return max(int(value), 0) if isinstance(value, (int, float)) else 0


def _to_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _to_ratio(value: object) -> float:
    if not isinstance(value, (int, float)):
        return 0.0
    numeric = float(value)
    if numeric < 0:
        return 0.0
    if numeric > 1:
        return 1.0
    return numeric


def _to_bool(value: object) -> bool:
    return value is True


def _to_count_map(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for raw_key, raw_count in value.items():
        if not isinstance(raw_key, str):
            continue
        count = _to_non_negative_int(raw_count)
        if count > 0:
            counts[raw_key] = count
    return counts


def _to_string_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str) and item]


def _increment_count(counts: dict[str, int], key: str) -> None:
    counts[key] = counts.get(key, 0) + 1


def _ensure_count(counts: dict[str, int], key: str) -> None:
    if key not in counts:
        counts[key] = 1


def _restore_counts_from_outcomes(value: object) -> tuple[int, int, int] | None:
    if not isinstance(value, list):
        return None

    requested = 0
    allowed = 0
    blocked = 0
    for raw_event in value:
        if not isinstance(raw_event, Mapping):
            continue
        outcome = raw_event.get("outcome")
        if outcome == "allowed":
            requested += 1
            allowed += 1
        elif outcome == "blocked":
            requested += 1
            blocked += 1

    if requested == 0:
        return None
    return requested, allowed, blocked


def _restore_result_totals_from_events(value: object) -> tuple[int, int, int, int] | None:
    if not isinstance(value, list):
        return None

    count = 0
    tokens = 0
    lines = 0
    bytes_count = 0
    for raw_event in value:
        if not isinstance(raw_event, Mapping):
            continue
        count += 1
        tokens += _to_non_negative_int(raw_event.get("estimated_tokens"))
        lines += _to_non_negative_int(raw_event.get("restored_line_count"))
        bytes_count += _to_non_negative_int(raw_event.get("restored_bytes"))

    if count == 0:
        return None
    return count, tokens, lines, bytes_count


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
