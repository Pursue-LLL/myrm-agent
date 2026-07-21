"""UI data model deep-merge utilities.

[INPUT]
- stdlib only

[OUTPUT]
- deep_merge_ui_data: recursively merge plain dict updates for A2UI bindings

[POS]
Shared merge helper for server stream collector and chat UI artifact persistence.
"""

from __future__ import annotations


def deep_merge_ui_data(
    existing: dict[str, object],
    updates: dict[str, object],
) -> dict[str, object]:
    """Recursively merge plain dict updates; arrays and scalars replace by key."""
    merged = dict(existing)
    for key, value in updates.items():
        existing_value = merged.get(key)
        if isinstance(existing_value, dict) and isinstance(value, dict):
            merged[key] = deep_merge_ui_data(existing_value, value)
        else:
            merged[key] = value
    return merged
