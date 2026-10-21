"""Restore-block health event normalization.

[INPUT]
- collections.abc::Mapping (POS: runtime metric payload shape checks)
- dataclasses::dataclass (POS: immutable API DTOs)

[OUTPUT]
- RestoreBlockEventHealth: UI-facing restore-block event DTO.
- to_restore_block_events: Bounded sanitizer for archive restore block events.

[POS]
Statistics API restore-health normalization layer. Converts raw task metrics into
small, typed payloads before the main context-health aggregate is serialized.
"""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class RestoreRangeHintHealth:
    range_arg: str
    reason: str
    start_line: int
    end_line: int
    line: int


@dataclass(frozen=True, slots=True)
class RestoreContentFeatureHealth:
    feature_type: str
    count: int
    values: list[str]


@dataclass(frozen=True, slots=True)
class RestoreBlockEventHealth:
    reason: str
    estimated_tokens: int
    archive_path: str
    message: str
    suggested_action: str
    reason_label_key: str
    severity: str
    primary_restore_arg: str
    recommended_ranges: list[str]
    restore_range_hints: list[RestoreRangeHintHealth]
    content_features: list[RestoreContentFeatureHealth]
    guidance_source: str
    fallback_reason: str
    timestamp: str


def to_restore_block_events(value: object) -> list[RestoreBlockEventHealth]:
    if not isinstance(value, list):
        return []
    events: list[RestoreBlockEventHealth] = []
    for raw_event in value[-5:]:
        if not isinstance(raw_event, Mapping):
            continue
        guidance = raw_event.get("guidance")
        guidance_mapping = guidance if isinstance(guidance, Mapping) else {}
        events.append(
            RestoreBlockEventHealth(
                reason=_to_str(raw_event.get("reason")),
                estimated_tokens=_to_non_negative_int(raw_event.get("estimated_tokens")),
                archive_path=_to_str(raw_event.get("archive_path")),
                message=_to_str(raw_event.get("message")),
                suggested_action=_to_str(raw_event.get("suggested_action")),
                reason_label_key=_first_str(
                    raw_event.get("reason_label_key"),
                    guidance_mapping.get("reason_label_key"),
                ),
                severity=_first_str(
                    raw_event.get("severity"),
                    guidance_mapping.get("severity"),
                ),
                primary_restore_arg=_first_str(
                    raw_event.get("primary_restore_arg"),
                    guidance_mapping.get("primary_restore_arg"),
                ),
                recommended_ranges=_to_str_list(
                    raw_event.get("recommended_ranges") or guidance_mapping.get("recommended_ranges")
                ),
                restore_range_hints=_to_restore_range_hints(
                    raw_event.get("restore_range_hints") or guidance_mapping.get("restore_range_hints")
                ),
                content_features=_to_restore_content_features(
                    raw_event.get("content_features") or guidance_mapping.get("content_features")
                ),
                guidance_source=_first_str(
                    raw_event.get("guidance_source"),
                    guidance_mapping.get("guidance_source"),
                ),
                fallback_reason=_first_str(
                    raw_event.get("fallback_reason"),
                    guidance_mapping.get("fallback_reason"),
                ),
                timestamp=_to_str(raw_event.get("timestamp")),
            )
        )
    return events


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


def _to_non_negative_int(value: object) -> int:
    return max(int(value), 0) if isinstance(value, (int, float)) else 0


def _to_restore_range_hints(value: object) -> list[RestoreRangeHintHealth]:
    if not isinstance(value, list):
        return []
    hints: list[RestoreRangeHintHealth] = []
    for raw_hint in value[:5]:
        if not isinstance(raw_hint, Mapping):
            continue
        range_arg = _to_str(raw_hint.get("range_arg"))
        if not range_arg:
            continue
        hints.append(
            RestoreRangeHintHealth(
                range_arg=range_arg,
                reason=_to_str(raw_hint.get("reason")) or "restore_map_range",
                start_line=_to_non_negative_int(raw_hint.get("start_line")),
                end_line=_to_non_negative_int(raw_hint.get("end_line")),
                line=_to_non_negative_int(raw_hint.get("line")),
            )
        )
    return hints


def _to_restore_content_features(value: object) -> list[RestoreContentFeatureHealth]:
    if not isinstance(value, list):
        return []
    features: list[RestoreContentFeatureHealth] = []
    for raw_feature in value[:8]:
        if not isinstance(raw_feature, Mapping):
            continue
        feature_type = _to_str(raw_feature.get("feature_type"))
        if not feature_type:
            continue
        features.append(
            RestoreContentFeatureHealth(
                feature_type=feature_type,
                count=_to_non_negative_int(raw_feature.get("count")),
                values=_to_str_list(raw_feature.get("values"))[:8],
            )
        )
    return features


__all__ = [
    "RestoreBlockEventHealth",
    "RestoreContentFeatureHealth",
    "RestoreRangeHintHealth",
    "to_restore_block_events",
]
