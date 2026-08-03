"""Parallel E2E runtime status probes: snapshot, queue state, capacity headroom.

[INPUT]
- tests.support.e2e_parallel_snapshot (POS: live process/flock snapshot)
- dev_gate_status (POS: Dev Gate registry status)
- dev_gate_contract (POS: Dev Gate constants — MUX_COLD_ATTACH_SLOTS)
- e2e_lease_liveness (POS: WaveLeaseCounts type)

[OUTPUT]
- load_parallel_runtime_snapshot: live E2E process snapshot (dict + human lines)
- safe_active_test_count: fail-closed active test count
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

import sys
from pathlib import Path
from typing import Final

_MONOREPO_ROOT: Final[Path] = Path(__file__).resolve().parents[4]


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
        from tests.support.e2e_parallel_snapshot import (  # noqa: PLC0415
            format_parallel_snapshot_human,
            parallel_snapshot_to_dict,
            snapshot_live_e2e_processes,
        )

        snapshot = snapshot_live_e2e_processes()
        return parallel_snapshot_to_dict(snapshot), format_parallel_snapshot_human(
            snapshot
        )
    except Exception as exc:
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


def compute_queue_state(
    *,
    live_agent_shpoib_count: int,
    mux_fields: dict[str, object],
    parallel_snapshot: dict[str, object] | None,
) -> tuple[bool, list[str]]:
    del live_agent_shpoib_count, mux_fields, parallel_snapshot
    from dev_gate_status import dev_gate_status  # noqa: PLC0415

    status = dev_gate_status()
    reasons: list[str] = []
    if int(status["private_waiting"]) > 0:
        reasons.append("private_credit_queue")
    try:
        from e2e_mux_transport_queue import transport_queue_snapshot  # noqa: PLC0415

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
    if private_waiting > 0 or "private_credit_queue" in queue_reasons:
        return "session"
    if queue_expected or mux_saturated:
        return "operation"
    return "none"


def cap_headroom_fields(
    *,
    lease_counts: object,
    mux_fields: dict[str, object],
    active_test_count: int,
    parallel_snapshot: dict[str, object] | None = None,
) -> dict[str, object]:
    from dev_gate_contract import MUX_COLD_ATTACH_SLOTS  # noqa: PLC0415
    from dev_gate_status import dev_gate_status  # noqa: PLC0415
    from e2e_lease_liveness import WaveLeaseCounts  # noqa: PLC0415

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
    mux_saturated = mux_fields.get("muxColdAttachSaturated") is True
    dev_gate = dev_gate_status()
    queue_expected, queue_reasons = compute_queue_state(
        live_agent_shpoib_count=counts.effective_live_agent_shpoib,
        mux_fields=mux_fields,
        parallel_snapshot=parallel_snapshot,
    )
    private_waiting = int(dev_gate["private_waiting"])
    queue_layer = compute_queue_layer(
        queue_expected=queue_expected,
        queue_reasons=queue_reasons,
        private_waiting=private_waiting,
        mux_saturated=mux_saturated,
    )
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
    }


def format_cap_headroom_human(
    *,
    lease_counts: object,
    mux_fields: dict[str, object],
    active_test_count: int,
    parallel_snapshot: dict[str, object] | None = None,
) -> str:
    headroom = cap_headroom_fields(
        lease_counts=lease_counts,
        mux_fields=mux_fields,
        active_test_count=active_test_count,
        parallel_snapshot=parallel_snapshot,
    )
    mux_active = int(mux_fields.get("muxColdAttachActive", 0))
    mux_max = int(mux_fields.get("muxColdAttachMax", 0))
    saturated = "yes" if mux_fields.get("muxColdAttachSaturated") else "no"
    queue = "yes" if headroom["parallelQueueExpected"] else "no"
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
        f"active_tests={active_test_count} queue_expected={queue}{reason_note} "
        "(do not stop other pytest)"
    )


def format_queue_human(
    *,
    lease_counts: object,
    mux_fields: dict[str, object],
    active_test_count: int,
    parallel_snapshot: dict[str, object] | None = None,
) -> str | None:
    headroom = cap_headroom_fields(
        lease_counts=lease_counts,
        mux_fields=mux_fields,
        active_test_count=active_test_count,
        parallel_snapshot=parallel_snapshot,
    )
    if not headroom["parallelQueueExpected"]:
        return None
    reasons = headroom.get("queueReasons", [])
    reason_str = (
        ",".join(str(item) for item in reasons)
        if isinstance(reasons, list) and reasons
        else "unknown"
    )
    return (
        "E2E_QUEUE_HUMAN: "
        f"reason={reason_str} "
        f"(private={headroom['privateActiveCredits']}/"
        f"{headroom['privateCapacityCredits']} "
        f"waiting={headroom['privateWaiting']} active_tests={active_test_count}). "
        "Only PRIVATE runtime creation queues in ADMIT (≤900s); "
        "SHARED logical sessions are unlimited. "
        "NEVER stop/kill other pytest. "
        "Progress on stderr: E2E_PRIVATE_ADMIT_WAIT every 30s. "
        "Do NOT pipe './myrm test' to tail|head — hides progress."
    )


def format_soak_headroom_verdict(*, max_active: int, max_wave: int) -> str:
    """Lightweight headroom probe for desktop soak — no full e2e-context json."""
    from e2e_api_verify import _mux_context_fields  # noqa: PLC0415
    from e2e_lease_liveness import (  # noqa: PLC0415
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
