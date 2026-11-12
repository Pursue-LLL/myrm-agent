"""Unified Browser Data Plane health — SSOT for mux/orchestrator/epoch observability.

[INPUT]
- runtime_probe.probe_runtime_context (mux daemon count)
- plane_probes (leases, sessions, orchestrator status), plane_state (states and classification), plane_reap (stale artifacts, mux log cap), plane_converge_lock (idle converge lock)
- stack_mutation_policy (idle drift apply)

[OUTPUT]
- reap_stale_plane_artifacts() / converge_plane_if_idle() / plane_health_snapshot()
- ensure_mux_daemon_if_absent() / _start_mux_daemon_if_needed() — idempotent mux cold start (never restarts live daemons)
- converge_plane_if_idle() takes the idle converge lock, which breaks a stale /tmp/plane-converge.lockdir (>120s)
- Consumed by e2e-context (dataPlane block) and attach fast-fail

[POS]
Dev Gate infra layer. Idle converge never mutates stack during active wave leases;
mux cold-start via ensure_mux_daemon_if_absent is lease-safe (start-only, never kills peers).
"""

from __future__ import annotations

import os
import subprocess
import time
from pathlib import Path
from typing import Final

from e2e_core.browser_epoch import (
    default_chrome_data_dir,
    mux_state_dir,
    resolve_e2e_port,
)
from e2e_core.plane_converge_lock import converge_lock_dir, try_acquire_converge_lock
from e2e_core.plane_probes import (
    cluster_active_sessions,
    orchestrator_status,
    plane_state_dir,
    resolve_monorepo_root,
    resolve_node_executable,
    socket_listener_probe,
    wave_active_leases,
)
from e2e_core.plane_reap import bound_log_growth, reap_stale_plane_artifacts
from e2e_core.plane_state import (
    ConvergeReceipt,
    PlaneHealthSnapshot,
    PlaneHealthState,
    build_agent_rule,
    classify_state,
)

# Wait budget for a cold mux daemon start. The daemon waits for Chrome's cold CDP
# endpoint before it attaches its upstream and creates its socket (ensure-cdp-ready.mjs
# waits up to 45s), so this must outlast that wait — a shorter poll reported failure while
# the daemon was still legitimately starting, which masqueraded as a broken plane and
# triggered a cold-start storm.
_MUX_COLD_START_WAIT_SEC: Final[float] = 60.0


def _socket_has_listener(socket_path: Path) -> bool:
    return socket_listener_probe(socket_path) is True


def _mux_daemon_count_live() -> int:
    try:
        from e2e_core.runtime_probe import probe_runtime_context

        ctx = probe_runtime_context()
        return int(ctx.get("mux_daemon_count") or 0)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return 0


def _orchestrator_daemon_listening() -> bool:
    """Whether the orchestrator daemon serves its socket, independent of any RPC.

    Delegates to the client-layer SSOT so plane classification and every launch gate
    share one definition of "daemon is up". `BrowserOrchestratorClient.is_alive()`
    answers a status RPC and therefore reports "not alive" for a daemon that is merely
    busy answering peers, which is what made a transient parallel-load timeout look
    like a plane outage.
    """
    try:
        from browser_orchestrator.client import BrowserOrchestratorClient
    except ImportError:
        return False
    try:
        return BrowserOrchestratorClient.transport_is_alive()
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return False


