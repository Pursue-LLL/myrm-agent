"""Shared Pydantic schemas for Plane-Server API contracts.

[INPUT]
- Built-in mapping primitives.

[OUTPUT]
- ContextCompactionSnapshot: content-blind control-plane context compaction telemetry payload schema.
- TelemetryPushPayload: skill quality telemetry push payload schema.

[POS]
Server/control-plane API schema boundary. Normalizes shared Pydantic DTOs for telemetry exchange.
"""

from collections.abc import Mapping

from pydantic import BaseModel, Field


class SkillQualityTelemetry(BaseModel):
    """Telemetry data for a single skill's quality metrics."""
    skill_id: str
    overall_score: float
    success_rate: float
    execution_time: float
    call_frequency: float


class TelemetryPushPayload(BaseModel):
    """Payload for pushing skill telemetry to the control plane."""
    tenant_id: str
    timestamp: str
    skills: list[SkillQualityTelemetry]


class ContextCompressionEventSnapshot(BaseModel):
    """Structured compression/pruning event snapshot."""

    timestamp: str = ""
    tokens_saved: int = 0
    compression_type: str = ""
    details: str = ""
    group_count: int = 0
    dedup_tokens_saved: int = 0
    integrity_skipped: int = 0
    archive_count: int = 0
    soft_trimmed_count: int = 0
    offload_failed_count: int = 0
    offload_failure_kinds: dict[str, int] = Field(default_factory=dict)
    deferred_count: int = 0
    deferred_reasons: dict[str, int] = Field(default_factory=dict)
    archive_deferred_count: int = 0
    archive_deferred_reasons: dict[str, int] = Field(default_factory=dict)
    archive_deferred_soft_trimmed_count: int = 0
    archive_deferred_soft_trimmed_reasons: dict[str, int] = Field(default_factory=dict)
    original_tokens: int = 0
    backoff_applied: bool = False
    backoff_reasons: list[str] = Field(default_factory=list)
    effective_soft_trim_ratio: float = 0.0
    effective_hard_clear_ratio: float = 0.0
    effective_min_prunable_tokens: int = 0
    backoff_sample_count: int = 0
    backoff_bad_signal_count: int = 0
    backoff_recovery_sample_count: int = 0

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ContextCompressionEventSnapshot":
        return cls(
            timestamp=_to_str(raw.get("timestamp")),
            tokens_saved=_to_int(raw.get("tokens_saved")),
            compression_type=_to_str(raw.get("compression_type")),
            details=_to_str(raw.get("details")),
            group_count=_to_int(raw.get("group_count")),
            dedup_tokens_saved=_to_int(raw.get("dedup_tokens_saved")),
            integrity_skipped=_to_int(raw.get("integrity_skipped")),
            archive_count=_to_int(raw.get("archive_count")),
            soft_trimmed_count=_to_int(raw.get("soft_trimmed_count")),
            offload_failed_count=_to_int(raw.get("offload_failed_count")),
            offload_failure_kinds=_to_count_map(raw.get("offload_failure_kinds")),
            deferred_count=_to_int(raw.get("deferred_count")),
            deferred_reasons=_to_count_map(raw.get("deferred_reasons")),
            archive_deferred_count=_to_int(raw.get("archive_deferred_count")),
            archive_deferred_reasons=_to_count_map(raw.get("archive_deferred_reasons")),
            archive_deferred_soft_trimmed_count=_to_int(raw.get("archive_deferred_soft_trimmed_count")),
            archive_deferred_soft_trimmed_reasons=_to_count_map(
                raw.get("archive_deferred_soft_trimmed_reasons")
            ),
            original_tokens=_to_int(raw.get("original_tokens")),
            backoff_applied=bool(raw.get("backoff_applied")),
            backoff_reasons=_to_str_list(raw.get("backoff_reasons")),
            effective_soft_trim_ratio=_to_float(raw.get("effective_soft_trim_ratio")),
            effective_hard_clear_ratio=_to_float(raw.get("effective_hard_clear_ratio")),
            effective_min_prunable_tokens=_to_int(raw.get("effective_min_prunable_tokens")),
            backoff_sample_count=_to_int(raw.get("backoff_sample_count")),
            backoff_bad_signal_count=_to_int(raw.get("backoff_bad_signal_count")),
            backoff_recovery_sample_count=_to_int(raw.get("backoff_recovery_sample_count")),
        )


class ContextRefetchEventSnapshot(BaseModel):
    """Structured refetch event snapshot."""

    timestamp: str = ""
    reason: str = ""
    tool_name: str = ""
    estimated_tokens: int = 0
    archive_path: str = ""
    has_archive_path: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ContextRefetchEventSnapshot":
        return cls(
            timestamp=_to_str(raw.get("timestamp")),
            reason=_to_str(raw.get("reason")),
            tool_name=_to_str(raw.get("tool_name")),
            estimated_tokens=_to_int(raw.get("estimated_tokens")),
            archive_path="",
            has_archive_path=_has_text_or_flag(raw, "archive_path", "has_archive_path"),
        )


