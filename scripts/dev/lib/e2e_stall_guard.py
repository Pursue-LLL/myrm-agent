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


def _resolve_transport_stall_cap_sec(*, current_node: str = "") -> float:
    """Resolve stall cap for hung-reap / e2e-context (signoff open_mcp_page uses R169 cap)."""
    try:
        from dev_gate_contract import resolve_transport_stall_cap_sec

        return resolve_transport_stall_cap_sec(current_node=current_node)
    except ImportError:
        pass
    return _transport_stall_cap_sec()


def node_stuck_reason_from_snapshot(snapshot: dict[str, object]) -> str | None:
    node = str(snapshot.get("currentNode") or "").strip()
    if not is_transport_stall_node(node):
        return None
    phase = str(snapshot.get("phase") or "").strip().lower()
    elapsed = node_elapsed_from_snapshot(snapshot)
    if elapsed is None:
        return None
    if phase == "bootstrap":
        from dev_gate_contract import (
            E2E_BOOTSTRAP_OPEN_MCP_EXCEEDED_TOKEN,
        )  # noqa: PLC0415

        try:
            from transport_supervisor import bootstrap_wall_cap_sec
        except ImportError:
            bootstrap_wall_cap_sec = lambda **kwargs: 240  # noqa: E731
        cap = float(bootstrap_wall_cap_sec(pessimistic=True))
        try:
            from dev_gate_contract import (
                is_e2e_signoff_runtime,
            )

            if is_e2e_signoff_runtime():
                from dev_gate_contract import signoff_bootstrap_transport_stall_cap_sec

                cap = max(cap, signoff_bootstrap_transport_stall_cap_sec())
        except ImportError:
            pass
        if elapsed >= cap:
            return (
                f"{E2E_BOOTSTRAP_OPEN_MCP_EXCEEDED_TOKEN}: node={node!r} "
                f"node_elapsed={int(elapsed)}s>={int(cap)}s"
            )
        return None
    if phase != "body":
        return None
    from dev_gate_contract import resolve_transport_stall_cap_sec

    stall_cap = resolve_transport_stall_cap_sec(current_node=node)
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


def parallel_active_test_node_stuck_fail_fast(row: dict[str, object]) -> bool:
    """True when active_tests[] row should trigger e2e-context FAIL_FAST.

    Delegates to hung-reap ``_parallel_node_stuck_reason`` so readiness and reap
    share bootstrap/admit/body wall defer SSOT.
    """
    from e2e_session_registry import LiveE2ESessionRow
    from e2e_stale_lease_reap import _parallel_node_stuck_reason

    pid = row.get("pid")
    node_elapsed = row.get("node_elapsed_sec")
    current_node = row.get("current_node")
    if not isinstance(pid, int):
        return False
    if not isinstance(node_elapsed, (int, float)):
        return False
    if not isinstance(current_node, str) or not current_node.strip():
        return False
    wall = str(row.get("wall_phase") or "").strip() or None
    elapsed_raw = row.get("elapsed_sec")
    elapsed_sec = float(elapsed_raw) if isinstance(elapsed_raw, (int, float)) else 0.0
    session = LiveE2ESessionRow(
        pid=pid,
        test_id=str(row.get("test_id") or ""),
        elapsed_sec=elapsed_sec,
        state=str(row.get("state") or ""),
        phase=str(wall or row.get("phase") or ""),
        current_node=current_node,
        wall_phase=wall,
        admit_elapsed_sec=(
            float(row["admit_elapsed_sec"])
            if isinstance(row.get("admit_elapsed_sec"), (int, float))
            else None
        ),
        body_elapsed_sec=(
            float(row["body_elapsed_sec"])
            if isinstance(row.get("body_elapsed_sec"), (int, float))
            else None
        ),
        node_elapsed_sec=float(node_elapsed),
    )
    return _parallel_node_stuck_reason(session) is not None


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
        token = MUX_RECLAIM_STALL_TOKEN
        try:
            from e2e_session_lifecycle import current_phase

            if current_phase() == "bootstrap":
                from dev_gate_contract import E2E_BOOTSTRAP_OPEN_MCP_EXCEEDED_TOKEN

                token = E2E_BOOTSTRAP_OPEN_MCP_EXCEEDED_TOKEN
        except ImportError:
            pass
        raise RuntimeError(
            f"{token}: {current_node} blocked for {elapsed:.1f}s "
            f"(cap={resolved_cap:.0f}s); recover mux and retry"
        )
