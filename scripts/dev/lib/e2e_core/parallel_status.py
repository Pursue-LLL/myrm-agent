"""Parallel E2E runtime status probes: snapshot, queue state, capacity headroom.

[INPUT]
- tests.support.e2e_parallel_snapshot (POS: live process/flock snapshot)
- dev_gate_status (POS: Dev Gate registry status)
- dev_gate_contract (POS: Dev Gate constants — MUX_COLD_ATTACH_SLOTS)
- e2e_lease_liveness (POS: WaveLeaseCounts type)

[OUTPUT]
- load_parallel_runtime_snapshot: live E2E process snapshot (dict + human lines)
- safe_active_test_count: fail-closed active test count
- resolve_cap_headroom_active_test_count: merge registry + leases + dev_gate (observability)
- cap_headroom_fields: dict of capacity/headroom metrics
- format_cap_headroom_human: one-line cap status for Agent
- format_queue_human: optional queue explanation when backpressure active
- compute_queue_state: (blocked, reasons) tuple

[POS]
Parallel runtime status plane — observe capacity + queue state without
touching API resolution or context probe logic.  Used by e2e_api_verify
for Agent-facing e2e-context output.
"""

from __future__ import annotations

import os
import sys
import time
from pathlib import Path
from typing import Final

_MONOREPO_ROOT: Final[Path] = Path(__file__).resolve().parents[5]


def _server_tests_support_dir() -> Path:
    return _MONOREPO_ROOT / "myrm-agent" / "myrm-agent-server"


def load_parallel_runtime_snapshot() -> tuple[dict[str, object], list[str]]:
    """SSOT parallel chrome_e2e processes + flock holders for Agent diagnosis."""
    support_dir = _server_tests_support_dir()
    inserted = False
    support_text = str(support_dir)
    if support_text not in sys.path:
        sys.path.insert(0, support_text)
        inserted = True
    try:
        from tests.support.e2e_parallel_snapshot import (
            format_parallel_snapshot_human,
            parallel_snapshot_to_dict,
            snapshot_live_e2e_processes,
        )

        snapshot = snapshot_live_e2e_processes()
        return parallel_snapshot_to_dict(snapshot), format_parallel_snapshot_human(
            snapshot
        )
    except (ImportError, OSError, RuntimeError, TypeError, ValueError) as exc:
        fallback: dict[str, object] = {
            "agent_stream_lock": None,
            "desktop_approval_lock": None,
            "active_tests": [],
            "active_test_count": "UNKNOWN",
            "snapshot_error": str(exc),
            "snapshot_unavailable": True,
        }
        return fallback, [
            "E2E_PARALLEL_ACTIVE: UNAVAILABLE (fail-closed: treat as non-zero)",
            f"E2E_PARALLEL_SNAPSHOT_ERROR={exc}",
        ]
    finally:
        if inserted:
            sys.path.remove(support_text)


