"""ResumeTurnContract SSOT for chrome_e2e browser takeover resume (R93).

[INPUT]
dev_gate.contract resume-related constants

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

# Parallel-aware API fetch timeout floor when active chrome_e2e ≥ 2.
RESUME_PARALLEL_API_FETCH_TIMEOUT_SEC: float = 30.0
RESUME_DEFAULT_API_FETCH_TIMEOUT_SEC: float = 15.0

# Progress diagnostics during DONE poll (parallel stall visibility).
RESUME_DONE_POLL_PROGRESS_INTERVAL_SEC: float = 30.0


def parallel_active_test_count() -> int:
    try:
        from mux.transport_supervisor import parallel_active_test_count as _count

        return _count()
    except ImportError:
        return 1


def resolve_stream_converge_poll_timeout_sec() -> float:
    """Scale poll-only STREAM_CONVERGE with parallel chrome_e2e load (R95 SSOT)."""
    active = max(1, parallel_active_test_count())
    return RESUME_STREAM_CONVERGE_TIMEOUT_SEC * (1 + active)


def resolve_done_poll_fetch_timeout_sec() -> float:
    if parallel_active_test_count() >= 2:
        return RESUME_PARALLEL_API_FETCH_TIMEOUT_SEC
    return RESUME_DEFAULT_API_FETCH_TIMEOUT_SEC


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
