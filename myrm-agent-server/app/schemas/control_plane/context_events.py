"""[INPUT]
- pydantic::BaseModel (POS: schema base)

[OUTPUT]
- ContextCompressionEventSnapshot, ContextRefetchEventSnapshot, ContextArchiveRestoreBlockEventSnapshot, ContextArchiveRestoreOutcomeEventSnapshot, ContextArchiveRestoreResultEventSnapshot

[POS]
Control-plane schemas: context compression/refetch/archive-restore event snapshots.
"""

from __future__ import annotations

from collections.abc import Mapping

from pydantic import BaseModel, Field

from .coercion import (
    _content_blind_content_feature,
    _content_blind_restore_range_hint,
    _count_from_items_or_raw,
    _first_str,
    _has_text_or_flag,
    _to_count_map,
    _to_dict_list,
    _to_float,
    _to_int,
    _to_str,
    _to_str_list,
)


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
    elapsed_ms: int = 0

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
            archive_deferred_soft_trimmed_reasons=_to_count_map(raw.get("archive_deferred_soft_trimmed_reasons")),
            original_tokens=_to_int(raw.get("original_tokens")),
            backoff_applied=bool(raw.get("backoff_applied")),
            backoff_reasons=_to_str_list(raw.get("backoff_reasons")),
            effective_soft_trim_ratio=_to_float(raw.get("effective_soft_trim_ratio")),
            effective_hard_clear_ratio=_to_float(raw.get("effective_hard_clear_ratio")),
            effective_min_prunable_tokens=_to_int(raw.get("effective_min_prunable_tokens")),
            backoff_sample_count=_to_int(raw.get("backoff_sample_count")),
            backoff_bad_signal_count=_to_int(raw.get("backoff_bad_signal_count")),
            backoff_recovery_sample_count=_to_int(raw.get("backoff_recovery_sample_count")),
            elapsed_ms=_to_int(raw.get("elapsed_ms")),
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
        recommended_ranges = _to_str_list(raw.get("recommended_ranges") or guidance_mapping.get("recommended_ranges"))
        restore_range_hints = _to_dict_list(raw.get("restore_range_hints") or guidance_mapping.get("restore_range_hints"))
        content_features = _to_dict_list(raw.get("content_features") or guidance_mapping.get("content_features"))
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
            restore_range_hints=[_content_blind_restore_range_hint(hint) for hint in restore_range_hints[:5]],
            restore_range_hint_count=_count_from_items_or_raw(
                len(restore_range_hints),
                raw,
                "restore_range_hint_count",
            ),
            content_features=[_content_blind_content_feature(feature) for feature in content_features[:8]],
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
