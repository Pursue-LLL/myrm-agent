"""Keep the plane's artifacts bounded: reap dead mux pid files and orphan sockets, recycle a failed orchestrator while idle, cap the mux log.

[INPUT]
- `mux.health` verdicts, `e2e_core.plane_probes` liveness probes and idle checks, `e2e_core.browser_epoch::mux_state_dir`
- `scripts/dev/ensure-browser-orchestrator.sh` (POS: fail-closed orchestrator ensure with ownership receipts)

[OUTPUT]
- `reap_stale_plane_artifacts()` → `ReapReceipt`, appended to `plane-health-reap.jsonl`
- `bound_log_growth()`: reset an oversize `mux.log` before a cold start so the daemon log cannot grow without limit

[POS]
Dev Gate infra layer. Removes only artifacts whose owner is provably gone; a probe that cannot decide never triggers a removal.
"""

from __future__ import annotations

import json
import os
import subprocess
import time
from dataclasses import asdict
from pathlib import Path
from typing import Final

from e2e_core.browser_epoch import mux_state_dir
from e2e_core.plane_probes import (
    cluster_active_sessions,
    orchestrator_status,
    pid_alive,
    plane_state_dir,
    resolve_monorepo_root,
    socket_listener_probe,
    wave_active_leases,
)
from e2e_core.plane_state import ReapReceipt

_PLANE_REAP_LOG: Final[str] = "plane-health-reap.jsonl"


def _reap_log_path() -> Path:
    path = plane_state_dir() / _PLANE_REAP_LOG
    path.parent.mkdir(parents=True, exist_ok=True)
    return path


def _append_reap_log(payload: dict[str, object]) -> None:
    line = json.dumps({**payload, "ts": time.time()}, separators=(",", ":"))
    try:
        with _reap_log_path().open("a", encoding="utf-8") as handle:
            handle.write(line + "\n")
    except OSError:
        pass


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

    mux_dir = mux_state_dir()
    pid_path = mux_dir / "daemon.pid"
    socket_path = mux_dir / "cdmcp-mux.sock"

    if pid_path.is_file():
        try:
            pid = int(pid_path.read_text(encoding="utf-8").strip())
        except (OSError, ValueError):
            pid = 0
        if pid > 0 and not pid_alive(pid):
            try:
                pid_path.unlink(missing_ok=True)
                mux_pid_removed = True
                details.append(f"mux_stale_pid={pid}")
            except OSError as exc:
                details.append(f"mux_pid_unlink_failed={exc}")

    if socket_path.exists() and socket_listener_probe(socket_path) is False:
        try:
            socket_path.unlink(missing_ok=True)
            mux_socket_removed = True
            details.append("mux_orphan_socket")
        except OSError as exc:
            details.append(f"mux_socket_unlink_failed={exc}")

    health, daemon_state, _ = orchestrator_status()
    if (
        daemon_state == "FAILED"
        and wave_active_leases() == 0
        and cluster_active_sessions() == 0
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
        health, daemon_state, _ = orchestrator_status()
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
            resolve_monorepo_root()
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


# mux.log is appended to continuously with no rotation; cap it so a long-lived workspace
# cannot grow the daemon log without bound (observed 409 MB).
_MUX_LOG_MAX_BYTES: Final[int] = 64 * 1024 * 1024


def bound_log_growth(log_file: Path) -> None:
    """Keep the mux daemon log bounded.

    mux.log has no rotation and the daemon appends continuously (measured ~18 KB/min even
    idle, far more while lanes race to cold-start); it had reached 409 MB with each new
    spawn appending to the same huge file, and derived errors files grow unbounded too.
    Reset it once past the cap so disk use cannot grow without limit. Best-effort: a log
    that cannot be trimmed must never block an attach.
    """
    try:
        if log_file.stat().st_size < _MUX_LOG_MAX_BYTES:
            return
        log_file.write_text("", encoding="utf-8")
    except OSError:
        return
