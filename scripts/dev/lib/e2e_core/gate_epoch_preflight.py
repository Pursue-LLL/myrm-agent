"""Gate epoch preflight SSOT — stack/mux/epoch readiness for maintainer gates and Phase C ramp.

[INPUT]
- peer_count_ssot, api_verify, mux.load, stack_mutation_policy, stale_lease_reap; e2e_core.dev_ports::shared_api_base / shared_ui_base (POS: Default ports of the user, shared dev and isolated stacks — SSOT)

[OUTPUT]
- run_full_preflight() → PreflightResult (OK | DEFER | FAIL)
- quick_epoch_ready() → bool

[POS]
Used by phase-c ramp and maintainer epoch preflight loops.
Never trusts ./myrm-dev ready --chrome exit code; uses resolve_e2e_api_context() as SSOT.
"""

from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

from e2e_core.gate_epoch_chrome_heal import (
    restart_chrome_if_cdp_page_surge,
    restart_chrome_if_orphan_budget_exceeded,
    signoff_gate_cluster_clear,
)
from e2e_core.gate_epoch_core import (
    PreflightOutcome,
    PreflightResult,
    emit,
    epoch_ready,
    myrm_cmd,
    read_solo_snapshot,
    run_heal_flocked,
    solo_cluster_clear,
)
from e2e_core.gate_epoch_ready import (
    apply_drift_when_idle,
    poll_solo_stray_leases_after_ready,
    poll_solo_transient_peers_after_ready,
    ready_chrome_under_flock,
    verify_api_seed,
)


def run_signoff_solo_chrome_heals(monorepo_root: Path) -> None:
    """Orphan budget + CDP surge heal when signoff gate holds solo cluster."""
    if not signoff_gate_cluster_clear():
        return
    restart_chrome_if_orphan_budget_exceeded(monorepo_root)
    restart_chrome_if_cdp_page_surge(monorepo_root)


def heal_mux_when_solo(monorepo_root: Path) -> PreflightResult:
    """Mux reap + optional wave restart under solo constraints."""
    emit("=== GATE_MUX_HEAL start ===")
    run_signoff_solo_chrome_heals(monorepo_root)
    from mux.load import (
        active_mux_context_count,
        heal_mux_for_solo_gate,
        read_mux_status,
        reap_idle_empty_mux_contexts,
        stale_empty_mux_context_count,
    )

    heal_payload = heal_mux_for_solo_gate()
    emit(f"GATE_SOLO_MUX_HEAL: {json.dumps(heal_payload, sort_keys=True)}")

    status = read_mux_status(force=True)
    stale = stale_empty_mux_context_count(status)
    active = active_mux_context_count(status)
    mux_reaped = False
    if stale >= 1 or stale + active > 1:
        reaped = reap_idle_empty_mux_contexts(idle_ms=0).get("reaped", 0)
        mux_reaped = isinstance(reaped, int) and reaped > 0
    if mux_reaped:
        emit("GATE_MUX_HEAL: idle empty mux contexts reaped")

    wave_reaped = False
    try:
        from e2e_core.stale_lease_reap import maybe_reap_excess_wave_leases

        wave_reaped = maybe_reap_excess_wave_leases(slack=0)
    except ImportError:
        pass

    if wave_reaped:
        rc = run_heal_flocked(
            myrm_cmd(monorepo_root, "restart", "--chrome"),
            wait_sec=180.0,
        )
        if rc == 0:
            emit("GATE_MUX_HEAL: restart --chrome ok (wave reap)")
        else:
            emit(
                "GATE_MUX_HEAL_WARN: restart failed — stack-supervisor ensure (flocked)"
            )
            ensure = monorepo_root / "myrm-agent/scripts/dev/stack-supervisor.sh"
            run_heal_flocked(["bash", str(ensure), "rpc", "ensure"], wait_sec=180.0)
    else:
        emit("GATE_MUX_HEAL: skip restart (no excess wave leases)")

    snap = read_solo_snapshot()
    if not solo_cluster_clear(snap):
        return PreflightResult(
            outcome=PreflightOutcome.DEFER,
            reason=(
                f"solo_cluster_busy:peers={snap.peers} "
                f"leases={snap.active_leases} mux={snap.mux_peers}"
            ),
            snapshot=snap,
            tokens=("GATE_MUX_HEAL_DEFER",),
        )
    try:
        from e2e_core.idle_hygiene_scheduler import run_idle_tab_hygiene_if_safe

        hygiene = run_idle_tab_hygiene_if_safe(trigger="signoff_gate_preflight")
        emit(f"GATE_IDLE_HYGIENE: {json.dumps(hygiene, sort_keys=True)}")
    except ImportError:
        pass
    return PreflightResult(
        outcome=PreflightOutcome.OK,
        reason="mux_heal_ok",
        snapshot=snap,
        tokens=("GATE_MUX_HEAL_OK",),
    )


