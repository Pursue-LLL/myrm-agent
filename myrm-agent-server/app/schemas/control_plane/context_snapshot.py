"""[INPUT]
- pydantic::BaseModel (POS: schema base)

[OUTPUT]
- ContextCompactionSnapshot

[POS]
Control-plane schemas: the full context-compaction snapshot payload.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, Field

from .coercion import _to_count_map, _to_float, _to_int, _to_mapping_list, _to_signed_int, _to_str
from .context_events import (
    ContextArchiveRestoreBlockEventSnapshot,
    ContextArchiveRestoreOutcomeEventSnapshot,
    ContextArchiveRestoreResultEventSnapshot,
    ContextCompressionEventSnapshot,
    ContextRefetchEventSnapshot,
)


class ContextCompactionSnapshot(BaseModel):
    """Content-blind task-metrics snapshot for context compaction telemetry."""

    task_id: str = ""
    task_start_time: str = ""
    tokens_per_task: int = 0
    total_input_tokens: int = 0
    total_output_tokens: int = 0
    total_tokens_saved: int = 0
    net_tokens_saved: int = 0
    compression_efficiency: float = 0.0
    compression_count: int = 0
    compression_events: list[ContextCompressionEventSnapshot] = Field(default_factory=list)
    archive_count: int = 0
    soft_trimmed_count: int = 0
    offload_failed_count: int = 0
    prune_deferred_count: int = 0
    prune_deferred_reasons: dict[str, int] = Field(default_factory=dict)
    archive_deferred_count: int = 0
    archive_deferred_reasons: dict[str, int] = Field(default_factory=dict)
    archive_deferred_soft_trimmed_count: int = 0
    archive_deferred_soft_trimmed_reasons: dict[str, int] = Field(default_factory=dict)
    archived_original_tokens: int = 0
    refetch_count: int = 0
    refetch_ratio: float = 0.0
    archive_refetch_count: int = 0
    archive_refetch_tokens: int = 0
    archive_restore_requested_count: int = 0
    archive_restore_allowed_count: int = 0
    archive_restore_blocked_count: int = 0
    archive_restore_blocked_ratio: float = 0.0
    archive_restore_outcome_events: list[ContextArchiveRestoreOutcomeEventSnapshot] = Field(default_factory=list)
    archive_restore_result_count: int = 0
    archive_restore_result_tokens: int = 0
    archive_restore_result_lines: int = 0
    archive_restore_result_bytes: int = 0
    pruning_restore_cost_ratio: float = 0.0
    pruning_restore_roi_ratio: float = 0.0
    pruning_backoff_applied: bool = False
    pruning_backoff_reasons: dict[str, int] = Field(default_factory=dict)
    pruning_effective_soft_trim_ratio: float = 0.0
    pruning_effective_hard_clear_ratio: float = 0.0
    pruning_effective_min_prunable_tokens: int = 0
    pruning_backoff_sample_count: int = 0
    pruning_backoff_bad_signal_count: int = 0
    pruning_backoff_recovery_sample_count: int = 0
    archive_restore_result_events: list[ContextArchiveRestoreResultEventSnapshot] = Field(default_factory=list)
    archive_restore_block_events: list[ContextArchiveRestoreBlockEventSnapshot] = Field(default_factory=list)
    offload_failure_kinds: dict[str, int] = Field(default_factory=dict)
    pruning_tokens_saved: int = 0
    pruning_net_tokens_saved: int = 0
    refetch_events: list[ContextRefetchEventSnapshot] = Field(default_factory=list)
    task_duration_seconds: float = 0.0
    avg_compression_elapsed_ms: int = 0
    last_compression_elapsed_ms: int = 0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ContextCompactionSnapshot":
        compression_events = [
            ContextCompressionEventSnapshot.from_mapping(event) for event in _to_mapping_list(raw.get("compression_events"))
        ]
        refetch_events = [
            ContextRefetchEventSnapshot.from_mapping(event) for event in _to_mapping_list(raw.get("refetch_events"))
        ]
        archive_restore_block_events = [
            ContextArchiveRestoreBlockEventSnapshot.from_mapping(event)
            for event in _to_mapping_list(raw.get("archive_restore_block_events"))
        ]
        archive_restore_outcome_events = [
            ContextArchiveRestoreOutcomeEventSnapshot.from_mapping(event)
            for event in _to_mapping_list(raw.get("archive_restore_outcome_events"))
        ]
        archive_restore_result_events = [
            ContextArchiveRestoreResultEventSnapshot.from_mapping(event)
            for event in _to_mapping_list(raw.get("archive_restore_result_events"))
        ]
        return cls(
            task_id=_to_str(raw.get("task_id")),
            task_start_time=_to_str(raw.get("task_start_time")),
            tokens_per_task=_to_int(raw.get("tokens_per_task")),
            total_input_tokens=_to_int(raw.get("total_input_tokens")),
            total_output_tokens=_to_int(raw.get("total_output_tokens")),
            total_tokens_saved=_to_int(raw.get("total_tokens_saved")),
            net_tokens_saved=_to_int(raw.get("net_tokens_saved")),
            compression_efficiency=_to_float(raw.get("compression_efficiency")),
            compression_count=_to_int(raw.get("compression_count")),
            compression_events=compression_events,
            archive_count=_to_int(raw.get("archive_count")),
            soft_trimmed_count=_to_int(raw.get("soft_trimmed_count")),
            offload_failed_count=_to_int(raw.get("offload_failed_count")),
            prune_deferred_count=_to_int(raw.get("prune_deferred_count")),
            prune_deferred_reasons=_to_count_map(raw.get("prune_deferred_reasons")),
            archive_deferred_count=_to_int(raw.get("archive_deferred_count")),
            archive_deferred_reasons=_to_count_map(raw.get("archive_deferred_reasons")),
            archive_deferred_soft_trimmed_count=_to_int(raw.get("archive_deferred_soft_trimmed_count")),
            archive_deferred_soft_trimmed_reasons=_to_count_map(raw.get("archive_deferred_soft_trimmed_reasons")),
            archived_original_tokens=_to_int(raw.get("archived_original_tokens")),
            refetch_count=_to_int(raw.get("refetch_count")),
            refetch_ratio=_to_float(raw.get("refetch_ratio")),
            archive_refetch_count=_to_int(raw.get("archive_refetch_count")),
            archive_refetch_tokens=_to_int(raw.get("archive_refetch_tokens")),
            archive_restore_requested_count=_to_int(raw.get("archive_restore_requested_count")),
            archive_restore_allowed_count=_to_int(raw.get("archive_restore_allowed_count")),
            archive_restore_blocked_count=_to_int(raw.get("archive_restore_blocked_count")),
            archive_restore_blocked_ratio=_to_float(raw.get("archive_restore_blocked_ratio")),
            archive_restore_outcome_events=archive_restore_outcome_events,
            archive_restore_result_count=_to_int(raw.get("archive_restore_result_count")),
            archive_restore_result_tokens=_to_int(raw.get("archive_restore_result_tokens")),
            archive_restore_result_lines=_to_int(raw.get("archive_restore_result_lines")),
            archive_restore_result_bytes=_to_int(raw.get("archive_restore_result_bytes")),
            pruning_restore_cost_ratio=_to_float(raw.get("pruning_restore_cost_ratio")),
            pruning_restore_roi_ratio=_to_float(raw.get("pruning_restore_roi_ratio")),
            pruning_backoff_applied=bool(raw.get("pruning_backoff_applied")),
            pruning_backoff_reasons=_to_count_map(raw.get("pruning_backoff_reasons")),
            pruning_effective_soft_trim_ratio=_to_float(raw.get("pruning_effective_soft_trim_ratio")),
            pruning_effective_hard_clear_ratio=_to_float(raw.get("pruning_effective_hard_clear_ratio")),
            pruning_effective_min_prunable_tokens=_to_int(raw.get("pruning_effective_min_prunable_tokens")),
            pruning_backoff_sample_count=_to_int(raw.get("pruning_backoff_sample_count")),
            pruning_backoff_bad_signal_count=_to_int(raw.get("pruning_backoff_bad_signal_count")),
            pruning_backoff_recovery_sample_count=_to_int(raw.get("pruning_backoff_recovery_sample_count")),
            archive_restore_result_events=archive_restore_result_events,
            archive_restore_block_events=archive_restore_block_events,
            offload_failure_kinds=_to_count_map(raw.get("offload_failure_kinds")),
            pruning_tokens_saved=_to_int(raw.get("pruning_tokens_saved")),
            pruning_net_tokens_saved=_to_signed_int(raw.get("pruning_net_tokens_saved")),
            refetch_events=refetch_events,
            task_duration_seconds=_to_float(raw.get("task_duration_seconds")),
            avg_compression_elapsed_ms=_to_int(raw.get("avg_compression_elapsed_ms")),
            last_compression_elapsed_ms=_to_int(raw.get("last_compression_elapsed_ms")),
        )
