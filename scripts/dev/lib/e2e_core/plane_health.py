"""Unified Browser Data Plane health — SSOT for mux/orchestrator/epoch observability.

[INPUT]
- runtime_probe.probe_runtime_context (mux daemon count)
- browser_orchestrator.browser_orchestrator_snapshot (orchestrator state)
- stack_mutation_policy (idle drift apply)

[OUTPUT]
- reap_stale_plane_artifacts() / converge_plane_if_idle() / plane_health_snapshot()
- ensure_mux_daemon_if_absent() / _start_mux_daemon_if_needed() — idempotent mux cold start (never restarts live daemons)
- _try_acquire_converge_lock() breaks stale /tmp/plane-converge.lockdir (>120s)
- Consumed by e2e-context (dataPlane block) and attach fast-fail (R032)

[POS]
Dev Gate infra layer. Idle converge never mutates stack during active wave leases;
mux cold-start via ensure_mux_daemon_if_absent is lease-safe (start-only, never kills peers).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import time
from dataclasses import asdict, dataclass
from enum import Enum
from pathlib import Path
from typing import Final

from e2e_core.real_user_home import real_user_home
from e2e_core.runtime_identity import (
    _default_chrome_data_dir,
    _mux_state_dir,
    _resolve_e2e_port,
)

_PLANE_REAP_LOG: Final[str] = "plane-health-reap.jsonl"
_CONVERGE_LOCK: Final[str] = "plane-converge.lockdir"
_CONVERGE_LOCK_STALE_SEC: Final[float] = 120.0
_IDLE_CONVERGE_WALL_SEC: Final[float] = 45.0


class PlaneHealthState(str, Enum):
    OBSERVABLE = "OBSERVABLE"
    DEGRADED = "DEGRADED"
    STALE = "STALE"
    FAILED_LATCHED = "FAILED_LATCHED"
    RECOVERING = "RECOVERING"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True)
class ReapReceipt:
    mux_pid_removed: bool
    mux_socket_removed: bool
    orchestrator_recycled: bool
    detail: str


@dataclass(frozen=True)
class ConvergeReceipt:
    ok: bool
    action: str
    detail: str
    elapsed_sec: float


@dataclass(frozen=True)
class PlaneHealthSnapshot:
    state: PlaneHealthState
    mux_daemon_count: int
    orchestrator_state: str
    orchestrator_health: str
    mux_snapshot_available: bool
    epoch_match: bool
    drift_pending: bool
    wave_leases: int
    cluster_active: int
    agent_rule: str
    converge_action: str | None


def _state_dir() -> Path:
    override = os.getenv("MYRM_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return real_user_home() / ".local" / "state" / "myrm-dev"


def _reap_log_path() -> Path:
    path = _state_dir() / _PLANE_REAP_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_reap_log(payload: dict[str, object]) -> None:
    line = json.dumps({**payload, "ts": time.time()}, separators=(",", ":"))
    try:
        with _reap_log_path().open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


def _pid_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError:
        return False
    return True


def _socket_has_listener(socket_path: Path) -> bool:
    if not socket_path.is_socket():
        return False
    try:
        proc = subprocess.run(
            ["lsof", "-t", "--", str(socket_path)],
            capture_output=True,
            text=True,
            check=False,
            timeout=2.0,
        )
    except (OSError, subprocess.TimeoutExpired):
        return False
    for line in proc.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            if _pid_alive(int(text)):
                return True
        except ValueError:
            continue
    return False


def _resolve_monorepo_root() -> Path:
    override = os.getenv("MYRM_MONOREPO_ROOT", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[5]


def _wave_active_leases() -> int:
    try:
        from stack_mutation_policy import wave_shared_active_lease_count

        return wave_shared_active_lease_count(_resolve_monorepo_root())
    except ImportError:
        return 0


def _cluster_active_sessions() -> int:
    try:
        from dev_gate.status import dev_gate_status

        payload = dev_gate_status()
        shared = int(payload.get("shared_active") or 0)
        private = int(payload.get("private_active") or 0)
        return max(0, shared + private)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return 0


def _mux_daemon_count_live() -> int:
    try:
        from e2e_core.runtime_probe import probe_runtime_context

        ctx = probe_runtime_context()
        return int(ctx.get("mux_daemon_count") or 0)
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return 0


def _orchestrator_status() -> tuple[str, str, bool]:
    try:
        from browser_orchestrator import browser_orchestrator_snapshot

        snap = browser_orchestrator_snapshot()
    except ImportError:
        return "UNKNOWN", "UNKNOWN", False
    health = str(snap.get("health") or "UNKNOWN")
    daemon_state = str(snap.get("daemon_state") or "UNKNOWN")
    mux_available = snap.get("mux_snapshot_available") is True
    return health, daemon_state, mux_available


def reap_stale_plane_artifacts() -> ReapReceipt:
    """Remove dead mux pid files and orphan sockets before probing."""
    mux_pid_removed = False
    mux_socket_removed = False
    orchestrator_recycled = False
    details: list[str] = []

    try:
        from mux.health import (
            MuxDaemonState,
            evaluate_mux_health,
            reap_unhealthy_mux_daemon,
        )

        verdict = evaluate_mux_health()
        if verdict.state in {
            MuxDaemonState.ZOMBIE_ALIVE_NO_SOCKET,
            MuxDaemonState.CORRUPT_PID,
        }:
            zombie_receipt = reap_unhealthy_mux_daemon(verdict=verdict)
            if zombie_receipt.reaped:
                mux_pid_removed = True
                details.append(f"mux_zombie_reaped={zombie_receipt.detail}")
    except ImportError:
        pass

    mux_dir = _mux_state_dir()
    pid_path = mux_dir / "daemon.pid"
    socket_path = mux_dir / "cdmcp-mux.sock"

    if pid_path.is_file():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pid = 0
        if pid > 0 and not _pid_alive(pid):
            try:
                pid_path.unlink(missing_ok=True)
                mux_pid_removed = True
                details.append(f"mux_stale_pid={pid}")
            except OSError as exc:
                details.append(f"mux_pid_unlink_failed={exc}")

    if socket_path.exists() and not _socket_has_listener(socket_path):
        try:
            socket_path.unlink(missing_ok=True)
            mux_socket_removed = True
            details.append("mux_orphan_socket")
        except OSError as exc:
            details.append(f"mux_socket_unlink_failed={exc}")

    health, daemon_state, _ = _orchestrator_status()
    if (
        daemon_state == "FAILED"
        and _wave_active_leases() == 0
        and _cluster_active_sessions() == 0
    ):
        latch_reset = False
        try:
            from browser_orchestrator.client import BrowserOrchestratorClient

            client = BrowserOrchestratorClient()
            reset_payload = client.reset_failure_latch_if_idle()
            latch_reset = reset_payload.get("ok") is True
            if latch_reset:
                details.append(
                    f"orchestrator_latch_reset={reset_payload.get('detail', 'ok')}"
                )
        except (
            ImportError,
            OSError,
            RuntimeError,
            TimeoutError,
            TypeError,
            ValueError,
        ) as exc:
            details.append(f"orchestrator_latch_reset_err={exc}")
        health, daemon_state, _ = _orchestrator_status()
        if latch_reset and daemon_state != "FAILED":
            receipt = ReapReceipt(
                mux_pid_removed=mux_pid_removed,
                mux_socket_removed=mux_socket_removed,
                orchestrator_recycled=False,
                detail=";".join(details) if details else "orchestrator_latch_reset",
            )
            _append_reap_log(asdict(receipt))
            return receipt
        ensure_script = (
            _resolve_monorepo_root()
            / "scripts"
            / "dev"
            / "ensure-browser-orchestrator.sh"
        )
        if ensure_script.is_file():
            try:
                proc = subprocess.run(
                    ["bash", str(ensure_script)],
                    capture_output=True,
                    text=True,
                    check=False,
                    timeout=20.0,
                    env={**os.environ, "MYRM_BROWSER_ORCHESTRATOR": "1"},
                )
                if proc.returncode == 0:
                    orchestrator_recycled = True
                    details.append("orchestrator_ensure_ok")
                else:
                    tail = (proc.stderr or proc.stdout or "").strip()[-200:]
                    details.append(f"orchestrator_ensure_rc={proc.returncode}:{tail}")
            except (OSError, subprocess.TimeoutExpired) as exc:
                details.append(f"orchestrator_ensure_err={exc}")
        elif health == "FAILED":
            details.append("orchestrator_failed_idle")

    receipt = ReapReceipt(
        mux_pid_removed=mux_pid_removed,
        mux_socket_removed=mux_socket_removed,
        orchestrator_recycled=orchestrator_recycled,
        detail=";".join(details) if details else "noop",
    )
    _append_reap_log(asdict(receipt))
    return receipt


def _resolve_node_executable() -> str | None:
    override = os.getenv("MYRM_NODE_BIN", "").strip()
    if override and Path(override).is_file():
        return override
    found = shutil.which("node")
    if found:
        return found
    for candidate in (Path("/opt/homebrew/bin/node"), Path("/usr/local/bin/node")):
        if candidate.is_file():
            return str(candidate)
    return None


def _start_mux_daemon_if_needed() -> bool:
    """Start mux with the same env contract as chrome-e2e-preflight _start_mux_daemon."""
    if _mux_daemon_count_live() >= 1:
        return True
    root = _resolve_monorepo_root()
    mux_bin = (
        root
        / "scripts"
        / "dev"
        / "cdmcp-mux-autoconnect"
        / "bin"
        / "cdmcp-mux-autoconnect.mjs"
    )
    node = _resolve_node_executable()
    if node is None or not mux_bin.is_file():
        return False
    mux_dir = _mux_state_dir()
    mux_dir.mkdir(parents=True, exist_ok=True)
    mux_socket = mux_dir / "cdmcp-mux.sock"
    chrome_data = _default_chrome_data_dir()
    request_timeout = os.getenv("CDMCP_MUX_REQUEST_TIMEOUT_MS", "180000").strip() or "180000"
    node_dir = str(Path(node).parent)
    current_path = os.environ.get("PATH", "")
    fixed_path = f"{node_dir}:{current_path}" if node_dir not in current_path.split(":") else current_path
    env = {
        **os.environ,
        "PATH": fixed_path,
        "CHROME_DATA_DIR": str(chrome_data),
        "MYRM_CHROME_E2E_DATA_DIR": str(chrome_data),
        "MYRM_CHROME_E2E_PORT": str(_resolve_e2e_port()),
        "CDMCP_MUX_STATE_DIR": str(mux_dir),
        "CDMCP_MUX_SOCKET": str(mux_socket),
        "CDMCP_MUX_REQUEST_TIMEOUT_MS": request_timeout,
        "MCP_MUX_UPSTREAM_STDERR": os.getenv("MCP_MUX_UPSTREAM_STDERR", "1"),
    }
    log_file = mux_dir / "mux.log"
    try:
        log_handle = log_file.open("a", encoding="utf-8")
    except OSError:
        log_handle = None
    try:
        subprocess.Popen(
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
    deadline = time.monotonic() + 15.0
    while time.monotonic() < deadline:
        if _mux_daemon_count_live() >= 1:
            return True
        time.sleep(0.5)
    return False


def ensure_mux_daemon_if_absent() -> bool:
    """Start the shared mux daemon when none is running.

    Safe under parallel attach: never stops, restarts, or kills an existing daemon.
    """
    if _mux_daemon_count_live() >= 1:
        return True
    return _start_mux_daemon_if_needed()


def _classify_state(
    *,
    mux_count: int,
    orch_health: str,
    orch_state: str,
    mux_available: bool,
) -> PlaneHealthState:
    if orch_state == "RECOVERING" or orch_health == "RECOVERING":
        return PlaneHealthState.RECOVERING
    if orch_state == "FAILED" or orch_health == "FAILED":
        return PlaneHealthState.FAILED_LATCHED
    if mux_count < 1 or not mux_available:
        return PlaneHealthState.STALE
    if orch_health in {"DEGRADED", "UNKNOWN"}:
        return PlaneHealthState.DEGRADED
    if orch_health == "READY" and mux_count >= 1 and mux_available:
        return PlaneHealthState.OBSERVABLE
    return PlaneHealthState.UNKNOWN


def _build_agent_rule(
    state: PlaneHealthState,
    *,
    epoch_match: bool,
    drift_pending: bool,
    wave_leases: int,
) -> str:
    if state is PlaneHealthState.OBSERVABLE and epoch_match:
        return "READY: cluster ready for chrome_e2e launch"
    if state is PlaneHealthState.OBSERVABLE:
        return (
            "PLANE_OBSERVABLE: mux/orchestrator healthy — read epoch_match from "
            "e2e-context for SHARED launch routing"
        )
    if not epoch_match and drift_pending and wave_leases == 0:
        return (
            "DRIFT_PENDING: wave idle — run ./myrm restart --chrome to apply workspace "
            "epoch, or declare PRIVATE for workspace backend code; do not stop other pytest"
        )
    if state in {PlaneHealthState.STALE, PlaneHealthState.FAILED_LATCHED}:
        if wave_leases == 0:
            return (
                "PLANE_STALE: mux/orchestrator unhealthy — run ./myrm restart --chrome "
                "or wait for plane converge; verify-api does not heal mux/orch; "
                "do not stop other pytest"
            )
        return (
            "PLANE_DEGRADED: parallel active — plane heal deferred until wave idle; "
            "do not stop other pytest"
        )
    if state is PlaneHealthState.RECOVERING:
        return "PLANE_RECOVERING: wait for orchestrator recovery or retry attach"
    return "PLANE_UNKNOWN: run ./myrm e2e-context json and execute agent_rule"


def plane_health_snapshot(
    *,
    epoch_match: bool = False,
    drift_pending: bool = False,
) -> PlaneHealthSnapshot:
    mux_count = _mux_daemon_count_live()
    orch_health, orch_state, mux_available = _orchestrator_status()
    wave_leases = _wave_active_leases()
    cluster_active = _cluster_active_sessions()
    state = _classify_state(
        mux_count=mux_count,
        orch_health=orch_health,
        orch_state=orch_state,
        mux_available=mux_available,
    )
    converge_action: str | None = None
    if (
        state in {PlaneHealthState.STALE, PlaneHealthState.FAILED_LATCHED}
        and wave_leases == 0
    ):
        converge_action = "converge_plane_if_idle"
    agent_rule = _build_agent_rule(
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


def _converge_lock_dir() -> Path:
    return Path("/tmp") / _CONVERGE_LOCK


def _try_acquire_converge_lock() -> bool:
    """Acquire idle converge lock; break stale lockdirs left by crashed convergers."""
    lock_dir = _converge_lock_dir()
    pid_file = lock_dir / "converge.pid"
    try:
        lock_dir.mkdir(exist_ok=False)
        try:
            pid_file.write_text(str(os.getpid()), encoding="utf-8")
        except OSError:
            pass
        return True
    except FileExistsError:
        # Check if the process holding the lock is dead
        is_dead = False
        try:
            if pid_file.is_file():
                raw_pid = pid_file.read_text(encoding="utf-8").strip()
                if raw_pid.isdigit():
                    pid = int(raw_pid)
                    try:
                        os.kill(pid, 0)
                    except ProcessLookupError:
                        is_dead = True
                    except (PermissionError, OSError):
                        pass
        except OSError:
            pass

        try:
            age_sec = time.time() - lock_dir.stat().st_mtime
        except OSError:
            return False
        if not is_dead and age_sec < _CONVERGE_LOCK_STALE_SEC:
            return False
        try:
            if pid_file.is_file():
                pid_file.unlink(missing_ok=True)
            lock_dir.rmdir()
        except OSError:
            return False
        try:
            lock_dir.mkdir(exist_ok=False)
            try:
                pid_file.write_text(str(os.getpid()), encoding="utf-8")
            except OSError:
                pass
            return True
        except FileExistsError:
            return False


def converge_plane_if_idle() -> ConvergeReceipt:
    """Idle-only plane reset: reap → drift apply → mux → orchestrator."""
    started = time.monotonic()
    wave_leases = _wave_active_leases()
    cluster_active = _cluster_active_sessions()
    if wave_leases > 0 or cluster_active > 0:
        return ConvergeReceipt(
            ok=False,
            action="skipped",
            detail=f"active wave_leases={wave_leases} cluster={cluster_active}",
            elapsed_sec=time.monotonic() - started,
        )

    if not _try_acquire_converge_lock():
        return ConvergeReceipt(
            ok=False,
            action="skipped",
            detail="converge already in progress",
            elapsed_sec=time.monotonic() - started,
        )

    lock_dir = _converge_lock_dir()
    try:
        reap_stale_plane_artifacts()
        root = _resolve_monorepo_root()
        state_dir = _state_dir()
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

        _start_mux_daemon_if_needed()
        ensure_script = root / "scripts" / "dev" / "ensure-browser-orchestrator.sh"
        if ensure_script.is_file():
            subprocess.run(
                ["bash", str(ensure_script)],
                capture_output=True,
                check=False,
                timeout=20.0,
                env={**os.environ, "MYRM_BROWSER_ORCHESTRATOR": "1"},
            )

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
