"""Stack mutation policy SSOT for shared dev stack during parallel Chrome E2E.

[INPUT]
- stack-epoch.sh::_wave_active_lease_count (POS: Wave lease 计数)
- dev_gate_contract.py::chrome_e2e_pytest_safe_timeout_sec (POS: session 预算 SSOT)

[OUTPUT]
- decide_drift_heal / pending-stack-drift.json persistence
- CLI: decide-drift, record-pending, clear-pending, session-safe-timeout

[POS]
共享栈 mutation 决策层。attach/supervisor 在 active wave leases>0 时 defer drift heal。
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Final

PENDING_DRIFT_FILENAME: Final[str] = "pending-stack-drift.json"


class DriftHealAction(str, Enum):
    NOOP = "noop"
    APPLY = "apply"
    DEFER = "defer"


@dataclass(frozen=True)
class PendingStackDrift:
    reason: str
    recorded_at: str
    server_dir: str


def pending_drift_path(state_dir: Path) -> Path:
    return state_dir / PENDING_DRIFT_FILENAME


def read_pending_drift(state_dir: Path) -> PendingStackDrift | None:
    path = pending_drift_path(state_dir)
    if not path.is_file():
        return None
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    reason = str(payload.get("reason", "")).strip()
    server_dir = str(payload.get("server_dir", "")).strip()
    recorded_at = str(payload.get("recorded_at", "")).strip()
    if not reason:
        return None
    return PendingStackDrift(
        reason=reason, recorded_at=recorded_at, server_dir=server_dir
    )


def pending_drift_exists(state_dir: Path) -> bool:
    return read_pending_drift(state_dir) is not None


def record_pending_drift(state_dir: Path, *, reason: str, server_dir: str) -> None:
    state_dir.mkdir(parents=True, exist_ok=True)
    payload = PendingStackDrift(
        reason=reason.strip(),
        recorded_at=datetime.now(tz=UTC).isoformat(),
        server_dir=server_dir.strip(),
    )
    pending_drift_path(state_dir).write_text(
        json.dumps(asdict(payload), indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def clear_pending_drift(state_dir: Path) -> None:
    path = pending_drift_path(state_dir)
    if path.is_file():
        path.unlink()


def decide_drift_heal(*, active_leases: int, drift_pending: bool) -> DriftHealAction:
    if not drift_pending:
        return DriftHealAction.NOOP
    if active_leases > 0:
        return DriftHealAction.DEFER
    return DriftHealAction.APPLY


def should_defer_harness_install(active_leases: int) -> bool:
    return active_leases > 0


def should_defer_supervisor_backend_heal(
    *,
    active_leases: int,
    pending_drift: bool,
    api_http_ok: bool,
) -> bool:
    if pending_drift and active_leases > 0:
        return True
    return False


@dataclass(frozen=True, slots=True)
class PendingDriftApplyResult:
    action: str
    detail: str = ""


def apply_pending_drift_if_idle(
    *,
    monorepo_root: Path,
    state_dir: Path | None = None,
    server_dir: Path | None = None,
) -> PendingDriftApplyResult:
    """Apply deferred shared-backend drift heal when no active wave leases remain (R31 / SMP R3)."""
    root = monorepo_root.resolve()
    resolved_state = state_dir or _default_state_dir()
    resolved_server = server_dir or (root / "myrm-agent" / "myrm-agent-server")
    dev_stack = root / "myrm-agent" / "scripts" / "dev" / "dev-stack.sh"
    active_leases = wave_active_lease_count(root)
    if active_leases > 0:
        return PendingDriftApplyResult(
            "skipped",
            f"active_leases={active_leases}",
        )
    if not pending_drift_exists(resolved_state):
        return PendingDriftApplyResult("noop")
    if not dev_stack.is_file():
        return PendingDriftApplyResult("failed", f"missing dev-stack: {dev_stack}")
    env = {
        **os.environ,
        "MYRM_WAVE_GATE_BYPASS": "1",
        "MYRM_SUPERVISOR_BYPASS": "1",
    }
    try:
        proc = subprocess.run(
            ["bash", str(dev_stack), "backend-only", "ensure"],
            capture_output=True,
            text=True,
            timeout=120,
            check=False,
            cwd=str(root),
            env=env,
        )
    except (OSError, subprocess.TimeoutExpired) as exc:
        return PendingDriftApplyResult("failed", str(exc))
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "backend-only ensure failed").strip()
        return PendingDriftApplyResult("failed", detail[:500])
    clear_pending_drift(resolved_state)
    return PendingDriftApplyResult(
        "applied",
        f"server_dir={resolved_server}",
    )


def wave_active_lease_count(monorepo_root: Path) -> int:
    wave_bin = monorepo_root / "scripts" / "dev" / "wave.sh"
    if not wave_bin.is_file():
        return 0
    try:
        result = subprocess.run(
            ["bash", str(wave_bin), "status"],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
    except (OSError, subprocess.TimeoutExpired):
        return 0
    if result.returncode != 0:
        return 0
    try:
        payload = json.loads(result.stdout or "{}")
    except json.JSONDecodeError:
        return 0
    raw = payload.get("activeLeaseCount")
    if isinstance(raw, int):
        return max(0, raw)
    if isinstance(raw, str) and raw.isdigit():
        return int(raw)
    return 0


def _default_state_dir() -> Path:
    home = Path.home()
    return Path(
        os.environ.get(
            "MYRM_DEV_STATE_DIR", str(home / ".local" / "state" / "myrm-dev")
        )
    )


def _cmd_decide_drift(args: argparse.Namespace) -> int:
    action = decide_drift_heal(
        active_leases=int(args.active_leases),
        drift_pending=bool(int(args.drift_pending)),
    )
    sys.stdout.write(f"{action.value}\n")
    return 0


def _cmd_record_pending(args: argparse.Namespace) -> int:
    record_pending_drift(
        Path(args.state_dir),
        reason=str(args.reason),
        server_dir=str(args.server_dir),
    )
    return 0


def _cmd_clear_pending(args: argparse.Namespace) -> int:
    clear_pending_drift(Path(args.state_dir))
    return 0


def _cmd_pending_exists(args: argparse.Namespace) -> int:
    exists = pending_drift_exists(Path(args.state_dir))
    sys.stdout.write("1" if exists else "0")
    return 0


def _cmd_session_safe_timeout(args: argparse.Namespace) -> int:
    from dev_gate_contract import chrome_e2e_pytest_safe_timeout_sec  # noqa: PLC0415

    timeout_sec = chrome_e2e_pytest_safe_timeout_sec(
        str(args.lane),
        int(args.item_count),
        joined_argv=str(args.joined_argv),
    )
    sys.stdout.write(f"{timeout_sec}\n")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)

    decide = sub.add_parser("decide-drift")
    decide.add_argument("--active-leases", required=True)
    decide.add_argument("--drift-pending", choices=("0", "1"), required=True)
    decide.set_defaults(handler=_cmd_decide_drift)

    record = sub.add_parser("record-pending")
    record.add_argument("--state-dir", default=str(_default_state_dir()))
    record.add_argument("--reason", required=True)
    record.add_argument("--server-dir", required=True)
    record.set_defaults(handler=_cmd_record_pending)

    clear = sub.add_parser("clear-pending")
    clear.add_argument("--state-dir", default=str(_default_state_dir()))
    clear.set_defaults(handler=_cmd_clear_pending)

    exists = sub.add_parser("pending-exists")
    exists.add_argument("--state-dir", default=str(_default_state_dir()))
    exists.set_defaults(handler=_cmd_pending_exists)

    safe = sub.add_parser("session-safe-timeout")
    safe.add_argument("--lane", required=True)
    safe.add_argument("--item-count", required=True)
    safe.add_argument("--joined-argv", default="")
    safe.set_defaults(handler=_cmd_session_safe_timeout)

    parsed = parser.parse_args(argv)
    handler = getattr(parsed, "handler", None)
    if handler is None:
        parser.error("command handler missing")
    return int(handler(parsed))


if __name__ == "__main__":
    raise SystemExit(main())
