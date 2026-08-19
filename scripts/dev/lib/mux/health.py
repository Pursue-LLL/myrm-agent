"""Mux daemon health SSOT — zombie/dead/corrupt detection, reap, restart policy (UBDP-6).

[INPUT]
- cdmcp-mux state dir (daemon.lock, daemon.pid, Unix socket)
- mux.load.read_mux_status (parallel context / wave lease counts)

[OUTPUT]
- evaluate_mux_health() -> MuxHealthVerdict
- reap_unhealthy_mux_daemon() -> MuxReapReceipt
- should_allow_mux_restart() -> bool

[POS]
Dev Gate infra layer. Consumed by plane_health, chrome-e2e-preflight, doctor.
"""

from __future__ import annotations

import argparse
import json
import os
import signal
import sys
import time
from dataclasses import dataclass
from enum import Enum
from pathlib import Path

if __package__ in (None, ""):
    _lib_root = str(Path(__file__).resolve().parent.parent)
    if _lib_root not in sys.path:
        sys.path.insert(0, _lib_root)

from e2e_core.real_user_home import real_user_home
from mux.load import mux_context_count, read_mux_status, wave_lease_count
from mux.responsive_probe import mux_timeout_effective, mux_tools_list_responsive

DAEMON_LOCK_NAME = "daemon.lock"
DAEMON_PID_NAME = "daemon.pid"
DEFAULT_SOCKET_NAME = "cdmcp-mux.sock"
DEFAULT_EXPECTED_TIMEOUT_MS = 180_000
REAP_GRACE_SEC = 0.5
REAP_KILL_WAIT_SEC = 2.0


class MuxDaemonState(str, Enum):
    HEALTHY = "HEALTHY"
    ZOMBIE_ALIVE_NO_SOCKET = "ZOMBIE_ALIVE_NO_SOCKET"
    DEAD = "DEAD"
    CORRUPT_PID = "CORRUPT_PID"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class MuxHealthVerdict:
    state: MuxDaemonState
    owner_pid: int | None
    socket_path: str
    probe_ok: bool
    agent_rule: str
    detail: str


@dataclass(frozen=True, slots=True)
class MuxReapReceipt:
    reaped: bool
    pid: int | None
    reason: str
    detail: str


