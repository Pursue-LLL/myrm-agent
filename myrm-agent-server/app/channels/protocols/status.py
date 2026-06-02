"""Status command handler protocol — business-layer injection for /status.

[INPUT]
- (none — leaf module)

[OUTPUT]
- SessionStatus: Frozen dataclass describing current session state
- StatusProvider: Protocol for querying session status from business layer

[POS]
Business-layer handler protocol for the /status slash command. Framework
provides runtime state (agent running, queue depth, yolo mode) and delegates
session metadata retrieval (session_id, title, tokens, model, timestamps)
to the business layer via this protocol.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Protocol, runtime_checkable


@dataclass(frozen=True, slots=True)
class SessionStatus:
    """Session metadata returned by the business layer for /status display."""

    session_id: str
    title: str | None = None
    total_tokens: int = 0
    model_name: str | None = None
    created_at: str | None = None
    last_activity: str | None = None


@runtime_checkable
class StatusProvider(Protocol):
    """Protocol for querying session status. Implemented by the business layer."""

    async def get_session_status(self, channel: str, peer_id: str) -> SessionStatus | None:
        """Return session metadata for the given channel+peer, or None if no session exists."""
        ...
