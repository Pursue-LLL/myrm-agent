"""Bringing the stack ready during gate epoch preflight: signoff fast path, flocked `ready --chrome`, drift apply and the post-ready polls.

[INPUT]
- `e2e_core.runtime_probe` / `e2e_core.runtime_identity` health payload, `e2e_core.endpoint_health` stack-core verdict (POS: is the stack core already healthy)
- `e2e_core.signoff_stack_preflight`, `e2e_core.stack_mutation_policy`, `e2e_core.stale_lease_reap` (POS: signoff ready, pending drift, stale leases)

[OUTPUT]
- `ready_chrome_under_flock()`: one bounded attempt to make the shared stack ready
- `verify_api_seed()` / `apply_drift_when_idle()`: seed the API verifier, apply pending epoch drift once nothing runs
- `poll_solo_stray_leases_after_ready()` / `poll_solo_transient_peers_after_ready()`: wait out transient leases and peers before deferring

[POS]
Dev gate layer only. The steps `epoch_preflight_loop()` repeats until the epoch matches; none of them kills a peer.
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path

from e2e_core.dev_ports import shared_api_base, shared_ui_base
from e2e_core.gate_epoch_core import (
    SoloSnapshot,
    emit,
    myrm_cmd,
    read_solo_snapshot,
    run_heal_flocked,
    solo_cluster_clear,
)


def apply_drift_when_idle(monorepo_root: Path) -> None:
    from e2e_core.stack_mutation_policy import apply_pending_drift_for_maintenance

    result = apply_pending_drift_for_maintenance(monorepo_root=monorepo_root)
    emit(f"GATE_EPOCH_DRIFT action={result.action} detail={result.detail!r}")


def verify_api_seed(monorepo_root: Path) -> None:
    emit("GATE_EPOCH_HEAL: verify-api --ensure-backend (solo; no peer kill)")
    subprocess.run(
        myrm_cmd(
            monorepo_root, "verify-api", "--ensure-backend", "GET", "/api/v1/health"
        ),
        check=False,
        cwd=str(monorepo_root),
    )


def _build_signoff_stack_core_health_payload():
    from e2e_core.runtime_identity import build_health_json
    from e2e_core.runtime_probe import probe_runtime_context

    ctx = probe_runtime_context()
    ui_base = os.environ.get("E2E_UI_BASE", shared_ui_base())
    api_base = os.environ.get("E2E_API_BASE", shared_api_base())
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
    from e2e_core.endpoint_health import stack_core_health_errors

    snap = read_solo_snapshot()
    if not solo_cluster_clear(snap):
        return False
    core_errors = stack_core_health_errors(_build_signoff_stack_core_health_payload())
    if core_errors:
        return False
    emit(
        "SIGNOFF_PREFLIGHT_STACK_CORE_OK: "
        f"epoch_match={'yes' if snap.epoch_match else 'no'} "
        f"active_leases={snap.active_leases}"
    )
    verify_api_seed(monorepo_root)
    if snap.active_leases == 0:
        apply_drift_when_idle(monorepo_root)
    return True


def ready_chrome_under_flock(monorepo_root: Path, *, wall_sec: int) -> None:
    if (
        os.environ.get("MYRM_E2E_P0A_GATE") == "1"
        or os.environ.get("E2E_SIGNOFF") == "1"
    ):
        if _try_signoff_stack_core_fast_path(monorepo_root):
            return
        from e2e_core.signoff_stack_preflight import run_signoff_ready_under_flock

        rc = run_signoff_ready_under_flock(monorepo_root, wall_sec=wall_sec)
        if rc != 0:
            emit(f"GATE_EPOCH_PREFLIGHT_WARN: signoff ready subprocess rc={rc}")
        return
    env = os.environ.copy()
    env["MYRM_READY_CHROME_SOLO_WALL_SEC"] = str(wall_sec)
    cmd = [
        "env",
        f"MYRM_READY_CHROME_SOLO_WALL_SEC={wall_sec}",
        *myrm_cmd(monorepo_root, "ready", "--chrome"),
    ]
    rc = run_heal_flocked(cmd, wait_sec=180.0)
    if rc != 0:
        emit(f"GATE_EPOCH_PREFLIGHT_WARN: ready --chrome subprocess rc={rc}")


def poll_solo_stray_leases_after_ready(
    *,
    poll_sec: float = 2.0,
    wall_sec: float = 30.0,
) -> SoloSnapshot:
    """Poll transient wave leases left by solo ready --chrome before deferring."""
    snap = read_solo_snapshot()
    if snap.peers > 0 or snap.mux_peers > 1 or snap.active_leases == 0:
        return snap
    emit(
        "GATE_EPOCH_PREFLIGHT: solo stray leases after ready "
        f"active_leases={snap.active_leases} — poll idle (no peer kill)"
    )
    try:
        from e2e_core.stale_lease_reap import maybe_reap_stale_heartbeat_leases

        maybe_reap_stale_heartbeat_leases()
    except ImportError:
        pass
    deadline = time.monotonic() + wall_sec
    while time.monotonic() < deadline:
        snap = read_solo_snapshot()
        if solo_cluster_clear(snap):
            emit(
                "GATE_EPOCH_PREFLIGHT: solo stray leases cleared "
                f"active_leases={snap.active_leases}"
            )
            return snap
        time.sleep(poll_sec)
    return read_solo_snapshot()


def poll_solo_transient_peers_after_ready(
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
    emit(
        "GATE_EPOCH_PREFLIGHT: solo transient peers after ready "
        f"peers={snap.peers} active_leases={snap.active_leases} "
        f"mux_peers={snap.mux_peers} — poll idle (no peer kill)"
    )
    deadline = time.monotonic() + wall_sec
    while time.monotonic() < deadline:
        snap = read_solo_snapshot()
        if solo_cluster_clear(snap):
            emit(
                "GATE_EPOCH_PREFLIGHT: solo transient peers cleared "
                f"peers={snap.peers} active_leases={snap.active_leases}"
            )
            return snap
        time.sleep(poll_sec)
    return read_solo_snapshot()
