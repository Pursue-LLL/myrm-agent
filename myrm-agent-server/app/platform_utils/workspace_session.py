"""Chat workspace session id normalization for sandbox volume lookup.

[INPUT]
- Raw chat_id from frontend Goal API or agent runtime session keys

[OUTPUT]
- to_workspace_session_id: Normalize to ``chat_{chat_id}`` workspace session key

[POS]
SSOT for mapping chat identifiers to code-execution workspace session ids.
Aligns with chat_crud.ensure_default_workspace_dir and general_agent session ids.
"""

from __future__ import annotations

CHAT_SESSION_PREFIX = "chat_"


def to_workspace_session_id(chat_or_session_id: str) -> str:
    """Return the workspace session key used by create_workspace_service."""
    normalized = chat_or_session_id.strip()
    if not normalized:
        return normalized
    if normalized.startswith(CHAT_SESSION_PREFIX):
        return normalized
    return f"{CHAT_SESSION_PREFIX}{normalized}"


def to_rest_chat_id(session_or_chat_id: str | None) -> str | None:
    """Strip repeated ``chat_`` prefixes so REST uuid aligns with harness session ids."""
    if not session_or_chat_id:
        return None
    normalized = session_or_chat_id.strip()
    while normalized.startswith(CHAT_SESSION_PREFIX):
        normalized = normalized.removeprefix(CHAT_SESSION_PREFIX)
    return normalized or None


__all__ = ["CHAT_SESSION_PREFIX", "to_rest_chat_id", "to_workspace_session_id"]
