"""Dev Gate E2E capacity facade — single maintainer entry for parallel backpressure.

[INPUT] dev_gate_contract.py (POS: Dev Gate v2 numeric caps SSOT)
[OUTPUT] E2ECapacitySnapshot: consolidated cap numbers for docs and tooling
[POS] Maintainer-facing summary of LIVE lease + mux admission gates (behavior unchanged).
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Final

from dev_gate_contract import (
    DEFAULT_BOOTSTRAP_SLOTS,
    E2E_MUX_ADMISSION_WAIT_SEC,
    MUX_MAX_CONCURRENT_SESSIONS,
    MUX_SIGNOFF_RESERVED_SLOTS,
    SIGNOFF_LIVE_AGENT_MAX_CONCURRENT,
)

CAPACITY_DOC: Final[str] = (
    "LIVE_AGENT Wave lease cap (wave-lease-owner.sh) and global mux session cap "
    "(e2e_mux_admission.py). User messages: e2e_capacity_messages.py."
)


@dataclass(frozen=True, slots=True)
class E2ECapacitySnapshot:
    live_agent_max: int
    mux_max_sessions: int
    mux_signoff_reserved_slots: int
    mux_admission_wait_sec: int
    bootstrap_slots: int

    @classmethod
    def from_contract(cls) -> E2ECapacitySnapshot:
        return cls(
            live_agent_max=SIGNOFF_LIVE_AGENT_MAX_CONCURRENT,
            mux_max_sessions=MUX_MAX_CONCURRENT_SESSIONS,
            mux_signoff_reserved_slots=MUX_SIGNOFF_RESERVED_SLOTS,
            mux_admission_wait_sec=E2E_MUX_ADMISSION_WAIT_SEC,
            bootstrap_slots=DEFAULT_BOOTSTRAP_SLOTS,
        )

    def dev_mux_cap_during_signoff(self) -> int:
        """Dev chrome_e2e uses full mux cap even when maintainer signoff runs."""
        return self.mux_max_sessions
