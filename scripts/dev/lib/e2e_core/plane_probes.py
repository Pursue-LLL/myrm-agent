"""Read-only observations of the browser data plane: state dir, pid and socket liveness, leases, sessions, orchestrator status.

[INPUT]
- `stack_mutation_policy` wave leases, `dev_gate.status` active sessions, `browser_orchestrator` snapshot (POS: who else is using the plane and what the orchestrator reports)
- `e2e_core.real_user_home::real_user_home` (POS: the real home regardless of HOME)

[OUTPUT]
- `plane_state_dir()` / `resolve_monorepo_root()` / `resolve_node_executable()`: where dev state, the checkout and `node` live
- `pid_alive()` / `socket_listener_probe()`: liveness; `None` from the socket probe means "unknowable, do not act"
- `wave_active_leases()` / `cluster_active_sessions()` / `orchestrator_status()`: load and orchestrator verdicts that fall back to zero / UNKNOWN when a source is absent

[POS]
Dev Gate infra layer. Leaf module of `plane_health.py`; nothing here starts, stops or removes anything.
"""

from __future__ import annotations

import os
import shutil
import subprocess
from pathlib import Path

from e2e_core.real_user_home import real_user_home


def plane_state_dir() -> Path:
    override = os.getenv("MYRM_STATE_DIR", "").strip()
    if override:
        return Path(override)
    return real_user_home() / ".local" / "state" / "myrm-dev"


def pid_alive(pid: int) -> bool:
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


def socket_listener_probe(socket_path: Path) -> bool | None:
    """Tri-state socket listener probe: True, False, or None when unknowable.

    ``None`` means the probe itself failed (e.g. lsof timed out under load). Callers that
    decide whether to *destroy* something must treat ``None`` as "do not act": a probe
    error is not "no listener", and acting on it would remove a live daemon's socket
    and then reap that daemon, spiralling the whole cluster.
    """
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
        return None
    # A non-zero lsof exit with no stdout means lsof ran and found nothing listening.
    if proc.returncode != 0 and not proc.stdout.strip():
        return None if proc.returncode not in (0, 1) else False
    for line in proc.stdout.splitlines():
        text = line.strip()
        if not text:
            continue
        try:
            if pid_alive(int(text)):
                return True
        except ValueError:
            continue
    return False


def resolve_monorepo_root() -> Path:
    override = os.getenv("MYRM_MONOREPO_ROOT", "").strip()
    if override:
        return Path(override)
    return Path(__file__).resolve().parents[5]


def wave_active_leases() -> int:
    try:
        from stack_mutation_policy import wave_shared_active_lease_count

        return wave_shared_active_lease_count(resolve_monorepo_root())
    except ImportError:
        return 0


def cluster_active_sessions() -> int:
    try:
        from dev_gate.status import dev_gate_status

        payload = dev_gate_status()
        counts = (payload.get("shared_active"), payload.get("private_active"))
        return max(0, sum(count for count in counts if isinstance(count, int)))
    except (ImportError, OSError, RuntimeError, TypeError, ValueError):
        return 0


def orchestrator_status() -> tuple[str, str, bool]:
    try:
        from browser_orchestrator import browser_orchestrator_snapshot

        snap = browser_orchestrator_snapshot()
    except ImportError:
        return "UNKNOWN", "UNKNOWN", False
    health = str(snap.get("health") or "UNKNOWN")
    daemon_state = str(snap.get("daemon_state") or "UNKNOWN")
    mux_available = snap.get("mux_snapshot_available") is True
    return health, daemon_state, mux_available


def resolve_node_executable() -> str | None:
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
