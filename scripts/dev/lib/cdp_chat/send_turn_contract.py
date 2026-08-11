"""SendTurnContract SSOT for chrome_e2e chat submit (R72).

[INPUT]
dev_gate_contract::SEND_TURN_* constants

[OUTPUT]
SendTurnPhase / SendTurnError / resolve_send_turn_profile

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