def mux_state_dir() -> Path:
    override = os.getenv("CDMCP_MUX_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return real_user_home() / ".local" / "state" / "cdmcp-mux"


def mux_socket_path(*, state_dir: Path | None = None) -> str:
    override = os.getenv("CDMCP_MUX_SOCKET", "").strip()
    if override:
        return override
    base = state_dir if state_dir is not None else mux_state_dir()
    return str(base / DEFAULT_SOCKET_NAME)


def _process_alive(pid: int) -> bool:
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


def _read_owner_pid(lock_path: Path) -> int | None:
    if not lock_path.is_file():
        return None
    try:
        payload = json.loads(lock_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, dict):
        return None
    raw_pid = payload.get("pid")
    if isinstance(raw_pid, int) and raw_pid > 0:
        return raw_pid
    if isinstance(raw_pid, str) and raw_pid.isdigit():
        return int(raw_pid)
    return None


def _read_pid_stamp(pid_path: Path) -> int | None:
    if not pid_path.is_file():
        return None
    try:
        raw = pid_path.read_text(encoding="utf-8").strip()
    except OSError:
        return None
    if not raw.isdigit():
        return None
    pid = int(raw)
    return pid if pid > 0 else None


def _socket_exists(socket_path: str) -> bool:
    return bool(socket_path) and os.path.exists(socket_path)


def _probe_responsive(*, state_dir: Path, socket_path: str) -> bool:
    expected_ms = int(
        os.getenv("CDMCP_MUX_REQUEST_TIMEOUT_MS", str(DEFAULT_EXPECTED_TIMEOUT_MS))
    )
    if mux_timeout_effective(
        state_dir=state_dir,
        expected_ms=expected_ms,
        socket_path=socket_path,
        probe_timeout_sec=4.0,
    ):
        return True
    if not _socket_exists(socket_path):
        return False
    return mux_tools_list_responsive(timeout_sec=4.0)


def evaluate_mux_health(
    *,
    state_dir: Path | None = None,
    socket_path: str | None = None,
) -> MuxHealthVerdict:
    base = state_dir if state_dir is not None else mux_state_dir()
    sock = socket_path if socket_path is not None else mux_socket_path(state_dir=base)
    lock_path = base / DAEMON_LOCK_NAME
    pid_path = base / DAEMON_PID_NAME

    owner_pid = _read_owner_pid(lock_path)
    stamp_pid = _read_pid_stamp(pid_path)
    socket_present = _socket_exists(sock)

    if stamp_pid is not None and owner_pid is not None and stamp_pid != owner_pid:
        return MuxHealthVerdict(
            state=MuxDaemonState.CORRUPT_PID,
            owner_pid=owner_pid,
            socket_path=sock,
            probe_ok=False,
            agent_rule="MUX_CORRUPT_PID: reap stale mux stamps then ./myrm restart --chrome",
            detail=f"daemon.pid={stamp_pid} daemon.lock.pid={owner_pid}",
        )

    if stamp_pid is not None and not str(stamp_pid).isdigit():
        return MuxHealthVerdict(
            state=MuxDaemonState.CORRUPT_PID,
            owner_pid=owner_pid,
            socket_path=sock,
            probe_ok=False,
            agent_rule="MUX_CORRUPT_PID: reap stale mux stamps then ./myrm restart --chrome",
            detail="daemon.pid is not numeric",
        )

    candidate_pid = owner_pid if owner_pid is not None else stamp_pid
    pid_alive = candidate_pid is not None and _process_alive(candidate_pid)

    if pid_alive and not socket_present:
        return MuxHealthVerdict(
            state=MuxDaemonState.ZOMBIE_ALIVE_NO_SOCKET,
            owner_pid=candidate_pid,
            socket_path=sock,
            probe_ok=False,
            agent_rule=(
                f"MUX_ZOMBIE_REAP: orphan mux pid={candidate_pid} alive without socket; "
                "auto-reap then ./myrm restart --chrome"
            ),
            detail="pid alive, unix socket missing",
        )

    if not pid_alive and not socket_present:
        status = read_mux_status(force=True)
        if status is None or status.get("ok") is not True:
            return MuxHealthVerdict(
                state=MuxDaemonState.DEAD,
                owner_pid=candidate_pid,
                socket_path=sock,
                probe_ok=False,
                agent_rule="MUX_DEAD: ./myrm restart --chrome",
                detail="no pid, no socket, mux status not ok",
            )

    probe_ok = _probe_responsive(state_dir=base, socket_path=sock)
    if probe_ok:
        return MuxHealthVerdict(
            state=MuxDaemonState.HEALTHY,
            owner_pid=candidate_pid,
            socket_path=sock,
            probe_ok=True,
            agent_rule="",
            detail="socket responsive",
        )

    if pid_alive:
        return MuxHealthVerdict(
            state=MuxDaemonState.ZOMBIE_ALIVE_NO_SOCKET,
            owner_pid=candidate_pid,
            socket_path=sock,
            probe_ok=False,
            agent_rule=(
                f"MUX_ZOMBIE_REAP: mux pid={candidate_pid} unresponsive; "
                "auto-reap then ./myrm restart --chrome"
            ),
            detail="pid alive, probe failed",
        )

    return MuxHealthVerdict(
        state=MuxDaemonState.DEAD,
        owner_pid=candidate_pid,
        socket_path=sock,
        probe_ok=False,
        agent_rule="MUX_DEAD: ./myrm restart --chrome",
        detail="probe failed, pid not alive",
    )


def _terminate_pid(pid: int) -> bool:
    if not _process_alive(pid):
        return False
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError:
        return False
    deadline = time.monotonic() + REAP_KILL_WAIT_SEC
    while time.monotonic() < deadline:
        if not _process_alive(pid):
            return True
        time.sleep(REAP_GRACE_SEC)
    try:
        os.kill(pid, signal.SIGKILL)
    except OSError:
        return not _process_alive(pid)
    return not _process_alive(pid)


def _unlink_stale_stamps(*, base: Path, lock_path: Path, pid_path: Path) -> list[str]:
    removed: list[str] = []
    for path in (lock_path, pid_path):
        if path.is_file():
            try:
                path.unlink(missing_ok=True)
                removed.append(path.name)
            except OSError as exc:
                removed.append(f"{path.name}_err={exc}")
    start_lock = base / "daemon.start.lock"
    if start_lock.is_dir():
        try:
            start_lock.rmdir()
        except OSError:
            pass
    return removed


def reap_unhealthy_mux_daemon(
    *,
    state_dir: Path | None = None,
    verdict: MuxHealthVerdict | None = None,
) -> MuxReapReceipt:
    base = state_dir if state_dir is not None else mux_state_dir()
    lock_path = base / DAEMON_LOCK_NAME
    pid_path = base / DAEMON_PID_NAME
    current = verdict if verdict is not None else evaluate_mux_health(state_dir=base)

    if current.state is MuxDaemonState.HEALTHY:
        return MuxReapReceipt(
            reaped=False,
            pid=current.owner_pid,
            reason="healthy",
            detail=current.detail,
        )

    if current.state not in {
        MuxDaemonState.ZOMBIE_ALIVE_NO_SOCKET,
        MuxDaemonState.DEAD,
        MuxDaemonState.CORRUPT_PID,
    }:
        return MuxReapReceipt(
            reaped=False,
            pid=current.owner_pid,
            reason=current.state.value,
            detail=current.detail,
        )

    pid = current.owner_pid
    reaped = False
    if pid is not None and _process_alive(pid):
        reaped = _terminate_pid(pid)

    stamp_removed = _unlink_stale_stamps(
        base=base, lock_path=lock_path, pid_path=pid_path
    )
    detail_parts = [current.detail]
    if stamp_removed:
        detail_parts.append(f"removed={','.join(stamp_removed)}")
    if reaped:
        detail_parts.append(f"terminated_pid={pid}")

    return MuxReapReceipt(
        reaped=reaped or bool(stamp_removed),
        pid=pid,
        reason=current.state.value,
        detail=";".join(detail_parts),
    )


def should_allow_mux_restart(
    verdict: MuxHealthVerdict,
    *,
    wave_leases: int,
    mux_contexts: int,
) -> bool:
    """Return True when mux daemon restart must proceed (not blocked for peer protection)."""
    if verdict.state in {
        MuxDaemonState.ZOMBIE_ALIVE_NO_SOCKET,
        MuxDaemonState.DEAD,
        MuxDaemonState.CORRUPT_PID,
    }:
        return True
    if verdict.state is MuxDaemonState.UNKNOWN:
        return True
    if verdict.state is MuxDaemonState.HEALTHY:
        if wave_leases > 0 or mux_contexts > 0:
            return False
        return True
    return True


def parallel_load_blocks_mux_restart() -> bool:
    """Shell helper: exit 0 when restart must be blocked, 1 when allowed."""
    verdict = evaluate_mux_health()
    status = read_mux_status(force=True)
    contexts = mux_context_count(status)
    leases = wave_lease_count(status)
    allow = should_allow_mux_restart(
        verdict, wave_leases=leases, mux_contexts=contexts
    )
    return not allow


def main() -> int:
    parser = argparse.ArgumentParser(description="Mux daemon health SSOT (UBDP-6)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("evaluate", help="Print JSON MuxHealthVerdict")
    sub.add_parser("reap", help="Reap unhealthy mux daemon")
    sub.add_parser(
        "restart-blocked",
        help="Exit 0 if parallel load blocks restart, 1 if restart allowed",
    )

    args = parser.parse_args()
    if args.cmd == "evaluate":
        verdict = evaluate_mux_health()
        print(
            json.dumps(
                {
                    "state": verdict.state.value,
                    "owner_pid": verdict.owner_pid,
                    "socket_path": verdict.socket_path,
                    "probe_ok": verdict.probe_ok,
                    "agent_rule": verdict.agent_rule,
                    "detail": verdict.detail,
                }
            )
        )
        return 0
    if args.cmd == "reap":
        receipt = reap_unhealthy_mux_daemon()
        print(
            json.dumps(
                {
                    "reaped": receipt.reaped,
                    "pid": receipt.pid,
                    "reason": receipt.reason,
                    "detail": receipt.detail,
                }
            )
        )
        return 0
    if args.cmd == "restart-blocked":
        return 0 if parallel_load_blocks_mux_restart() else 1
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