def load_parallel_runtime_snapshot_lite() -> tuple[dict[str, object], list[str]]:
    """Fast parallel snapshot for e2e-context json under load (skip pgrep/session scan)."""
    try:
        from dev_gate.status import dev_gate_status
        from e2e_core.lease_liveness import (
            load_wave_snapshot,
            wave_lease_counts,
        )

        dev_gate = dev_gate_status()
        wave = load_wave_snapshot()
        counts = wave_lease_counts(wave)
        shared = int(dev_gate.get("shared_active", 0))
        private = int(dev_gate.get("private_active", 0))
        active = max(counts.effective_total, shared + private)
        sessions_raw = dev_gate.get("sessions", [])
        sessions = sessions_raw if isinstance(sessions_raw, list) else []
        now = time.time()
        active_tests: list[dict[str, object]] = []
        admit_count = 0
        body_count = 0
        for raw in sessions:
            if not isinstance(raw, dict):
                continue
            state = str(raw.get("state", ""))
            submitted_at = float(raw.get("submitted_at", 0.0) or 0.0)
            phase_started_at = float(raw.get("phase_started_at", 0.0) or 0.0)
            wall_phase = "body" if state in {"BODY", "TEARDOWN"} else "bootstrap"
            if state in {"SUBMITTED", "PRIVATE_ADMIT", "PREPARING", "PAGE_OPEN"}:
                admit_count += 1
            if state in {"BODY", "TEARDOWN"}:
                body_count += 1
            active_tests.append(
                {
                    "pid": int(raw.get("owner_pid", 0) or 0),
                    "test_id": str(raw.get("test_node_id", "")),
                    "elapsed_sec": max(0.0, now - submitted_at),
                    "state": state,
                    "current_node": str(raw.get("current_node", "")) or None,
                    "wall_phase": wall_phase,
                    "admit_elapsed_sec": (
                        max(0.0, now - submitted_at) if wall_phase == "bootstrap" else None
                    ),
                    "body_elapsed_sec": (
                        max(0.0, now - phase_started_at) if wall_phase == "body" else None
                    ),
                    "node_elapsed_sec": max(
                        0.0, now - float(raw.get("node_started_at", 0.0) or now)
                    ),
                    "batch_mode": False,
                }
            )
        payload: dict[str, object] = {
            "agent_stream_lock": None,
            "desktop_approval_lock": None,
            "active_tests": active_tests,
            "active_test_count": active,
            "admit_active_count": admit_count,
            "body_active_count": body_count,
            "snapshot_lite": True,
            "snapshot_lite_source": "dev_gate+wave",
        }
        return payload, [
            (
                "E2E_PARALLEL_ACTIVE: "
                f"lite_count={active} (full session scan skipped under parallel load)"
            )
        ]
    except (ImportError, OSError, OverflowError, RuntimeError, TypeError, ValueError):
        return load_parallel_runtime_snapshot()


def should_use_lite_parallel_snapshot() -> bool:
    """Auto-lite when parallel pressure is active unless explicitly disabled."""
    raw = os.environ.get("MYRM_E2E_CONTEXT_LITE", "").strip().lower()
    if raw in {"0", "false", "no"}:
        return False
    if raw in {"1", "true", "yes"}:
        return True
    try:
        from e2e_core.peer_count_ssot import parallel_active_test_count_ssot

        return parallel_active_test_count_ssot() > 0
    except ImportError:
        return False


def resolve_parallel_runtime_snapshot() -> tuple[dict[str, object], list[str]]:
    if should_use_lite_parallel_snapshot():
        return load_parallel_runtime_snapshot_lite()
    return load_parallel_runtime_snapshot()


def safe_active_test_count(snapshot: dict[str, object]) -> int:
    """Extract active_test_count; fail-closed returns 1 when UNKNOWN/invalid.

    P0-A: snapshot unavailable must never report 0 (which would trigger
    restart/heal while parallel sessions are actually running).
    """
    raw = snapshot.get("active_test_count", 0)
    if isinstance(raw, int):
        return raw
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return 1


def resolve_cap_headroom_active_test_count(
    snapshot: dict[str, object],
    *,
    wave_leases_effective: int,
    dev_gate: dict[str, object],
) -> tuple[int, bool]:
    """Merge session registry, peer SSOT, Dev Gate, and wave leases for Agent headroom.

    Returns (resolved_count, observability_mismatch). Mismatch is True when parallel
    signals (leases, dev_gate activity, live pytest peers) exist but the session
    registry reports zero — the historical active_test_count=0 drift case.
    """
    registry_raw = snapshot.get("active_test_count", 0)
    if isinstance(registry_raw, int):
        registry_count = registry_raw
    elif isinstance(registry_raw, str) and registry_raw.isdigit():
        registry_count = int(registry_raw)
    else:
        registry_count = safe_active_test_count(snapshot)

    admit_count = int(snapshot.get("admit_active_count", 0) or 0)
    body_count = int(snapshot.get("body_active_count", 0) or 0)
    active_tests_raw = snapshot.get("active_tests")
    listed = len(active_tests_raw) if isinstance(active_tests_raw, list) else 0
    registry_live = max(registry_count, admit_count, body_count, listed)

    pytest_peers = 0
    try:
        from e2e_core.peer_count_ssot import chrome_e2e_pytest_peer_count

        pytest_peers = chrome_e2e_pytest_peer_count()
    except ImportError:
        pytest_peers = 0

    dev_gate_activity = int(dev_gate.get("shared_active", 0) or 0) + int(
        dev_gate.get("private_active", 0) or 0
    )
    lease_signal = max(0, int(wave_leases_effective))

    parallel_signals = max(pytest_peers, dev_gate_activity, lease_signal)
    observability_mismatch = registry_live == 0 and parallel_signals > 0

    if observability_mismatch:
        resolved = max(parallel_signals, 1)
    else:
        resolved = max(registry_live, pytest_peers)

    return resolved, observability_mismatch


