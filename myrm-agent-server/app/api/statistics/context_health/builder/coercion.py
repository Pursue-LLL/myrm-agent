"""[INPUT]
- .context_health_cache / .context_health_restore (POS: cache + restore health layers)

[OUTPUT]
- _max_status, _to_non_negative_int, _to_int, _to_ratio, _to_bool, _to_count_map, _to_string_list, _increment_count, _ensure_count, _restore_counts_from_outcomes, _restore_result_totals_from_events

[POS]
Statistics context-health builder: defensive int/ratio/bool/map coercion and restore-counter aggregation helpers.
"""

from __future__ import annotations

from collections.abc import Mapping

from .models import (
    _STATUS_RANK,
    HealthStatus,
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
