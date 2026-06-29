"""Proactive follow-up settings resolution.

[INPUT]
- (none)

[OUTPUT]
- resolve_memory_enabled: Whether proactive memory features are active for a user.

[POS]
Single source of truth for enableMemory interpretation in server cron, channels,
and voice paths. Matches schema default in app.schemas.config (False when unset).
"""

from __future__ import annotations


def resolve_memory_enabled(personal_settings: dict[str, object] | None) -> bool:
    """Return True only when the user explicitly enabled memory."""
    if not personal_settings:
        return False
    raw = personal_settings.get("enableMemory")
    return raw is True
