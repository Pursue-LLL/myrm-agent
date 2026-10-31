"""SendTurnContract SSOT for chrome_e2e chat submit (R72).

[INPUT]
dev_gate.contract::SEND_TURN_* constants

[OUTPUT]
SendTurnPhase / SendTurnError / resolve_send_turn_profile / format_api_poll / format_turn_trace

[POS]
Dev Gate layer — UI+API dual-consistency for E2E send; not product chat logic.
"""

from __future__ import annotations

import os
from enum import Enum
from typing import Literal

SendTurnProfile = Literal["live", "read"]


class SendTurnPhase(str, Enum):
    BIND = "BIND"
    ARM = "ARM"
    SUBMIT = "SUBMIT"
    OBSERVE = "OBSERVE"
    SEAL = "SEAL"


class SendTurnError(RuntimeError):
    """Raised when a send turn fails before SEAL."""

    def __init__(
        self,
        phase: SendTurnPhase,
        message: str,
        *,
        detail: dict[str, object] | None = None,
    ) -> None:
        self.phase = phase
        self.detail = detail or {}
        super().__init__(f"{phase.value}: {message}")


def resolve_send_turn_profile() -> SendTurnProfile:
    lane = os.environ.get("MYRM_E2E_LANE", "").strip().upper()
    return "read" if lane == "READ" else "live"


def is_live_send_turn_profile() -> bool:
    return resolve_send_turn_profile() == "live"


def format_api_poll(debug: dict[str, object]) -> str:
    """Log fragment for the page's message-poll health, empty when the page reported none.

    `apiUsers=0` alone cannot tell "the user row is not persisted" from "the API does not
    know the chat yet" (HTTP 404, normal for a new chat until its first assistant output) or
    "the poll could not be answered"; the page counts each per turn. The slowest poll shows
    how close real answers run to the page's per-poll cap.
    """
    poll = debug.get("apiPoll")
    if not isinstance(poll, dict):
        return ""
    last = poll.get("lastFailure") or "-"
    return (
        f" pollNotFound={poll.get('notFound')}"
        f" pollFailed={poll.get('failures')}/{poll.get('polls')}"
        f" pollLastFailure={last} pollSlowest={poll.get('slowestMs')}ms"
    )


_TRACE_OUTCOME_MAX_CHARS = 80


def _is_number(value: object) -> bool:
    return isinstance(value, (int, float)) and not isinstance(value, bool)


def _one_token(text: str) -> str:
    return "_".join(text.split())


def _format_trace_entry(entry: object) -> str | None:
    if not isinstance(entry, dict):
        return None
    event_type, first_ms, last_ms = (
        entry.get("type"),
        entry.get("atMs"),
        entry.get("lastAtMs"),
    )
    if not isinstance(event_type, str) or not _is_number(first_ms):
        return None
    count = entry.get("count")
    times = f"{first_ms / 1000:.1f}"
    if _is_number(last_ms) and last_ms != first_ms:
        times += f"-{last_ms / 1000:.1f}"
    repeat = f"*{count}" if isinstance(count, int) and count > 1 else ""
    return f"{_one_token(event_type)}{repeat}@{times}s"


def format_turn_trace(debug: dict[str, object]) -> str:
    """Log fragment for what the turn did, empty when the page reported none.

    The page's `streaming` flag cannot tell a turn that is still starting from one that ended
    without output (its stream watchdog turns the flag off 3.5 s after the last event while the
    model still works). The SSE events the page received, with their times in seconds after the
    hand-over, and how the send promise ended, can: `settle=pending` means the request had not
    ended when the page gave up. A malformed report is cut down, never raised: this runs while
    another failure is being reported.
    """
    trace = debug.get("turnTrace")
    if not isinstance(trace, dict):
        return ""
    raw_events = trace.get("events")
    entries = [
        text
        for text in map(
            _format_trace_entry, raw_events if isinstance(raw_events, list) else []
        )
        if text is not None
    ]
    dropped = trace.get("dropped")
    dropped_text = (
        f" dropped={dropped}" if isinstance(dropped, int) and dropped > 0 else ""
    )
    settle = trace.get("settle")
    outcome = settle.get("outcome") if isinstance(settle, dict) else None
    settled_ms = settle.get("atMs") if isinstance(settle, dict) else None
    if isinstance(outcome, str) and _is_number(settled_ms):
        settle_text = (
            f"{_one_token(outcome[:_TRACE_OUTCOME_MAX_CHARS])}@{settled_ms / 1000:.1f}s"
        )
    else:
        settle_text = "pending"
    return f" trace=[{' '.join(entries)}]{dropped_text} settle={settle_text}"