def _start_mux_daemon_if_needed() -> bool:
    """Start mux with the same env contract as chrome-e2e-preflight _start_mux_daemon."""
    if _mux_daemon_count_live() >= 1:
        return True
    root = resolve_monorepo_root()
    mux_bin = (
        root
        / "scripts"
        / "dev"
        / "cdmcp-mux-autoconnect"
        / "bin"
        / "cdmcp-mux-autoconnect.mjs"
    )
    node = resolve_node_executable()
    if node is None or not mux_bin.is_file():
        return False
    mux_dir = mux_state_dir()
    mux_dir.mkdir(parents=True, exist_ok=True)
    mux_socket = mux_dir / "cdmcp-mux.sock"
    chrome_data = default_chrome_data_dir()
    request_timeout = (
        os.getenv("CDMCP_MUX_REQUEST_TIMEOUT_MS", "180000").strip() or "180000"
    )
    node_dir = str(Path(node).parent)
    current_path = os.environ.get("PATH", "")
    fixed_path = (
        f"{node_dir}:{current_path}"
        if node_dir not in current_path.split(":")
        else current_path
    )
    env = {
        **os.environ,
        "PATH": fixed_path,
        "CHROME_DATA_DIR": str(chrome_data),
        "MYRM_CHROME_E2E_DATA_DIR": str(chrome_data),
        "MYRM_CHROME_E2E_PORT": str(resolve_e2e_port()),
        "CDMCP_MUX_STATE_DIR": str(mux_dir),
        "CDMCP_MUX_SOCKET": str(mux_socket),
        "CDMCP_MUX_REQUEST_TIMEOUT_MS": request_timeout,
        "MCP_MUX_UPSTREAM_STDERR": os.getenv("MCP_MUX_UPSTREAM_STDERR", "1"),
    }
    log_file = mux_dir / "mux.log"
    bound_log_growth(log_file)
    try:
        log_handle = log_file.open("a", encoding="utf-8")
    except OSError:
        log_handle = None
    try:
        proc = subprocess.Popen(
            [node, str(mux_bin), "daemon"],
            stdout=log_handle or subprocess.DEVNULL,
            stderr=subprocess.STDOUT if log_handle is not None else subprocess.DEVNULL,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            env=env,
        )
    except OSError:
        if log_handle is not None:
            log_handle.close()
        return False
    if log_handle is not None:
        log_handle.close()
    # A direct daemon start may legitimately wait for a cold Chrome CDP endpoint
    # (bounded by the mux package's own CDP wait), so this poll must outlast that
    # wait. Short-circuiting on process death keeps a genuinely broken start from
    # burning the whole budget.
    deadline = time.monotonic() + _MUX_COLD_START_WAIT_SEC
    while time.monotonic() < deadline:
        if _mux_daemon_count_live() >= 1:
            return True
        if proc.poll() is not None:
            # Our spawn exited. That is NOT failure when a daemon is already owned:
            # concurrent cold starts (e.g. several lanes attaching at once) race, and
            # the loser intentionally exits with "mux daemon already owned by pid N".
            # Reporting that as failure denied attach for every losing lane even though
            # the shared mux was up — and each race appended megabytes to mux.log.
            return _mux_daemon_count_live() >= 1 or _socket_has_listener(
                mux_state_dir() / "cdmcp-mux.sock"
            )
        time.sleep(0.5)
    return _mux_daemon_count_live() >= 1


def ensure_mux_daemon_if_absent() -> bool:
    """Start the shared mux daemon when none is running.

    Safe under parallel attach: never stops, restarts, or kills an existing daemon.
    """
    if _mux_daemon_count_live() >= 1:
        return True
    return _start_mux_daemon_if_needed()


def plane_health_snapshot(
    *,
    epoch_match: bool = False,
    drift_pending: bool = False,
) -> PlaneHealthSnapshot:
    mux_count = _mux_daemon_count_live()
    orch_health, orch_state, mux_available = orchestrator_status()
    wave_leases = wave_active_leases()
    cluster_active = cluster_active_sessions()
    state = classify_state(
        mux_count=mux_count,
        orch_health=orch_health,
        orch_state=orch_state,
        mux_available=mux_available,
        orchestrator_listening=_orchestrator_daemon_listening(),
    )
    converge_action: str | None = None
    if (
        state in {PlaneHealthState.STALE, PlaneHealthState.FAILED_LATCHED}
        and wave_leases == 0
    ):
        converge_action = "converge_plane_if_idle"
    agent_rule = build_agent_rule(
        state,
        epoch_match=epoch_match,
        drift_pending=drift_pending,
        wave_leases=wave_leases,
    )
    return PlaneHealthSnapshot(
        state=state,
        mux_daemon_count=mux_count,
        orchestrator_state=orch_state,
        orchestrator_health=orch_health,
        mux_snapshot_available=mux_available,
        epoch_match=epoch_match,
        drift_pending=drift_pending,
        wave_leases=wave_leases,
        cluster_active=cluster_active,
        agent_rule=agent_rule,
        converge_action=converge_action,
    )


def _repair_additive_plane_services() -> None:
    """Start-only repair of the plane's additive components.

    Safe while lanes are running: ``_start_mux_daemon_if_needed`` starts at most one
    daemon and never touches an existing one, and ``ensure-browser-orchestrator.sh`` is
    fail-closed with ownership receipts (it refuses to kill any daemon that owns a live
    context or operation). Neither step applies pending drift, reaps, or restarts.
    """
    _start_mux_daemon_if_needed()
    ensure_script = (
        resolve_monorepo_root() / "scripts" / "dev" / "ensure-browser-orchestrator.sh"
    )
    if not ensure_script.is_file():
        return
    try:
        subprocess.run(
            ["bash", str(ensure_script)],
            capture_output=True,
            check=False,
            timeout=20.0,
            env={**os.environ, "MYRM_BROWSER_ORCHESTRATOR": "1"},
        )
    except (OSError, subprocess.TimeoutExpired):
        return


