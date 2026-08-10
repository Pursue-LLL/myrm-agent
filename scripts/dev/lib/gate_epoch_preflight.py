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
        snapshot.peers == 0 and snapshot.active_leases == 0 and snapshot.mux_peers <= 1
    )


SIGNOFF_GATE_CDP_PAGE_CEILING = 8


def attach_parallel_leases() -> int:
    """Match e2e_bootstrap.sh _e2e_parallel_active_leases (wave first, then live sessions)."""
    from e2e_lease_liveness import load_wave_snapshot, wave_lease_counts

    effective = wave_lease_counts(load_wave_snapshot()).effective_total
    if effective > 0:
        return effective
    from e2e_session_registry import list_live_e2e_sessions

    return len(list_live_e2e_sessions())


def signoff_lane_spawn_clear(snapshot: SoloSnapshot) -> bool:
    """Step1 gate lane spawn SSOT — align with chrome attach parallel lease accounting."""
    return solo_cluster_clear(snapshot) and attach_parallel_leases() == 0


def signoff_gate_cluster_clear() -> bool:
    return signoff_lane_spawn_clear(read_solo_snapshot())


def count_cdp_page_targets() -> int | None:
    from browser_tab_hygiene import _chrome_port, _count_cdp_targets

    count = _count_cdp_targets(_chrome_port())
    return count if count >= 0 else None


def _chrome_e2e_listener_pids() -> list[str]:
    import subprocess

    from browser_tab_hygiene import _chrome_port

    port = _chrome_port()
    result = subprocess.run(
        ["lsof", "-tiTCP:{port}", "-sTCP:LISTEN"],
        capture_output=True,
        text=True,
        check=False,
    )
    return [line.strip() for line in result.stdout.splitlines() if line.strip()]


def _kill_chrome_e2e_browser(*, wait_sec: float = 45.0) -> bool:
    """Terminate dedicated Myrm E2E Chrome (CDP listener) — clears tab storms."""
    import subprocess
    import time

    pids = _chrome_e2e_listener_pids()
    if not pids:
        return False
    for pid in pids:
        subprocess.run(["kill", "-TERM", pid], check=False)
    deadline = time.monotonic() + min(wait_sec, 15.0)
    while time.monotonic() < deadline:
        if not _chrome_e2e_listener_pids():
            return True
        time.sleep(0.5)
    for pid in _chrome_e2e_listener_pids():
        subprocess.run(["kill", "-KILL", pid], check=False)
    time.sleep(1.0)
    return not _chrome_e2e_listener_pids()


def _ensure_chrome_e2e_browser(monorepo_root: Path) -> int:
    import subprocess

    ensure = (
        monorepo_root / "myrm-agent" / "scripts" / "dev" / "ensure-myrm-chrome-e2e.sh"
    )
    if not ensure.is_file():
        return 1
    completed = subprocess.run(
        ["bash", str(ensure)],
        cwd=str(monorepo_root),
        check=False,
    )
    return int(completed.returncode)


def restart_chrome_if_cdp_page_surge(
    monorepo_root: Path,
    *,
    ceiling: int = SIGNOFF_GATE_CDP_PAGE_CEILING,
) -> bool:
    """Solo signoff heal when CDP page targets exceed gate ceiling (Aug4 PASS had ~3)."""
    count = count_cdp_page_targets()
    if count is None or count <= ceiling:
        return False
    _emit(
        "GATE_CDP_SURGE_HEAL: "
        f"pages={count} ceiling={ceiling} — kill E2E Chrome + ensure + attach ready"
    )
    if not _kill_chrome_e2e_browser():
        _emit("GATE_CDP_SURGE_HEAL_WARN: E2E Chrome listener still up after kill")
    if _ensure_chrome_e2e_browser(monorepo_root) != 0:
        _emit("GATE_CDP_SURGE_HEAL_WARN: ensure-myrm-chrome-e2e failed")
        return False
    after = count_cdp_page_targets()
    if after is not None and after > ceiling:
        _emit(
            f"GATE_CDP_SURGE_HEAL_WARN: pages={after} still above ceiling={ceiling} after ensure"
        )
    rc = _run_heal_flocked(
        _myrm_cmd(monorepo_root, "ready", "--attach", "--chrome"),
        wait_sec=180.0,
    )
    if rc == 0:
        _emit("GATE_CDP_SURGE_HEAL_OK: attach ready --chrome after CDP surge kill")
        return True
    _emit(f"GATE_CDP_SURGE_HEAL_WARN: attach ready rc={rc}")
    return False


