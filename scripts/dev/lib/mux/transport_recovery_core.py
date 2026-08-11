"""Transport Recovery State Machine (TRSM) — SSOT for mux orphan/recover paths.

Single resolver for chrome_mcp_client abandon/recover/teardown decisions.
See temp-docs/repair/DEV_GATE_CHROME_MCP_ROADMAP.md §55.
"""

from __future__ import annotations

from enum import Enum
from typing import Final

TRSM_MODE_TOKEN: Final[str] = "E2E_TRSM_MODE"


class TransportRecoveryMode(str, Enum):
    """Explicit recovery strategy; avoids scattered teardown/recover branches."""

    SOLO_FULL = "solo_full"
    PARALLEL_PAGE_RECLAIM = "parallel_page_reclaim"
    PARALLEL_LOCAL_RESPAWN = "parallel_local_respawn"


def resolve_transport_recovery_mode(
    *,
    parallel_peers: int,
    shim_alive: bool,
) -> TransportRecoveryMode:
    """Pick recovery mode from peer load and local shim liveness."""
    if parallel_peers <= 1:
        return TransportRecoveryMode.SOLO_FULL
    if shim_alive:
        return TransportRecoveryMode.PARALLEL_PAGE_RECLAIM
    return TransportRecoveryMode.PARALLEL_LOCAL_RESPAWN


def should_skip_global_teardown(mode: TransportRecoveryMode) -> bool:
    """Global shim teardown harms peer mux sessions only when peers>1 and shim up.

    R121: callers may pass ``cdp_drift=True`` to ``abandon_inflight_requests`` for
    scoped mux attach restart instead of skipping all teardown under parallel reclaim.
    """
    return mode == TransportRecoveryMode.PARALLEL_PAGE_RECLAIM
