"""Deprecated compatibility redirect to app.services.chat.context_bomb_guard.

[INPUT]
- app.services.chat.context_bomb_guard

[OUTPUT]
- ContextBombDefenseService, SpilloverPayloadResult

[POS]
Compatibility shim preserving external references.
"""

from __future__ import annotations

from app.services.chat.context_bomb_guard import (
    MESSAGE_MAX_CHARS,
    SPILLED_FILE_TTL_SECONDS,
    ContextBombDefenseService,
    SpilloverPayloadResult,
    get_context_bomb_defense_service,
)

__all__ = [
    "MESSAGE_MAX_CHARS",
    "SPILLED_FILE_TTL_SECONDS",
    "ContextBombDefenseService",
    "SpilloverPayloadResult",
    "get_context_bomb_defense_service",
]
