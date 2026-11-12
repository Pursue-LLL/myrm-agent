"""Coordination state of the shared-UI heal: state directory, heal stamp, flock paths and the attach leader record.

[INPUT]
- `MYRM_E2E_STATE_DIR` or `~/.local/state/myrm-e2e` (POS: state directory shared by every parallel Chrome E2E session)

[OUTPUT]
- `stamp_path()` / `flock_path()` / `attach_heal_flock_path()` / `ui_heal_global_flock_path()`: the files the heals coordinate through
- `warm_ui_heal_recently_applied()` / `write_heal_stamp()`: the debounce stamp
- `write_attach_leader_meta()` / `read_attach_leader_meta()` / `clear_attach_leader_meta()` / `leader_process_alive()` / `attach_heal_leader_stale()`: the attach leader record

[POS]
Dev infrastructure. Plain file and process-liveness state; the heals that take the locks live in `warm_ui_heal.py`.
"""

from __future__ import annotations

import os
import time
from pathlib import Path

from e2e_core.real_user_home import real_user_home

DEFAULT_DEBOUNCE_SEC = 60.0


_ATTACH_LEADER_STALE_SEC = 120.0


def _state_dir() -> Path:
    raw = os.environ.get(
        "MYRM_E2E_STATE_DIR",
        str(real_user_home() / ".local" / "state" / "myrm-e2e"),
    )
    path = Path(raw)
    path.mkdir(parents=True, exist_ok=True)
    return path


def stamp_path() -> Path:
    return _state_dir() / "warm-ui-heal.stamp"


def flock_path() -> Path:
    return _state_dir() / "warm-ui-heal.flock"


def attach_heal_flock_path() -> Path:
    return _state_dir() / "attach-frontend-heal.flock"


def _attach_heal_leader_meta_path() -> Path:
    return _state_dir() / "attach-frontend-heal.leader.json"


def write_attach_leader_meta(owner_pid: int) -> None:
    import json

    payload = {"pid": owner_pid, "started_at": time.time()}
    _attach_heal_leader_meta_path().write_text(
        json.dumps(payload, separators=(",", ":")),
        encoding="utf-8",
    )


def clear_attach_leader_meta() -> None:
    meta = _attach_heal_leader_meta_path()
    if meta.is_file():
        meta.unlink()


def read_attach_leader_meta() -> tuple[int | None, float | None]:
    import json

    meta = _attach_heal_leader_meta_path()
    if not meta.is_file():
        return None, None
    try:
        payload = json.loads(meta.read_text(encoding="utf-8"))
    except (OSError, ValueError, json.JSONDecodeError):
        return None, None
    pid_raw = payload.get("pid")
    started_raw = payload.get("started_at")
    pid = int(pid_raw) if isinstance(pid_raw, int) or str(pid_raw).isdigit() else None
    started = float(started_raw) if started_raw is not None else None
    return pid, started


def leader_process_alive(pid: int | None) -> bool:
    if pid is None or pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except OSError:
        return False
    return True


def attach_heal_leader_stale(*, stale_sec: float = _ATTACH_LEADER_STALE_SEC) -> bool:
    """True when meta points to a dead pid or a leader running longer than stale_sec."""
    pid, started = read_attach_leader_meta()
    if pid is None:
        return False
    if not leader_process_alive(pid):
        return True
    if started is None:
        return False
    return (time.time() - started) > stale_sec


def ui_heal_global_flock_path() -> Path:
    return _state_dir() / "ui-heal-global.flock"


def warm_ui_heal_recently_applied(
    *, debounce_sec: float = DEFAULT_DEBOUNCE_SEC
) -> bool:
    stamp = stamp_path()
    if not stamp.is_file():
        return False
    try:
        last = float(stamp.read_text(encoding="utf-8").strip())
    except ValueError:
        return False
    return (time.time() - last) < debounce_sec


def write_heal_stamp() -> None:
    stamp_path().write_text(f"{time.time():.3f}\n", encoding="utf-8")