def converge_plane_if_idle() -> ConvergeReceipt:
    """Plane reset: reap → drift apply → mux → orchestrator.

    Full reset (drift apply + reap) only runs when no lane is active. While lanes are
    active it degrades to additive repair instead of skipping: the plane could not
    recover at all under load, so one lane's transient hiccup outlived every peer and
    forced a manual restart (the failure the product contract forbids). Additive repair
    cannot disturb a running lane, and destructive repair still waits for idle.
    """
    started = time.monotonic()
    wave_leases = wave_active_leases()
    cluster_active = cluster_active_sessions()
    under_load = wave_leases > 0 or cluster_active > 0

    if not try_acquire_converge_lock():
        return ConvergeReceipt(
            ok=False,
            action="skipped",
            detail="converge already in progress",
            elapsed_sec=time.monotonic() - started,
        )

    lock_dir = converge_lock_dir()
    try:
        if under_load:
            _repair_additive_plane_services()
            snap = plane_health_snapshot()
            ok = snap.state is PlaneHealthState.OBSERVABLE
            return ConvergeReceipt(
                ok=ok,
                action="additive_repaired" if ok else "additive_partial",
                detail=f"under_load wave_leases={wave_leases} cluster={cluster_active}; "
                f"{snap.agent_rule}",
                elapsed_sec=time.monotonic() - started,
            )

        reap_stale_plane_artifacts()
        root = resolve_monorepo_root()
        state_dir = plane_state_dir()
        try:
            from stack_mutation_policy import (
                apply_pending_drift_for_maintenance,
                pending_drift_exists,
            )

            if pending_drift_exists(state_dir):
                drift_result = apply_pending_drift_for_maintenance(
                    monorepo_root=root,
                    state_dir=state_dir,
                )
                if drift_result.action == "failed":
                    return ConvergeReceipt(
                        ok=False,
                        action="drift_apply_failed",
                        detail=drift_result.detail,
                        elapsed_sec=time.monotonic() - started,
                    )
        except ImportError:
            pass

        _repair_additive_plane_services()

        snap = plane_health_snapshot()
        ok = snap.state is PlaneHealthState.OBSERVABLE
        return ConvergeReceipt(
            ok=ok,
            action="converged" if ok else "partial",
            detail=snap.agent_rule,
            elapsed_sec=time.monotonic() - started,
        )
    finally:
        try:
            (lock_dir / "converge.pid").unlink(missing_ok=True)
            lock_dir.rmdir()
        except OSError:
            pass


def ensure_plane_before_probe(
    *,
    allow_converge: bool | None = None,
    epoch_match: bool = False,
    drift_pending: bool = False,
) -> PlaneHealthSnapshot:
    """Single pre-probe entry for context, launch-check, and attach preflight."""
    if allow_converge is None:
        allow_converge = os.environ.get("MYRM_PLANE_AUTO_CONVERGE", "1").strip() != "0"
    return ensure_plane_observable(
        allow_converge=allow_converge,
        epoch_match=epoch_match,
        drift_pending=drift_pending,
    )


def plane_next_action_for_snapshot(snap: PlaneHealthSnapshot) -> str | None:
    """Map non-OBSERVABLE plane to a launch-check token (UBDP-5)."""
    if snap.state is PlaneHealthState.OBSERVABLE:
        return None
    if snap.wave_leases > 0 or snap.cluster_active > 0:
        return "PLANE_DEGRADED_DEFER"
    return "PLANE_DEGRADED"


def ensure_plane_observable(
    *,
    allow_converge: bool = False,
    epoch_match: bool = False,
    drift_pending: bool = False,
) -> PlaneHealthSnapshot:
    reap_stale_plane_artifacts()
    if _mux_daemon_count_live() < 1:
        ensure_mux_daemon_if_absent()
    snap = plane_health_snapshot(epoch_match=epoch_match, drift_pending=drift_pending)
    if (
        allow_converge
        and snap.converge_action == "converge_plane_if_idle"
        and snap.state is not PlaneHealthState.OBSERVABLE
    ):
        converge_plane_if_idle()
        reap_stale_plane_artifacts()
        snap = plane_health_snapshot(
            epoch_match=epoch_match, drift_pending=drift_pending
        )
    return snap