def run_signoff_solo_chrome_heals(monorepo_root: Path) -> None:
    """Orphan budget + CDP surge heal when signoff gate holds solo cluster."""
    if not signoff_gate_cluster_clear():
        return
    restart_chrome_if_orphan_budget_exceeded(monorepo_root)
    restart_chrome_if_cdp_page_surge(monorepo_root)


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


def restart_chrome_if_orphan_budget_exceeded(monorepo_root: Path) -> bool:
    """Solo signoff heal when blank tabs exceed orphan budget (TAB-5)."""
    try:
        from chrome_e2e.gates.orphan_budget import evaluate_orphan_budget
    except ImportError:
        return False
    budget = evaluate_orphan_budget()
    if budget.get("ok"):
        return False
    _emit(
        "GATE_ORPHAN_BUDGET_HEAL: "
        f"{json.dumps(budget, sort_keys=True)} — restart --chrome (solo; no peer kill)"
    )
    rc = _run_heal_flocked(
        _myrm_cmd(monorepo_root, "restart", "--chrome"),
        wait_sec=180.0,
    )
    if rc == 0:
        _emit("GATE_ORPHAN_BUDGET_HEAL_OK: restart --chrome")
        return True
    _emit(f"GATE_ORPHAN_BUDGET_HEAL_WARN: restart rc={rc}")
    return False


def heal_mux_when_solo(monorepo_root: Path) -> PreflightResult:
    """Mux reap + optional wave restart under solo constraints."""
    _emit("=== GATE_MUX_HEAL start ===")
    run_signoff_solo_chrome_heals(monorepo_root)
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
            _emit(
                "GATE_MUX_HEAL_WARN: restart failed — stack-supervisor ensure (flocked)"
            )
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
    try:
        from idle_hygiene_scheduler import run_idle_tab_hygiene_if_safe

        hygiene = run_idle_tab_hygiene_if_safe(trigger="signoff_gate_preflight")
        _emit(f"GATE_IDLE_HYGIENE: {json.dumps(hygiene, sort_keys=True)}")
    except ImportError:
        pass
    return PreflightResult(
        outcome=PreflightOutcome.OK,
        reason="mux_heal_ok",
        snapshot=snap,
        tokens=("GATE_MUX_HEAL_OK",),
    )


def _apply_drift_when_idle(monorepo_root: Path) -> None:
    from stack_mutation_policy import apply_pending_drift_for_maintenance

    result = apply_pending_drift_for_maintenance(monorepo_root=monorepo_root)
    _emit(f"GATE_EPOCH_DRIFT action={result.action} detail={result.detail!r}")


def _verify_api_seed(monorepo_root: Path) -> None:
    _emit("GATE_EPOCH_HEAL: verify-api --ensure-backend (solo; no peer kill)")
    subprocess.run(
        _myrm_cmd(
            monorepo_root, "verify-api", "--ensure-backend", "GET", "/api/v1/health"
        ),
        check=False,
        cwd=str(monorepo_root),
    )


def _build_signoff_stack_core_health_payload():
    import os
    from pathlib import Path

    from runtime_identity import build_health_json
    from runtime_probe import probe_runtime_context

    ctx = probe_runtime_context()
    ui_base = os.environ.get("E2E_UI_BASE", "http://127.0.0.1:3000")
    api_base = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8080")
    frontend_dir = Path(str(ctx["frontend_dir"])) if ctx.get("frontend_dir") else None
    profile_dir = Path(str(ctx["profile_dir"])) if ctx.get("profile_dir") else None
    cdp_port_raw = ctx.get("cdp_port")
    cdp_port = (
        int(cdp_port_raw)
        if isinstance(cdp_port_raw, int) and cdp_port_raw > 0
        else None
    )
    return build_health_json(
        ui_base=ui_base,
        api_base=api_base,
        mux_daemon_count=int(ctx["mux_daemon_count"]),
        upstream_ready=bool(ctx["upstream_ready"]),
        ws_stamp_matches=bool(ctx["ws_stamp_matches"]),
        shell_hot=False,
        client_hot=False,
        attach_mode=False,
        auto_hot=True,
        upstream_generation=int(ctx.get("upstream_generation") or 0),
        frontend_dir=frontend_dir,
        cdp_port=cdp_port,
        profile_dir=profile_dir,
    )


