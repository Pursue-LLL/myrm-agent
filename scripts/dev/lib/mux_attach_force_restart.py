"""Force-restart mux daemon during attach-mode E2E when new_page hangs under parallel load."""

from __future__ import annotations

import fcntl
import os
import subprocess
import time
from collections.abc import Iterator
from contextlib import contextmanager
from pathlib import Path

ATTACH_RESTART_COOLDOWN_SEC: float = 45.0
ATTACH_RESTART_BLOCKED_TOKEN: str = "MUX_ATTACH_RESTART_BLOCKED_PARALLEL"


def _desktop_soak_signoff_parallel_attach_restart_ok() -> bool:
    """R265: desktop leg soak must heal mux attach under active wave leases."""
    return os.environ.get("E2E_SIGNOFF", "").strip() == "1" and os.environ.get(
        "MYRM_E2E_DESKTOP_SOAK", ""
    ).strip() in ("1", "true", "yes")


def _parallel_load_blocks_attach_restart() -> bool:
    """P0-B: active mux contexts / wave leases block global daemon restart."""
    try:
        from mux_load import snapshot_mux_load

        load = snapshot_mux_load(force=True)
        if max(0, load.mux_contexts, load.wave_leases) > 0:
            return True
    except (ImportError, OSError, TypeError, ValueError):
        pass
    try:
        from chrome_mcp_client import _parallel_mux_peer_count

        return _parallel_mux_peer_count() >= 2
    except (ImportError, OSError, TypeError, ValueError):
        return False


def _preflight_timeout_sec() -> float:
    """Scale attach-restart preflight under parallel signoff (R121)."""
    try:
        import sys
        from pathlib import Path

        lib_dir = Path(__file__).resolve().parent
        if str(lib_dir) not in sys.path:
            sys.path.insert(0, str(lib_dir))
        from chrome_mcp_client import _parallel_mux_peer_count

        peers = _parallel_mux_peer_count()
    except (ImportError, OSError, TypeError, ValueError):
        peers = 1
    if peers <= 1:
        return 90.0
    return min(240.0, 90.0 + 30.0 * (peers - 1))


def _attach_restart_stamp_path() -> Path:
    dev_dir = Path(__file__).resolve().parent.parent
    dev_dir_str = str(dev_dir)
    import sys

    if dev_dir_str not in sys.path:
        sys.path.insert(0, dev_dir_str)
    from wave_orchestrator.paths import resolve_dev_state_dir

    return resolve_dev_state_dir() / "mux-last-attach-restart.ts"


@contextmanager
def _attach_restart_registry_lock() -> Iterator[Path]:
    stamp_path = _attach_restart_stamp_path()
    stamp_path.parent.mkdir(parents=True, exist_ok=True)
    lock_path = stamp_path.parent / "mux-attach-restart.lock"
    with lock_path.open("a+", encoding="utf-8") as handle:
        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield stamp_path
        finally:
            fcntl.flock(handle.fileno(), fcntl.LOCK_UN)


def force_mux_attach_restart(
    *,
    reason: str = "attach new_page timeout",
    allow_parallel: bool = False,
) -> bool:
    """Restart mux daemon via chrome-e2e-preflight (MYRM_MUX_FORCE_ATTACH_RESTART=1).

    Safe under active wave leases: attach heal path only restarts mux, not shared backend.
    Returns True when preflight script ran successfully (exit 0).

    Parallel callers must use ``force_mux_attach_restart_scoped`` or
    ``force_mux_attach_restart_deduped`` (inside an existing ``mux_recovery_scope``).
    """
    if not allow_parallel and _parallel_load_blocks_attach_restart():
        import sys

        sys.stderr.write(
            f"{ATTACH_RESTART_BLOCKED_TOKEN}: parallel mux contexts or wave leases active\n"
        )
        sys.stderr.flush()
        return False
    monorepo_root = Path(__file__).resolve().parents[4]
    preflight = monorepo_root / "myrm-agent" / "scripts" / "dev" / "chrome-e2e-preflight.sh"
    if not preflight.is_file():
        return False
    env = {
        **os.environ,
        "MYRM_MUX_ALLOW_TIMEOUT_RESTART": "1",
        "MYRM_CHROME_E2E_ATTACH": "1",
        "MYRM_MUX_FORCE_ATTACH_RESTART": "1",
        "MYRM_PREFLIGHT_SKIP_ATTACH_WAIT": "1",
    }
    if reason.strip():
        env["MYRM_MUX_FORCE_ATTACH_REASON"] = reason.strip()
    try:
        result = subprocess.run(
            ["bash", str(preflight)],
            env=env,
            cwd=str(monorepo_root),
            timeout=int(_preflight_timeout_sec()),
            check=False,
            capture_output=True,
            text=True,
        )
        return result.returncode == 0
    except subprocess.TimeoutExpired:
        return False


def force_mux_attach_restart_deduped(
    *,
    reason: str = "attach new_page timeout",
    cooldown_sec: float = ATTACH_RESTART_COOLDOWN_SEC,
) -> bool:
    """Restart mux attach daemon at most once per cooldown window.

    Registry fcntl lock + preflight stamp reservation prevent parallel workers from
    stampeding restart during the slow preflight window.

    Caller must already hold ``mux_recovery_scope``.
    Returns False when a recent restart was skipped; True when restart ran ok.
    """
    with _attach_restart_registry_lock() as stamp_path:
        now = time.time()
        if stamp_path.is_file():
            try:
                last = float(stamp_path.read_text(encoding="utf-8").strip())
                if now - last < cooldown_sec:
                    return False
            except ValueError:
                pass
        allow_parallel = _desktop_soak_signoff_parallel_attach_restart_ok()
        ok = force_mux_attach_restart(reason=reason, allow_parallel=allow_parallel)
        if ok:
            stamp_path.write_text(str(now), encoding="utf-8")
        return ok


def force_mux_attach_restart_scoped(*, reason: str = "attach new_page timeout") -> bool:
    """Serialize global mux attach restart under ``mux_recovery_scope``.

    Prevents parallel cold-shim / new_page heal paths from stampeding daemon restart.
    """
    from transport_supervisor import mux_recovery_scope

    with mux_recovery_scope(phase="force_mux_attach_restart"):
        return force_mux_attach_restart_deduped(reason=reason)