def epoch_preflight_loop(
    monorepo_root: Path,
    *,
    wall_sec: float = 300.0,
    poll_sec: float = 10.0,
) -> PreflightResult:
    """Bounded loop until epoch_match=yes and active_leases=0."""
    deadline = time.monotonic() + wall_sec
    attempt = 0
    solo_restart_done = False

    while time.monotonic() < deadline:
        attempt += 1
        snap = read_solo_snapshot()

        if snap.peers > 0 or snap.mux_peers > 1:
            emit(
                "GATE_EPOCH_PREFLIGHT: cluster busy "
                f"peers={snap.peers} active_leases={snap.active_leases} "
                f"mux_peers={snap.mux_peers} — defer (no attach budget burn)"
            )
            return PreflightResult(
                outcome=PreflightOutcome.DEFER,
                reason="solo_cluster_busy",
                attempts=attempt,
                snapshot=snap,
                tokens=("GATE_EPOCH_PREFLIGHT_DEFER",),
            )

        if snap.active_leases > 0:
            emit(
                "GATE_EPOCH_PREFLIGHT: solo wave leases pending "
                f"active_leases={snap.active_leases} — heal loop (no peer kill)"
            )

        ready_chrome_under_flock(monorepo_root, wall_sec=180)
        snap = poll_solo_stray_leases_after_ready()
        snap = poll_solo_transient_peers_after_ready(snap)

        if snap.peers > 0 or snap.mux_peers > 1:
            emit(
                "GATE_EPOCH_PREFLIGHT: cluster busy after ready "
                f"peers={snap.peers} active_leases={snap.active_leases} "
                f"mux_peers={snap.mux_peers} — defer (no attach budget burn)"
            )
            return PreflightResult(
                outcome=PreflightOutcome.DEFER,
                reason="solo_cluster_busy_after_ready",
                attempts=attempt,
                snapshot=snap,
                tokens=("GATE_EPOCH_PREFLIGHT_DEFER",),
            )

        if snap.active_leases > 0:
            emit(
                "GATE_EPOCH_PREFLIGHT: stray wave leases after ready "
                f"active_leases={snap.active_leases} — continue heal loop (no instant defer)"
            )

        if epoch_ready(snap):
            emit(
                f"GATE_EPOCH_PREFLIGHT_OK: epoch_match=yes active_leases=0 attempt={attempt}"
            )
            return PreflightResult(
                outcome=PreflightOutcome.OK,
                reason="epoch_ready",
                attempts=attempt,
                snapshot=snap,
                tokens=("GATE_EPOCH_PREFLIGHT_OK",),
            )

        if snap.epoch_match and snap.active_leases > 0:
            emit(
                "GATE_EPOCH_PREFLIGHT: epoch_match=yes but "
                f"active_leases={snap.active_leases} — wait for wave idle"
            )

        emit(
            "GATE_EPOCH_PREFLIGHT: epoch_match="
            f"{'yes' if snap.epoch_match else 'no'} active_leases={snap.active_leases} "
            f"blocked={int(snap.blocked)} drift_pending={int(snap.drift_pending)} "
            f"attempt={attempt}"
        )

        if snap.active_leases > 0:
            emit(
                f"GATE_EPOCH_HEAL: verify-api seed (wave leases={snap.active_leases})"
            )
            verify_api_seed(monorepo_root)
        else:
            verify_api_seed(monorepo_root)
            apply_drift_when_idle(monorepo_root)
            if attempt >= 2 and not solo_restart_done:
                emit("GATE_EPOCH_HEAL: solo restart --chrome (peers=0, wave leases=0)")
                rc = run_heal_flocked(
                    myrm_cmd(monorepo_root, "restart", "--chrome"),
                    wait_sec=180.0,
                )
                solo_restart_done = True
                if rc != 0:
                    emit("GATE_EPOCH_HEAL_WARN: restart --chrome failed")

        time.sleep(poll_sec)

    snap = read_solo_snapshot()
    if snap.peers > 0 or snap.mux_peers > 1:
        emit(
            "GATE_EPOCH_PREFLIGHT: cluster busy at wall "
            f"peers={snap.peers} active_leases={snap.active_leases} "
            f"mux_peers={snap.mux_peers} — defer (no attach budget burn)"
        )
        return PreflightResult(
            outcome=PreflightOutcome.DEFER,
            reason="solo_cluster_busy_at_wall",
            attempts=attempt,
            snapshot=snap,
            tokens=("GATE_EPOCH_PREFLIGHT_DEFER",),
        )
    emit(f"GATE_EPOCH_PREFLIGHT_FAIL: epoch_match!=yes after {int(wall_sec)}s")
    return PreflightResult(
        outcome=PreflightOutcome.FAIL,
        reason="epoch_preflight_timeout",
        attempts=attempt,
        snapshot=snap,
        tokens=("GATE_EPOCH_PREFLIGHT_FAIL",),
    )