class ContextArchiveRestoreBlockEventSnapshot(BaseModel):
    """Structured archive restore block event snapshot."""

    timestamp: str = ""
    reason: str = ""
    estimated_tokens: int = 0
    archive_path: str = ""
    message: str = ""
    suggested_action: str = ""
    reason_label_key: str = ""
    severity: str = ""
    primary_restore_arg: str = ""
    has_archive_path: bool = False
    has_primary_restore_arg: bool = False
    recommended_ranges: list[str] = Field(default_factory=list)
    recommended_range_count: int = 0
    restore_range_hints: list[dict[str, object]] = Field(default_factory=list)
    restore_range_hint_count: int = 0
    content_features: list[dict[str, object]] = Field(default_factory=list)
    content_feature_count: int = 0
    guidance_source: str = ""
    fallback_reason: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ContextArchiveRestoreBlockEventSnapshot":
        guidance = raw.get("guidance")
        guidance_mapping = guidance if isinstance(guidance, Mapping) else {}
        primary_restore_arg = _first_str(
            raw.get("primary_restore_arg"),
            guidance_mapping.get("primary_restore_arg"),
        )
        recommended_ranges = _to_str_list(
            raw.get("recommended_ranges")
            or guidance_mapping.get("recommended_ranges")
        )
        restore_range_hints = _to_dict_list(
            raw.get("restore_range_hints")
            or guidance_mapping.get("restore_range_hints")
        )
        content_features = _to_dict_list(
            raw.get("content_features")
            or guidance_mapping.get("content_features")
        )
        return cls(
            timestamp=_to_str(raw.get("timestamp")),
            reason=_to_str(raw.get("reason")),
            estimated_tokens=_to_int(raw.get("estimated_tokens")),
            archive_path="",
            has_archive_path=_has_text_or_flag(raw, "archive_path", "has_archive_path"),
            message="",
            suggested_action="",
            reason_label_key=_first_str(
                raw.get("reason_label_key"),
                guidance_mapping.get("reason_label_key"),
            ),
            severity=_first_str(raw.get("severity"), guidance_mapping.get("severity")),
            primary_restore_arg="",
            has_primary_restore_arg=bool(primary_restore_arg) or bool(raw.get("has_primary_restore_arg")),
            recommended_ranges=[],
            recommended_range_count=_count_from_items_or_raw(
                len(recommended_ranges),
                raw,
                "recommended_range_count",
            ),
            restore_range_hints=[
                _content_blind_restore_range_hint(hint)
                for hint in restore_range_hints[:5]
            ],
            restore_range_hint_count=_count_from_items_or_raw(
                len(restore_range_hints),
                raw,
                "restore_range_hint_count",
            ),
            content_features=[
                _content_blind_content_feature(feature)
                for feature in content_features[:8]
            ],
            content_feature_count=_count_from_items_or_raw(
                len(content_features),
                raw,
                "content_feature_count",
            ),
            guidance_source=_first_str(
                raw.get("guidance_source"),
                guidance_mapping.get("guidance_source"),
            ),
            fallback_reason=_first_str(
                raw.get("fallback_reason"),
                guidance_mapping.get("fallback_reason"),
            ),
        )


class ContextArchiveRestoreOutcomeEventSnapshot(BaseModel):
    """Structured archive restore allow/block outcome snapshot."""

    timestamp: str = ""
    outcome: str = ""
    reason: str = ""
    estimated_tokens: int = 0
    archive_path: str = ""
    has_archive_path: bool = False
    recorded: bool = False
    is_range_read: bool = False

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ContextArchiveRestoreOutcomeEventSnapshot":
        return cls(
            timestamp=_to_str(raw.get("timestamp")),
            outcome=_to_str(raw.get("outcome")),
            reason=_to_str(raw.get("reason")),
            estimated_tokens=_to_int(raw.get("estimated_tokens")),
            archive_path="",
            has_archive_path=_has_text_or_flag(raw, "archive_path", "has_archive_path"),
            recorded=bool(raw.get("recorded")),
            is_range_read=bool(raw.get("is_range_read")),
        )


