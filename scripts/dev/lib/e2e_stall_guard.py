"""Unified stall tripwires for parallel Chrome E2E (R96-B6 SSOT).

[INPUT]
- e2e_session_snapshot nodeStartedMonotonic / currentNode
- dev_gate_contract NODE_STUCK_FAIL_FAST_SEC + TRANSPORT_STALL_NODE_PREFIXES

[OUTPUT]
- node_stuck_reason_from_snapshot for hung reap + e2e-context FAIL_FAST
- assert_transport_node_not_stuck for open_mcp_page transport loops

[POS]
Dev Gate layer — complements progress_stale (heartbeat) with semantic node stuck.
"""

from __future__ import annotations

import time

from dev_gate_contract import (
    E2E_NODE_STUCK_TOKEN,
    MUX_RECLAIM_STALL_TOKEN,
    NODE_STUCK_FAIL_FAST_SEC,
    TRANSPORT_STALL_NODE_PREFIXES,
)


def is_transport_stall_node(node: str) -> bool:
    text = node.strip()
    if not text:
        return False
    lowered = text.lower()
    return any(
        lowered.startswith(prefix.lower()) for prefix in TRANSPORT_STALL_NODE_PREFIXES
    )


def node_started_from_snapshot(snapshot: dict[str, object]) -> float | None:
    raw = snapshot.get("nodeStartedMonotonic")
    if raw is None:
        return None
    try:
        return float(raw)
    except (TypeError, ValueError):
        return None


def node_elapsed_from_snapshot(snapshot: dict[str, object]) -> float | None:
    node = str(snapshot.get("currentNode") or "").strip()
    if not node:
        return None
    started = node_started_from_snapshot(snapshot)
    if started is None:
        progress_at = snapshot.get("progressAtMonotonic")
        if progress_at is None:
            return None
        try:
            started = float(progress_at)
        except (TypeError, ValueError):
            return None
    return max(0.0, time.monotonic() - started)


def node_stuck_reason_from_snapshot(snapshot: dict[str, object]) -> str | None:
    node = str(snapshot.get("currentNode") or "").strip()
    if not is_transport_stall_node(node):
        return None
    phase = str(snapshot.get("phase") or "").strip().lower()
    if phase != "body":
        return None
    elapsed = node_elapsed_from_snapshot(snapshot)
    if elapsed is None:
        return None
    stall_cap = _transport_stall_cap_sec()
    if elapsed >= stall_cap:
        return (
            f"{E2E_NODE_STUCK_TOKEN}: node={node!r} "
            f"node_elapsed={int(elapsed)}s>={int(stall_cap)}s"
        )
    return None


def _transport_stall_cap_sec() -> float:
    """Scale transport node stall cap under parallel mux load (R122-B11/R127)."""
    cap = float(NODE_STUCK_FAIL_FAST_SEC)
    peers = 0
    try:
        from mux_load import snapshot_mux_load

        load = snapshot_mux_load()
        peers = max(int(load.wave_leases), int(load.mux_contexts))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        peers = 0
    if peers < 2:
        try:
            from transport_supervisor import parallel_mux_peer_count

            peers = parallel_mux_peer_count()
        except (ImportError, OSError, RuntimeError, TypeError, ValueError):
            peers = 0
    if peers >= 2:
        return min(cap + peers * 22.0, 300.0)
    return cap


def transport_stall_cap_sec() -> float:
    """Public SSOT for scaled transport node stall cap."""
    return _transport_stall_cap_sec()


def assert_transport_node_not_stuck(
    *,
    current_node: str,
    node_started: float,
    stall_cap: float | None = None,
) -> None:
    """Fail-fast when a transport node exceeds stall cap (scaled under parallel)."""
    if not is_transport_stall_node(current_node):
        return
    resolved_cap = (
        float(stall_cap) if stall_cap is not None else _transport_stall_cap_sec()
    )
    elapsed = time.monotonic() - node_started
    if elapsed >= resolved_cap:
        raise RuntimeError(
            f"{MUX_RECLAIM_STALL_TOKEN}: {current_node} blocked for {elapsed:.1f}s "
            f"(cap={resolved_cap:.0f}s); recover mux and retry"
        )
