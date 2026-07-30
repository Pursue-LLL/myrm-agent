"""Agent scope key helpers for per-agent wiki source sync config/state.

[OUTPUT]
- normalize_agent_scope / scope_storage_key

[POS]
SSOT for mapping Settings Wiki agent vault scope to UserConfig nested keys.
"""

from __future__ import annotations

DEFAULT_AGENT_SCOPE = "__default__"


def normalize_agent_scope(agent_id: str | None) -> str:
    trimmed = (agent_id or "").strip()
    return trimmed or DEFAULT_AGENT_SCOPE