class ContextArchiveRestoreResultEventSnapshot(BaseModel):
    """Structured successful archive restore result snapshot."""

    timestamp: str = ""
    archive_path: str = ""
    restore_arg: str = ""
    has_archive_path: bool = False
    has_restore_arg: bool = False
    start_line: int = 0
    end_line: int = 0
    restored_line_count: int = 0
    estimated_tokens: int = 0
    restored_bytes: int = 0
    outcome: str = ""

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ContextArchiveRestoreResultEventSnapshot":
        return cls(
            timestamp=_to_str(raw.get("timestamp")),
            archive_path="",
            restore_arg="",
            has_archive_path=_has_text_or_flag(raw, "archive_path", "has_archive_path"),
            has_restore_arg=_has_text_or_flag(raw, "restore_arg", "has_restore_arg"),
            start_line=_to_int(raw.get("start_line")),
            end_line=_to_int(raw.get("end_line")),
            restored_line_count=_to_int(raw.get("restored_line_count")),
            estimated_tokens=_to_int(raw.get("estimated_tokens")),
            restored_bytes=_to_int(raw.get("restored_bytes")),
            outcome=_to_str(raw.get("outcome")),
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

    @classmethod
    def from_mapping(cls, raw: Mapping[str, object]) -> "ContextCompactionSnapshot":
        compression_events = [
            ContextCompressionEventSnapshot.from_mapping(event)
            for event in _to_mapping_list(raw.get("compression_events"))
        ]
        refetch_events = [
            ContextRefetchEventSnapshot.from_mapping(event)
            for event in _to_mapping_list(raw.get("refetch_events"))
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
            archive_deferred_soft_trimmed_reasons=_to_count_map(
                raw.get("archive_deferred_soft_trimmed_reasons")
            ),
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
        )


def _to_int(value: object) -> int:
    return max(int(value), 0) if isinstance(value, (int, float)) else 0


def _to_signed_int(value: object) -> int:
    return int(value) if isinstance(value, (int, float)) else 0


def _to_float(value: object) -> float:
    return float(value) if isinstance(value, (int, float)) else 0.0


def _to_str(value: object) -> str:
    return str(value) if value is not None else ""


def _first_str(*values: object) -> str:
    for value in values:
        if value is not None:
            text = str(value)
            if text:
                return text
    return ""


def _to_str_list(value: object) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in (_to_str(raw_item) for raw_item in value) if item]


def _to_count_map(value: object) -> dict[str, int]:
    if not isinstance(value, Mapping):
        return {}
    counts: dict[str, int] = {}
    for raw_key, raw_count in value.items():
        if not isinstance(raw_key, str):
            continue
        count = _to_int(raw_count)
        if count > 0:
            counts[raw_key] = count
    return counts


def _to_mapping_list(value: object) -> list[Mapping[str, object]]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, Mapping)]


def _to_dict_list(value: object) -> list[dict[str, object]]:
    return [dict(item) for item in _to_mapping_list(value)]


def _has_text_or_flag(raw: Mapping[str, object], text_key: str, flag_key: str) -> bool:
    return bool(_to_str(raw.get(text_key))) or bool(raw.get(flag_key))


def _count_from_items_or_raw(item_count: int, raw: Mapping[str, object], count_key: str) -> int:
    return max(item_count, _to_int(raw.get(count_key)))


def _content_blind_restore_range_hint(hint: dict[str, object]) -> dict[str, object]:
    return {
        "range_arg": "",
        "reason": _to_str(hint.get("reason")) or "restore_map_range",
        "start_line": _to_int(hint.get("start_line")),
        "end_line": _to_int(hint.get("end_line")),
        "line": _to_int(hint.get("line")),
    }


def _content_blind_content_feature(feature: dict[str, object]) -> dict[str, object]:
    return {
        "feature_type": _to_str(feature.get("feature_type")),
        "count": _to_int(feature.get("count")),
        "values": [],
        "value_count": max(
            len(_to_str_list(feature.get("values"))),
            _to_int(feature.get("value_count")),
        ),
    }


class ContextCompactionTelemetryEnvelope(BaseModel):
    """Detached telemetry payload ready for transport."""
    telemetry_subject: str
    chat_id: str
    timestamp: str
    snapshot: ContextCompactionSnapshot


class ContextCompactionBatchPayload(BaseModel):
    """Batch payload for context compaction telemetry."""
    events: list[ContextCompactionTelemetryEnvelope]


# -----------------------------------------------------------------------------
# Global Baselines
# -----------------------------------------------------------------------------

class SkillBaseline(BaseModel):
    """Global baseline data for a skill."""
    skill_id: str
    global_strategy: str
    confidence_score: float
    adoption_rate: float


class BaselinesResponse(BaseModel):
    """Response containing global skill baselines."""
    baselines: list[SkillBaseline]


# -----------------------------------------------------------------------------
# Health Metrics
# -----------------------------------------------------------------------------

class DLQMetrics(BaseModel):
    """Dead Letter Queue metrics."""
    failed_count: int
    status: str
    error: str | None = None


class HealthMetricsResponse(BaseModel):
    """System metrics exposed to the control plane."""
    dlq: DLQMetrics
