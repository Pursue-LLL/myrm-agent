"""Service layer types and DTOs for session-scoped loop scheduling.

[INPUT]
- myrm_agent_harness.runtime.loop::(LoopConfig, LoopState, LoopStatus, LoopStopReason)

[OUTPUT]
- SessionLoopStatusDTO: payload for REST and SSE status delivery
- SessionLoopStartResult: outcome of loop initialization

[POS]
Server service layer. Encapsulates serializable payloads for UI and API clients.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from myrm_agent_harness.runtime.loop import (
    LoopMode,
    LoopState,
    LoopStatus,
    format_interval,
)


@dataclass(frozen=True)
class SessionLoopStatusDTO:
    """Serializable status payload for UI components and SSE updates."""

    chat_id: str
    is_active: bool
    status: str
    mode: str
    prompt: str
    current_delay_seconds: float
    current_delay_human: str
    next_due_in_seconds: float
    next_due_in_human: str
    ticks_fired: int
    times_limit: int
    until_condition: str
    consecutive_unchanged: int
    last_stop_reason: str | None
    paused_reason: str | None

    def to_dict(self) -> dict[str, Any]:
        """Convert DTO to dictionary representation."""
        return {
            "chat_id": self.chat_id,
            "is_active": self.is_active,
            "status": self.status,
            "mode": self.mode,
            "prompt": self.prompt,
            "current_delay_seconds": self.current_delay_seconds,
            "current_delay_human": self.current_delay_human,
            "next_due_in_seconds": self.next_due_in_seconds,
            "next_due_in_human": self.next_due_in_human,
            "ticks_fired": self.ticks_fired,
            "times_limit": self.times_limit,
            "until_condition": self.until_condition,
            "consecutive_unchanged": self.consecutive_unchanged,
            "last_stop_reason": self.last_stop_reason,
            "paused_reason": self.paused_reason,
        }

    @classmethod
    def from_loop_state(cls, state: LoopState, now: float) -> SessionLoopStatusDTO:
        """Build status DTO from live LoopState and current timestamp."""
        remaining = max(0.0, state.next_due_at - now) if state.status == LoopStatus.ACTIVE else 0.0
        remaining_human = "due now" if remaining <= 0 and state.status == LoopStatus.ACTIVE else format_interval(remaining)

        return cls(
            chat_id=state.session_id,
            is_active=state.status == LoopStatus.ACTIVE,
            status=state.status.value,
            mode=state.mode.value,
            prompt=state.prompt,
            current_delay_seconds=state.current_delay if state.mode == LoopMode.SELF_PACED else state.interval_seconds,
            current_delay_human=format_interval(state.current_delay if state.mode == LoopMode.SELF_PACED else state.interval_seconds),
            next_due_in_seconds=remaining,
            next_due_in_human=remaining_human,
            ticks_fired=state.ticks_fired,
            times_limit=state.times,
            until_condition=state.until,
            consecutive_unchanged=state.consecutive_unchanged,
            last_stop_reason=state.last_stop_reason.value if state.last_stop_reason else None,
            paused_reason=state.paused_reason,
        )


@dataclass(frozen=True)
class SessionLoopStartResult:
    """Outcome of attempting to start or replace a loop."""

    success: bool
    status: SessionLoopStatusDTO | None = None
    error: str | None = None