def run_full_preflight(
    monorepo_root: Path,
    *,
    epoch_wall_sec: float = 300.0,
) -> PreflightResult:
    mux = heal_mux_when_solo(monorepo_root)
    if mux.outcome != PreflightOutcome.OK:
        return mux
    epoch = epoch_preflight_loop(monorepo_root, wall_sec=epoch_wall_sec)
    if epoch.outcome == PreflightOutcome.OK:
        emit("=== GATE_MUX_HEAL ok ===")
    return epoch


def quick_epoch_ready() -> PreflightResult:
    snap = read_solo_snapshot()
    if not solo_cluster_clear(snap):
        return PreflightResult(
            outcome=PreflightOutcome.DEFER,
            reason="solo_cluster_busy",
            snapshot=snap,
        )
    if epoch_ready(snap):
        return PreflightResult(
            outcome=PreflightOutcome.OK,
            reason="epoch_ready",
            snapshot=snap,
        )
    return PreflightResult(
        outcome=PreflightOutcome.DEFER,
        reason="epoch_not_ready",
        snapshot=snap,
    )


def _exit_code(result: PreflightResult) -> int:
    if result.outcome == PreflightOutcome.OK:
        return 0
    if result.outcome == PreflightOutcome.DEFER:
        return 2
    return 3


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Gate epoch preflight SSOT")
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument(
        "--mode",
        choices=("full", "quick", "epoch-only"),
        default="full",
    )
    parser.add_argument("--epoch-wall-sec", type=float, default=300.0)
    args = parser.parse_args(argv)
    root = args.root.resolve()

    if args.mode == "full":
        result = run_full_preflight(root, epoch_wall_sec=args.epoch_wall_sec)
    elif args.mode == "quick":
        result = quick_epoch_ready()
    else:
        result = epoch_preflight_loop(root, wall_sec=args.epoch_wall_sec)

    return _exit_code(result)


if __name__ == "__main__":
    raise SystemExit(main())
