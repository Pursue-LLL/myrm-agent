"""Proactive follow-up settings resolution.

[INPUT]
- (none)

[OUTPUT]
- resolve_memory_enabled: Whether proactive memory features are active for a user.
- resolve_conversation_search_enabled: Whether conversation_search_tool is enabled globally.

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


def resolve_conversation_search_enabled(personal_settings: dict[str, object] | None) -> bool:
    """Return True when memory is on and user opted into conversation_search tool."""
    if not resolve_memory_enabled(personal_settings):
        return False
    raw = personal_settings.get("memoryEnableConversationSearch")
    return raw is True