def compute_queue_state(
    *,
    live_agent_shpoib_count: int,
    mux_fields: dict[str, object],
    parallel_snapshot: dict[str, object] | None,
) -> tuple[bool, list[str]]:
    del live_agent_shpoib_count, mux_fields, parallel_snapshot
    from dev_gate.status import dev_gate_status

    status = dev_gate_status()
    reasons: list[str] = []
    private_waiting = int(status["private_waiting"])
    private_available = int(status.get("private_available_credits", 0) or 0)
    private_idle_reason = str(status.get("private_credit_idle_reason", "unknown"))
    if private_waiting > 0:
        if private_available > 0 and private_idle_reason not in {
            "head_blocked_large_reservation",
            "capacity_full",
        }:
            # A waiter with usable credits is an admission defect, not an
            # allowed PRIVATE queue. Surface it explicitly instead of teaching
            # agents to accept an avoidable stall as normal backpressure.
            reasons.append("private_queue_headroom")
        else:
            reasons.append("private_credit_queue")
    try:
        from e2e_core.mux_transport_queue import transport_queue_snapshot

        if transport_queue_snapshot().blocked:
            reasons.append("mux_transport_queue")
    except ImportError:
        pass
    return len(reasons) > 0, reasons


def compute_queue_layer(
    *,
    queue_expected: bool,
    queue_reasons: list[str],
    private_waiting: int,
    mux_saturated: bool,
) -> str:
    """Distinguish session-level PRIVATE queue from operation-level mux backpressure."""
    private_reasons = {"private_credit_queue", "private_queue_headroom"}
    operation_reasons = [
        reason for reason in queue_reasons if reason not in private_reasons
    ]
    if operation_reasons or mux_saturated:
        return "operation"
    if private_waiting > 0 or any(
        reason in private_reasons for reason in queue_reasons
    ):
        return "session"
    if queue_expected:
        return "operation"
    return "none"