def _try_signoff_stack_core_fast_path(monorepo_root: Path) -> bool:
    """Skip myrm ready when stack core + API liveness OK and solo clear (P0-SAO-8)."""
    from runtime_identity import stack_core_health_errors

    snap = read_solo_snapshot()
    if not solo_cluster_clear(snap):
        return False
    core_errors = stack_core_health_errors(_build_signoff_stack_core_health_payload())
    if core_errors:
        return False
    _emit(
        "SIGNOFF_PREFLIGHT_STACK_CORE_OK: "
        f"epoch_match={'yes' if snap.epoch_match else 'no'} "
        f"active_leases={snap.active_leases}"
    )
    _verify_api_seed(monorepo_root)
    if snap.active_leases == 0:
        _apply_drift_when_idle(monorepo_root)
    return True


def _ready_chrome_under_flock(monorepo_root: Path, *, wall_sec: int) -> None:
    if (
        os.environ.get("MYRM_E2E_P0A_GATE") == "1"
        or os.environ.get("E2E_SIGNOFF") == "1"
    ):
        if _try_signoff_stack_core_fast_path(monorepo_root):
            return
        from signoff_stack_preflight import run_signoff_ready_under_flock

        rc = run_signoff_ready_under_flock(monorepo_root, wall_sec=wall_sec)
        if rc != 0:
            _emit(f"GATE_EPOCH_PREFLIGHT_WARN: signoff ready subprocess rc={rc}")
        return
    env = os.environ.copy()
    env["MYRM_READY_CHROME_SOLO_WALL_SEC"] = str(wall_sec)
    cmd = [
        "env",
        f"MYRM_READY_CHROME_SOLO_WALL_SEC={wall_sec}",
        *_myrm_cmd(monorepo_root, "ready", "--chrome"),
    ]
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


def _poll_solo_transient_peers_after_ready(
    snap: SoloSnapshot,
    *,
    poll_sec: float = 2.0,
    wall_sec: float = 30.0,
) -> SoloSnapshot:
    """Poll transient pytest peers after solo ready --chrome before deferring."""
    if snap.peers == 0 and snap.mux_peers <= 1:
        return snap
    if snap.peers > 1 or snap.mux_peers > 1:
        return snap
    _emit(
        "GATE_EPOCH_PREFLIGHT: solo transient peers after ready "
        f"peers={snap.peers} active_leases={snap.active_leases} "
        f"mux_peers={snap.mux_peers} — poll idle (no peer kill)"
    )
    deadline = time.monotonic() + wall_sec
    while time.monotonic() < deadline:
        snap = read_solo_snapshot()
        if solo_cluster_clear(snap):
            _emit(
                "GATE_EPOCH_PREFLIGHT: solo transient peers cleared "
                f"peers={snap.peers} active_leases={snap.active_leases}"
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
        try:
            from signoff_runtime_guard import guard_signoff_runtime

            guard_signoff_runtime(reap=True)
        except ImportError:
            pass
        snap = read_solo_snapshot()

        if snap.peers > 0 or snap.mux_peers > 1:
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

        if snap.active_leases > 0:
            _emit(
                "GATE_EPOCH_PREFLIGHT: solo wave leases pending "
                f"active_leases={snap.active_leases} — heal loop (no peer kill)"
            )

        _ready_chrome_under_flock(monorepo_root, wall_sec=180)
        snap = _poll_solo_stray_leases_after_ready()
        snap = _poll_solo_transient_peers_after_ready(snap)

        if snap.peers > 0 or snap.mux_peers > 1:
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

        if snap.active_leases > 0:
            _emit(
                "GATE_EPOCH_PREFLIGHT: stray wave leases after ready "
                f"active_leases={snap.active_leases} — continue heal loop (no instant defer)"
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
    if snap.peers > 0 or snap.mux_peers > 1:
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
