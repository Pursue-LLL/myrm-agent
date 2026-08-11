"""Monotonic BOOTSTRAP attach deadline — shared across endpoint recovery and stack-core gate.

[INPUT]
- dev_gate_contract.attach_parallel_wait_sec (POS: parallel ADMIT budget)
- MYRM_E2E_DEDUPE_HOLDER_PID / process pid (session key)
- MYRM_DEV_STATE_DIR (session persistence)

[OUTPUT]
- begin_session() -> BootstrapSession (idempotent per holder)
- remaining_sec() -> int (monotonic budget left)
- bootstrap_snapshot() -> dict for evidence planes

[POS]
Prevents chrome-e2e-preflight from running a full endpoint recovery wait (e.g. 660s)
and then opening an independent READ stack-core gate (e.g. 150s) in the same ADMIT.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from real_user_home import real_user_home


@dataclass(frozen=True, slots=True)
class BootstrapSession:
    started_mono: float
    budget_sec: int
    active_leases: int
    holder_pid: int
    phase: str = "BOOTSTRAP_ATTACH"


def dev_state_dir() -> Path:
    override = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
    if override:
        return Path(override).resolve()
    return real_user_home() / ".local/state/myrm-dev"


def _holder_pid() -> int:
    raw = os.environ.get("MYRM_E2E_DEDUPE_HOLDER_PID", "").strip()
    if raw.isdigit():
        return int(raw)
    return os.getpid()


def session_path() -> Path:
    return dev_state_dir() / "bootstrap-attach" / f"{_holder_pid()}.json"


def _attach_base_sec() -> int:
    # Default 360 matches STACK_FRONTEND_ATTACH_HEAL_ENSURE_WAIT_SEC so the
    # BOOTSTRAP budget survives one full frontend cold-compile/heal cycle.
    raw = os.environ.get("MYRM_CHROME_E2E_ATTACH_WAIT_SEC", "360").strip()
    return int(raw) if raw.isdigit() else 360


def load_session() -> BootstrapSession | None:
    path = session_path()
    if not path.is_file():
        return None
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(raw, dict):
        return None
    started = raw.get("started_mono")
    budget = raw.get("budget_sec")
    leases = raw.get("active_leases")
    holder = raw.get("holder_pid")
    if not isinstance(started, (int, float)):
        return None
    if not isinstance(budget, int) or budget < 1:
        return None
    if not isinstance(leases, int) or leases < 0:
        return None
    if not isinstance(holder, int) or holder < 1:
        return None
    phase = raw.get("phase")
    if not isinstance(phase, str) or not phase.strip():
        phase = "BOOTSTRAP_ATTACH"
    return BootstrapSession(
        started_mono=float(started),
        budget_sec=budget,
        active_leases=leases,
        holder_pid=holder,
        phase=phase,
    )


def _write_session(session: BootstrapSession) -> None:
    path = session_path()
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(asdict(session), indent=2), encoding="utf-8")


def prune_dead_sessions() -> int:
    directory = dev_state_dir() / "bootstrap-attach"
    if not directory.is_dir():
        return 0
    removed = 0
    current = session_path()
    for path in directory.glob("*.json"):
        if path == current or not path.stem.isdigit():
            continue
        try:
            os.kill(int(path.stem), 0)
        except OSError:
            path.unlink(missing_ok=True)
            removed += 1
    return removed


def begin_session(*, active_leases: int) -> BootstrapSession:
    prune_dead_sessions()
    existing = load_session()
    if existing is not None:
        left = remaining_sec(existing)
        if left > 0:
            return existing
        # Exhausted monotonic budget — allow a fresh ADMIT attempt (same holder).
        clear_session()
    from dev_gate_contract import attach_parallel_wait_sec  # noqa: PLC0415

    budget = attach_parallel_wait_sec(active_leases, base=_attach_base_sec())
    session = BootstrapSession(
        started_mono=time.monotonic(),
        budget_sec=budget,
        active_leases=active_leases,
        holder_pid=_holder_pid(),
    )
    _write_session(session)
    return session


def elapsed_sec(session: BootstrapSession | None = None) -> float:
    resolved = session or load_session()
    if resolved is None:
        return 0.0
    return max(0.0, time.monotonic() - resolved.started_mono)


def remaining_sec(session: BootstrapSession | None = None) -> int:
    resolved = session or load_session()
    if resolved is None:
        return 0
    left = resolved.budget_sec - elapsed_sec(resolved)
    return max(0, int(left))


def bootstrap_snapshot() -> dict[str, Any]:
    session = load_session()
    if session is None:
        return {
            "active": False,
            "remainingSec": 0,
            "budgetSec": 0,
            "elapsedSec": 0.0,
            "holderPid": _holder_pid(),
        }
    elapsed = elapsed_sec(session)
    return {
        "active": True,
        "remainingSec": remaining_sec(session),
        "budgetSec": session.budget_sec,
        "elapsedSec": round(elapsed, 3),
        "activeLeases": session.active_leases,
        "holderPid": session.holder_pid,
        "phase": session.phase,
        "sessionPath": str(session_path()),
    }


def clear_session() -> None:
    path = session_path()
    if path.is_file():
        path.unlink()


def _cmd_begin(args: argparse.Namespace) -> int:
    session = begin_session(active_leases=int(args.active_leases))
    sys.stdout.write(f"{session.budget_sec}\n")
    return 0


def _cmd_remaining(_args: argparse.Namespace) -> int:
    sys.stdout.write(f"{remaining_sec()}\n")
    return 0


def _cmd_snapshot(_args: argparse.Namespace) -> int:
    sys.stdout.write(json.dumps(bootstrap_snapshot(), indent=2) + "\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    begin = sub.add_parser("begin")
    begin.add_argument("--active-leases", type=int, default=0)
    begin.set_defaults(handler=_cmd_begin)

    remaining = sub.add_parser("remaining")
    remaining.set_defaults(handler=_cmd_remaining)

    snapshot = sub.add_parser("snapshot")
    snapshot.set_defaults(handler=_cmd_snapshot)

    ns = parser.parse_args(argv)
    handler = getattr(ns, "handler", None)
    if handler is None:
        parser.print_help()
        return 2
    return int(handler(ns))


if __name__ == "__main__":
    raise SystemExit(main())