def cap_headroom_fields(
    *,
    lease_counts: object,
    mux_fields: dict[str, object],
    active_test_count: int,
    parallel_snapshot: dict[str, object] | None = None,
    observability_mismatch: bool = False,
    orchestrator_observability: dict[str, object] | None = None,
) -> dict[str, object]:
    from dev_gate.contract import MUX_COLD_ATTACH_SLOTS
    from dev_gate.status import dev_gate_status
    from e2e_core.lease_liveness import WaveLeaseCounts

    counts = (
        lease_counts
        if isinstance(lease_counts, WaveLeaseCounts)
        else WaveLeaseCounts(
            total=int(getattr(lease_counts, "total", lease_counts)),
            live_agent_shpoib=int(
                getattr(lease_counts, "live_agent_shpoib", lease_counts)
            ),
            live_agent_shared_hot=0,
            read_page=0,
            effective_total=int(getattr(lease_counts, "total", lease_counts)),
            effective_live_agent_shpoib=int(
                getattr(lease_counts, "live_agent_shpoib", lease_counts)
            ),
            effective_live_agent_shared_hot=0,
            effective_read_page=0,
        )
    )
    mux_active = int(mux_fields.get("muxColdAttachActive", 0))
    mux_max = int(mux_fields.get("muxColdAttachMax", MUX_COLD_ATTACH_SLOTS))
    mux_saturated_legacy = mux_fields.get("muxColdAttachSaturated") is True
    orch = orchestrator_observability or {}
    operation_saturated = orch.get("operationSaturated") is True
    mux_saturated = mux_saturated_legacy or operation_saturated
    dev_gate = dev_gate_status()
    queue_expected, queue_reasons = compute_queue_state(
        live_agent_shpoib_count=counts.effective_live_agent_shpoib,
        mux_fields=mux_fields,
        parallel_snapshot=parallel_snapshot,
    )
    private_waiting = int(dev_gate["private_waiting"])
    if operation_saturated:
        queue_expected = True
        if "orchestrator_operation_queue" not in queue_reasons:
            queue_reasons = [*queue_reasons, "orchestrator_operation_queue"]
    queue_layer = compute_queue_layer(
        queue_expected=queue_expected,
        queue_reasons=queue_reasons,
        private_waiting=private_waiting,
        mux_saturated=mux_saturated,
    )
    # A disagreement between the detailed process registry and independent live
    # signals is diagnostic, not an absence of observability.  The resolved
    # count above deliberately takes the maximum of Dev Gate, wave leases, and
    # pytest peers, so SHARED admission remains safe without serializing behind
    # a temporarily incomplete process scan.
    registry_unknown = dev_gate.get("registry_observability") == "unknown"
    return {
        "waveLeasesActive": counts.total,
        "waveLeasesEffective": counts.effective_total,
        "muxColdAttachRemaining": max(0, mux_max - mux_active),
        "activeTestCount": active_test_count,
        "parallelQueueExpected": queue_expected,
        "queueReasons": queue_reasons,
        "queueLayer": queue_layer,
        "sharedUnlimited": True,
        "sharedActive": int(dev_gate["shared_active"]),
        "privateActive": int(dev_gate["private_active"]),
        "privateWaiting": int(dev_gate["private_waiting"]),
        "privateActiveCredits": int(dev_gate["private_active_credits"]),
        "privateCapacityCredits": int(dev_gate["private_capacity_credits"]),
        "privateAvailableCredits": int(dev_gate.get("private_available_credits", 0)),
        "privateCreditIdleReason": str(
            dev_gate.get("private_credit_idle_reason", "unknown")
        ),
        "registryObservabilityUnknown": registry_unknown,
        "parallelObservabilityMismatch": observability_mismatch,
        "operationQueueDepth": orch.get("queueDepth", 0),
        "estimatedOperationWaitSec": orch.get("estimatedWaitSec", 0),
        "operationWithinSlo": orch.get("withinOperationSlo", True),
        "operationSloSec": orch.get("operationSloSec", 20),
    }


def format_cap_headroom_human(
    *,
    lease_counts: object,
    mux_fields: dict[str, object],
    active_test_count: int,
    parallel_snapshot: dict[str, object] | None = None,
    orchestrator_observability: dict[str, object] | None = None,
) -> str:
    headroom = cap_headroom_fields(
        lease_counts=lease_counts,
        mux_fields=mux_fields,
        active_test_count=active_test_count,
        parallel_snapshot=parallel_snapshot,
        orchestrator_observability=orchestrator_observability,
    )
    mux_active = int(mux_fields.get("muxColdAttachActive", 0))
    mux_max = int(mux_fields.get("muxColdAttachMax", 0))
    saturated = "yes" if mux_fields.get("muxColdAttachSaturated") else "no"
    queue = "yes" if headroom["parallelQueueExpected"] else "no"
    queue_layer = headroom.get("queueLayer", "none")
    est_wait = headroom.get("estimatedOperationWaitSec", 0)
    reasons = headroom.get("queueReasons", [])
    reason_note = ""
    if isinstance(reasons, list) and reasons:
        reason_note = f" queue_reasons={','.join(str(item) for item in reasons)}"
    return (
        "E2E_CAP_HEADROOM: "
        f"shared=unlimited active={headroom['sharedActive']} "
        f"private={headroom['privateActiveCredits']}/"
        f"{headroom['privateCapacityCredits']} "
        f"private_available={headroom['privateAvailableCredits']} "
        f"private_idle={headroom['privateCreditIdleReason']} "
        f"private_waiting={headroom['privateWaiting']} "
        f"mux_cold_attach={mux_active}/{mux_max} saturated={saturated} "
        f"queue_layer={queue_layer} op_queue_depth={headroom.get('operationQueueDepth', 0)} "
        f"estimated_op_wait_sec={est_wait} "
        f"active_tests={active_test_count} queue_expected={queue}{reason_note} "
        "(do not stop other pytest)"
    )


