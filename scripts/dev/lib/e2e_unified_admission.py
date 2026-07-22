"""Unified E2E Admission (UEA v3) — contract SSOT for formal chrome_e2e.

[INPUT]
- dev_gate_contract.py (POS: Dev Gate v2 parallel cap / unified wait SSOT)

[OUTPUT]
- E2E_UNIFIED_WAIT_SEC, LIVE_SHPOIB_MAX_CONCURRENT, LIVE_SHARED_HOT_MAX_CONCURRENT constants
- Profile resolution lives in scripts/dev/resolve_e2e_session_profile.py (test.sh entry)

[POS]
UEA v3 contract module. Shell orchestration: e2e_bootstrap.sh (stream lock) + test.sh (ordering).
"""

from __future__ import annotations

from dev_gate_contract import (  # noqa: E402
    E2E_UNIFIED_WAIT_SEC,
    LIVE_SHARED_HOT_MAX_CONCURRENT,
    LIVE_SHPOIB_MAX_CONCURRENT,
)

__all__ = [
    "E2E_UNIFIED_WAIT_SEC",
    "LIVE_SHARED_HOT_MAX_CONCURRENT",
    "LIVE_SHPOIB_MAX_CONCURRENT",
]
