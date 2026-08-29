"""Gate dev-stack frontend-only ensure after manual cleanup (prevents Agent respawn loops).

Pause stamp lives in the *shared* myrm-dev state dir so isolated runtimes
(MYRM_DEV_STATE_DIR override, ports 13000–14000) cannot bypass the gate.
Override for tests: MYRM_FRONTEND_DEV_PAUSE_DIR.
Force ensure: MYRM_FRONTEND_DEV_FORCE=1.
"""

from __future__ import annotations

import argparse
import os
import sys
import time
from pathlib import Path

if __package__ in (None, ""):
    _lib_root = str(Path(__file__).resolve().parent.parent)
    if _lib_root not in sys.path:
        sys.path.insert(0, _lib_root)

from e2e_core.real_user_home import real_user_home

# 8h: overnight Agent waves must not respawn next-server after manual cleanup
_DEFAULT_PAUSE_SEC = 28800.0
_PAUSE_BASENAME = "frontend-dev-paused-until"
_FORCE_TRUTHY = frozenset({"1", "true", "yes"})


def shared_dev_state_dir() -> Path:
    """Always the login-user shared myrm-dev dir (never wave/isolated state)."""
    override = os.environ.get("MYRM_FRONTEND_DEV_PAUSE_DIR", "").strip()
    if override:
        path = Path(override)
        path.mkdir(parents=True, exist_ok=True)
        return path
    path = real_user_home() / ".local" / "state" / "myrm-dev"
    path.mkdir(parents=True, exist_ok=True)
    return path


def pause_file_path() -> Path:
    return shared_dev_state_dir() / _PAUSE_BASENAME


def force_allowed() -> bool:
    """Deprecated escape hatch — FORCE alone must not defeat cleanup pause.

    Agents that need frontend after cleanup must run
    ``dev-stack.sh frontend-only clear-pause`` (or ``frontend_dev_pause.py clear``).
    Kept for diagnostics / future dual-key policy; currently always False for gate.
    """
    return False


def read_pause_until() -> float | None:
    path = pause_file_path()
    if not path.is_file():
        return None
    try:
        line = path.read_text(encoding="utf-8").splitlines()[0].strip()
        until = float(line)
    except (IndexError, ValueError, OSError):
        return None
    return until


def is_frontend_dev_paused() -> bool:
    if force_allowed():
        return False
    until = read_pause_until()
    if until is None:
        return False
    if time.time() >= until:
        try:
            pause_file_path().unlink(missing_ok=True)
        except OSError:
            pass
        return False
    return True


def write_frontend_dev_pause(seconds: float, reason: str = "cleanup") -> float:
    until = time.time() + max(0.0, seconds)
    pause_file_path().write_text(f"{until:.3f}\n{(reason.strip() or 'manual')}\n", encoding="utf-8")
    return until


def clear_frontend_dev_pause() -> bool:
    path = pause_file_path()
    if not path.is_file():
        return False
    path.unlink(missing_ok=True)
    return True


def pause_remaining_sec() -> float:
    until = read_pause_until()
    if until is None:
        return 0.0
    return max(0.0, until - time.time())


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Frontend dev pause gate (post-cleanup Agent respawn blocker)")
    sub = parser.add_subparsers(dest="cmd", required=True)

    sub.add_parser("check", help="exit 0 when paused, 1 when active")

    write_p = sub.add_parser("write", help="pause frontend-only ensure")
    write_p.add_argument("--seconds", type=float, default=_DEFAULT_PAUSE_SEC)
    write_p.add_argument("--reason", default="cleanup")

    sub.add_parser("clear", help="remove pause stamp")
    sub.add_parser("status", help="print paused|active and remaining sec")

    args = parser.parse_args(argv)

    if args.cmd == "check":
        return 0 if is_frontend_dev_paused() else 1
    if args.cmd == "write":
        until = write_frontend_dev_pause(args.seconds, args.reason)
        print(f"FRONTEND_DEV_PAUSED until={until:.0f} sec={args.seconds:.0f} reason={args.reason}")
        return 0
    if args.cmd == "clear":
        clear_frontend_dev_pause()
        print("FRONTEND_DEV_ACTIVE")
        return 0
    if args.cmd == "status":
        if is_frontend_dev_paused():
            print(f"paused remaining_sec={pause_remaining_sec():.0f}")
        else:
            print("active")
        return 0
    return 2


if __name__ == "__main__":
    raise SystemExit(main())