def format_queue_human(
    *,
    lease_counts: object,
    mux_fields: dict[str, object],
    active_test_count: int,
    parallel_snapshot: dict[str, object] | None = None,
    orchestrator_observability: dict[str, object] | None = None,
) -> str | None:
    headroom = cap_headroom_fields(
        lease_counts=lease_counts,
        mux_fields=mux_fields,
        active_test_count=active_test_count,
        parallel_snapshot=parallel_snapshot,
        orchestrator_observability=orchestrator_observability,
    )
    if not headroom["parallelQueueExpected"]:
        return None
    reasons = headroom.get("queueReasons", [])
    reason_str = (
        ",".join(str(item) for item in reasons)
        if isinstance(reasons, list) and reasons
        else "unknown"
    )
    queue_layer = headroom.get("queueLayer")
    reason_items = reasons if isinstance(reasons, list) else []
    contracts: list[str] = []
    if "private_queue_headroom" in reason_items:
        contracts.append(
            "PRIVATE_QUEUE_HEADROOM_BUG: usable PRIVATE credits exist while a "
            "waiter remains queued; diagnose coordinator capacity sweep immediately."
        )
    elif (
        int(headroom.get("privateWaiting", 0) or 0) > 0
        or "private_credit_queue" in reason_items
    ):
        contracts.append(
            "PRIVATE session ADMIT is bounded to 900s; progress token "
            "E2E_PRIVATE_ADMIT_WAIT is emitted at least every 30s."
        )
    if queue_layer == "operation":
        contracts.append(
            "SHARED session launch remains immediate; browser operations use "
            "internal backpressure with P99 SLO 20s and progress."
        )
    queue_contract = " ".join(contracts)
    return (
        "E2E_QUEUE_HUMAN: "
        f"layer={queue_layer} reason={reason_str} "
        f"(private={headroom['privateActiveCredits']}/"
        f"{headroom['privateCapacityCredits']} "
        f"waiting={headroom['privateWaiting']} active_tests={active_test_count}). "
        f"{queue_contract} "
        "NEVER stop/kill other pytest. "
        "Do NOT pipe './myrm test' to tail|head — hides progress."
    )


def format_soak_headroom_verdict(*, max_active: int, max_wave: int) -> str:
    """Lightweight headroom probe for desktop soak — no full e2e-context json."""
    from e2e_core.api_verify import _mux_context_fields
    from e2e_core.lease_liveness import (
        load_wave_snapshot_observation,
        wave_lease_counts,
    )

    parallel, _ = load_parallel_runtime_snapshot()
    active = safe_active_test_count(parallel)
    if parallel.get("snapshot_unavailable") is True:
        active = -1

    wave_snapshot = load_wave_snapshot_observation()
    counts = wave_lease_counts(wave_snapshot)
    mux_fields = _mux_context_fields()
    headroom = cap_headroom_fields(
        lease_counts=counts,
        mux_fields=mux_fields,
        active_test_count=max(0, active),
        parallel_snapshot=parallel,
    )
    wave = int(
        headroom.get("waveLeasesEffective", headroom.get("waveLeasesActive", 0)) or 0
    )
    mux_sat = 1 if mux_fields.get("muxColdAttachSaturated") is True else 0
    hand_probe_block = 1 if mux_fields.get("muxHandProbeAllowed") is False else 0
    transport_queue_block = 0
    reasons = headroom.get("queueReasons")
    if isinstance(reasons, list):
        for reason in reasons:
            if "mux_transport" in str(reason):
                transport_queue_block = 1
                break

    need = 0
    if active < 0:
        need = 0
    elif active > max_active:
        need = 1
    if wave >= max_wave:
        need = 1
    if mux_sat:
        need = 1
    if hand_probe_block:
        need = 1
    if transport_queue_block:
        need = 1
    return (
        f"active={active} wave={wave} mux_sat={mux_sat} "
        f"hand_probe_block={hand_probe_block} transport_queue_block={transport_queue_block} "
        f"need_wait={need}"
    )
