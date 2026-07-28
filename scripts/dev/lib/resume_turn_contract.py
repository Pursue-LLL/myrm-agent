"""ResumeTurnContract SSOT for chrome_e2e browser takeover resume (R93).

[INPUT]
dev_gate_contract resume-related constants

[OUTPUT]
ResumeTurnPhase / ResumeTurnError / timeout constants

[POS]
Dev Gate layer — UI_ACK (short MUX) + STREAM_CONVERGE (API thread); not product chat logic.
"""

from __future__ import annotations

from enum import Enum

# MUX evaluate budget for UI_ACK only (completeBrowserTakeoverWithResume).
RESUME_UI_ACK_EVALUATE_TIMEOUT_SEC: float = 30.0

# Agent-stream consume budget per STREAM_CONVERGE round (Python thread, not MUX).
RESUME_STREAM_CONVERGE_TIMEOUT_SEC: float = 120.0

# API poll after stream ends without inline DONE marker.
RESUME_DONE_POLL_TIMEOUT_SEC: float = 60.0

# Re-interrupt rounds when HITL fires again during resume SSE.
RESUME_REINTERRUPT_MAX_ROUNDS: int = 4

# Backoff after AgentBusyError 409 before retry.
RESUME_BUSY_BACKOFF_SEC: float = 3.0


class ResumeTurnPhase(str, Enum):
    UI_ACK = "UI_ACK"
    STREAM_CONVERGE = "STREAM_CONVERGE"
    DONE_POLL = "DONE_POLL"


class ResumeTurnError(RuntimeError):
    """Raised when resume turn fails before DONE convergence."""

    def __init__(
        self,
        phase: ResumeTurnPhase,
        message: str,
        *,
        detail: dict[str, object] | None = None,
    ) -> None:
        self.phase = phase
        self.detail = detail or {}
        super().__init__(f"{phase.value}: {message}")
