"""Gate epoch preflight SSOT — stack/mux/epoch readiness for Step1 signoff gate (P0-STACK-2).

[INPUT]
- peer_count_ssot, e2e_api_verify, mux_load, stack_mutation_policy, e2e_stale_lease_reap

[OUTPUT]
- run_full_preflight() → PreflightResult (OK | DEFER | FAIL)
- quick_epoch_ready() → bool

[POS]
Replaces bash _gate_assert_epoch_ready / _gate_heal_epoch_when_solo chains in e2e-p0a-1lane-gate.sh.
Never trusts ./myrm ready --chrome exit code; uses resolve_e2e_api_context() as SSOT.
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import Path
from typing import Literal


class PreflightOutcome(StrEnum):
    OK = "OK"
    DEFER = "DEFER"
    FAIL = "FAIL"


@dataclass(frozen=True, slots=True)
class SoloSnapshot:
    peers: int
    active_leases: int
    mux_peers: int
    epoch_match: bool
    blocked: bool
    drift_pending: bool


@dataclass(frozen=True, slots=True)
class PreflightResult:
    outcome: PreflightOutcome
    reason: str
    attempts: int = 0
    snapshot: SoloSnapshot | None = None
    tokens: tuple[str, ...] = field(default_factory=tuple)


def _emit(token: str) -> None:
    print(token, flush=True)


def _read_api_context():
    from e2e_api_verify import resolve_e2e_api_context

    return resolve_e2e_api_context(retry_after_apply=False)


def read_solo_snapshot() -> SoloSnapshot:
    from peer_count_ssot import (
        chrome_e2e_pytest_peer_count,
        solo_gate_active_mux_peer_count,
    )

    ctx = _read_api_context()
    return SoloSnapshot(
        peers=chrome_e2e_pytest_peer_count(),
        active_leases=int(ctx.active_leases),
        mux_peers=solo_gate_active_mux_peer_count(),
        epoch_match=bool(ctx.epoch_match),
        blocked=bool(ctx.blocked),
        drift_pending=bool(ctx.drift_pending),
    )


def solo_cluster_clear(snapshot: SoloSnapshot) -> bool:
    return (
        snapshot.peers == 0
        and snapshot.active_leases == 0
        and snapshot.mux_peers <= 1
    )


def epoch_ready(snapshot: SoloSnapshot) -> bool:
    return snapshot.epoch_match and snapshot.active_leases == 0


def _run_heal_flocked(
    cmd: list[str],
    *,
    wait_sec: float,
) -> int:
    from stack_mutation_policy import (
        default_backend_heal_flock_file,
        run_command_with_backend_heal_flock,
    )

    return run_command_with_backend_heal_flock(
        cmd=cmd,
        lock_file=default_backend_heal_flock_file(),
        wait_sec=wait_sec,
    )


def _myrm_cmd(monorepo_root: Path, *parts: str) -> list[str]:
    return [str(monorepo_root / "myrm"), *parts]


def heal_mux_when_solo(monorepo_root: Path) -> PreflightResult:
    """Mux reap + optional wave restart under solo constraints."""
    _emit(f"=== GATE_MUX_HEAL start ===")
    from mux_load import (
        active_mux_context_count,
        heal_mux_for_solo_gate,
        read_mux_status,
        reap_idle_empty_mux_contexts,
        stale_empty_mux_context_count,
    )

    heal_payload = heal_mux_for_solo_gate()
    _emit(f"GATE_SOLO_MUX_HEAL: {json.dumps(heal_payload, sort_keys=True)}")

    status = read_mux_status(force=True)
    stale = stale_empty_mux_context_count(status)
    active = active_mux_context_count(status)
    mux_reaped = False
    if stale >= 1 or stale + active > 1:
        result = reap_idle_empty_mux_contexts(idle_ms=0)
        mux_reaped = int(result.get("reaped", 0) or 0) > 0
    if mux_reaped:
        _emit("GATE_MUX_HEAL: idle empty mux contexts reaped")

    wave_reaped = False
    try:
        from e2e_stale_lease_reap import maybe_reap_excess_wave_leases

        wave_reaped = maybe_reap_excess_wave_leases(slack=0)
    except ImportError:
        pass

    if wave_reaped:
        rc = _run_heal_flocked(
            _myrm_cmd(monorepo_root, "restart", "--chrome"),
            wait_sec=180.0,
        )
        if rc == 0:
            _emit("GATE_MUX_HEAL: restart --chrome ok (wave reap)")
        else:
            _emit("GATE_MUX_HEAL_WARN: restart failed — stack-supervisor ensure (flocked)")
            ensure = monorepo_root / "myrm-agent/scripts/dev/stack-supervisor.sh"
            _run_heal_flocked(["bash", str(ensure), "rpc", "ensure"], wait_sec=180.0)
    else:
        _emit("GATE_MUX_HEAL: skip restart (no excess wave leases)")

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
    return PreflightResult(
        outcome=PreflightOutcome.OK,
        reason="mux_heal_ok",
        snapshot=snap,
        tokens=("GATE_MUX_HEAL_OK",),
    )


def _apply_drift_when_idle(monorepo_root: Path) -> None:
    from stack_mutation_policy import apply_pending_drift_if_idle

    result = apply_pending_drift_if_idle(monorepo_root=monorepo_root)
    _emit(f"GATE_EPOCH_DRIFT action={result.action} detail={result.detail!r}")


def _verify_api_seed(monorepo_root: Path) -> None:
    _emit("GATE_EPOCH_HEAL: verify-api --ensure-backend (solo; no peer kill)")
    subprocess.run(
        _myrm_cmd(monorepo_root, "verify-api", "--ensure-backend", "GET", "/api/v1/health"),
        check=False,
        cwd=str(monorepo_root),
    )


def _ready_chrome_under_flock(monorepo_root: Path, *, wall_sec: int) -> None:
    env = os.environ.copy()
    env["MYRM_READY_CHROME_SOLO_WALL_SEC"] = str(wall_sec)
    cmd = ["env", f"MYRM_READY_CHROME_SOLO_WALL_SEC={wall_sec}", *_myrm_cmd(monorepo_root, "ready", "--chrome")]
    rc = _run_heal_flocked(cmd, wait_sec=180.0)
    if rc != 0:
        _emit(f"GATE_EPOCH_PREFLIGHT_WARN: ready --chrome subprocess rc={rc}")


def _poll_solo_stray_leases_after_ready(
    *,
    poll_sec: float = 2.0,
    wall_sec: float = 30.0,
) -> SoloSnapshot:
    """Poll transient wave leases left by solo ready --chrome before deferring."""
    snap = read_solo_snapshot()
    if snap.peers > 0 or snap.mux_peers > 1 or snap.active_leases == 0:
        return snap
    _emit(
        "GATE_EPOCH_PREFLIGHT: solo stray leases after ready "
        f"active_leases={snap.active_leases} — poll idle (no peer kill)"
    )
    try:
        from e2e_stale_lease_reap import maybe_reap_stale_heartbeat_leases

        maybe_reap_stale_heartbeat_leases()
    except ImportError:
        pass
    deadline = time.monotonic() + wall_sec
    while time.monotonic() < deadline:
        snap = read_solo_snapshot()
        if solo_cluster_clear(snap):
            _emit(
                "GATE_EPOCH_PREFLIGHT: solo stray leases cleared "
                f"active_leases={snap.active_leases}"
            )
            return snap
        time.sleep(poll_sec)
    return read_solo_snapshot()


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

        if not solo_cluster_clear(snap):
            _emit(
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

        _ready_chrome_under_flock(monorepo_root, wall_sec=180)
        snap = _poll_solo_stray_leases_after_ready()

        if not solo_cluster_clear(snap):
            _emit(
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

        if epoch_ready(snap):
            _emit(
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
            _emit(
                "GATE_EPOCH_PREFLIGHT: epoch_match=yes but "
                f"active_leases={snap.active_leases} — wait for wave idle"
            )

        _emit(
            "GATE_EPOCH_PREFLIGHT: epoch_match="
            f"{'yes' if snap.epoch_match else 'no'} active_leases={snap.active_leases} "
            f"blocked={int(snap.blocked)} drift_pending={int(snap.drift_pending)} "
            f"attempt={attempt}"
        )

        if snap.active_leases > 0:
            _emit(
                f"GATE_EPOCH_HEAL: verify-api seed (wave leases={snap.active_leases})"
            )
            _verify_api_seed(monorepo_root)
        else:
            _verify_api_seed(monorepo_root)
            _apply_drift_when_idle(monorepo_root)
            if attempt >= 2 and not solo_restart_done:
                _emit("GATE_EPOCH_HEAL: solo restart --chrome (peers=0, wave leases=0)")
                rc = _run_heal_flocked(
                    _myrm_cmd(monorepo_root, "restart", "--chrome"),
                    wait_sec=180.0,
                )
                solo_restart_done = True
                if rc != 0:
                    _emit("GATE_EPOCH_HEAL_WARN: restart --chrome failed")

        time.sleep(poll_sec)

    snap = read_solo_snapshot()
    if not solo_cluster_clear(snap):
        _emit(
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
    _emit(f"GATE_EPOCH_PREFLIGHT_FAIL: epoch_match!=yes after {int(wall_sec)}s")
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
        _emit("=== GATE_MUX_HEAL ok ===")
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
