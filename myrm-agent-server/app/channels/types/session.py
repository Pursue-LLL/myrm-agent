"""Session identity, reset policy and daily epoch computation.

[INPUT]
(No external dependencies, pure data types and time computation)

[OUTPUT]
- SessionKey: Session identifier
- SessionResetMode, SessionPolicy: Session reset strategy
- compute_daily_epoch(): Daily-granularity time epoch computation

[POS]
Session identity and policy definitions. Provides session-isolated key generation
and time/idle-based auto-reset policies.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import UTC
from enum import StrEnum

_SAFE_CHARS = re.compile(r"[^a-zA-Z0-9_-]")


@dataclass(frozen=True, slots=True)
class SessionKey:
    """Structured session key with all isolation dimensions.

    Encodes user, channel, peer, topic, and agent into a deterministic
    string that serves as the conversation history DB key.  Structured
    fields allow callers to inspect individual dimensions without parsing.

    Format: ``{channel}:{peer_kind}:{peer}[:thread:{thread}][:agent:{agent}]``
    """

    channel: str
    peer_kind: str
    peer_id: str
    thread_id: str | None = None
    agent_id: str | None = None

    def to_str(self) -> str:
        sanitize = _SAFE_CHARS.sub
        parts = [
            sanitize("_", self.channel),
            self.peer_kind,
            sanitize("_", self.peer_id),
        ]
        if self.thread_id:
            parts.append(f"thread:{sanitize('_', self.thread_id)}")
        if self.agent_id:
            parts.append(f"agent:{sanitize('_', self.agent_id)}")
        return ":".join(parts).lower()

    @staticmethod
    def parse(raw: str) -> SessionKey | None:
        """Best-effort parse of a serialised session key."""
        parts = raw.split(":")
        if len(parts) < 3:
            return None
        thread_id: str | None = None
        agent_id: str | None = None
        idx = 3
        while idx < len(parts) - 1:
            tag = parts[idx]
            val = parts[idx + 1]
            if tag == "thread":
                thread_id = val
            elif tag == "agent":
                agent_id = val
            idx += 2
        return SessionKey(
            channel=parts[0],
            peer_kind=parts[1],
            peer_id=parts[2],
            thread_id=thread_id,
            agent_id=agent_id,
        )


class SessionResetMode(StrEnum):
    """How an IM channel session is segmented into separate Chat records."""

    PERSISTENT = "persistent"
    DAILY = "daily"
    IDLE = "idle"


@dataclass(frozen=True, slots=True)
class SessionPolicy:
    """Declarative session reset policy for IM channels.

    Controls when a new Chat record is created for the same IM peer.
    - persistent: one Chat per peer forever (legacy default)
    - daily: new Chat after ``daily_reset_hour`` UTC each day
    - idle: new Chat after ``idle_minutes`` of inactivity
    """

    mode: SessionResetMode = SessionResetMode.DAILY
    daily_reset_hour: int = 4
    idle_minutes: int = 120


def compute_daily_epoch(reset_hour: int) -> str:
    """Pure-computation epoch for daily reset (zero DB cost).

    Returns an ISO date string that stays the same from *reset_hour* today
    until *reset_hour* tomorrow. Messages within the same epoch share a Chat.
    """
    from datetime import datetime, timedelta

    now = datetime.now(tz=UTC)
    cutoff = now.replace(hour=reset_hour, minute=0, second=0, microsecond=0)
    if now < cutoff:
        cutoff -= timedelta(days=1)
    return cutoff.date().isoformat()
