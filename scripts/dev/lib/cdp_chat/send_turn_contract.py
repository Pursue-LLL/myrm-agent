"""SendTurnContract SSOT for chrome_e2e chat submit (R72).

[INPUT]
dev_gate.contract::SEND_TURN_* constants

[OUTPUT]
SendTurnPhase / SendTurnError / resolve_send_turn_profile / format_api_poll

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
