"""[INPUT]
- none (imports no other project module)

[OUTPUT]
- _to_int, _to_signed_int, _to_float, _to_str, _first_str, _to_str_list, _to_count_map, _to_mapping_list, _to_dict_list, _has_text_or_flag, _count_from_items_or_raw, _content_blind_restore_range_hint, _content_blind_content_feature

[POS]
Control-plane schemas: defensive coercion helpers shared by the snapshots.
"""

from __future__ import annotations

from collections.abc import Mapping


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
