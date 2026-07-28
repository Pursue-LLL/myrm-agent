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
import fcntl
import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from collections.abc import Iterator
from contextlib import contextmanager
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from enum import Enum
from pathlib import Path
from typing import Final

PENDING_DRIFT_FILENAME: Final[str] = "pending-stack-drift.json"
_HARNESS_IMPORT_FAILED_TOKEN: Final[str] = (
    "monorepo harness source present but myrm_agent_harness import failed"
)


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


def _run_backend_only_ensure(
    *, dev_stack: Path, root: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(dev_stack), "backend-only", "ensure"],
        capture_output=True,
        text=True,
        timeout=120,
        check=False,
        cwd=str(root),
        env=env,
    )


def _run_harness_install(
    *, root: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["./myrm", "harness", "install"],
        capture_output=True,
        text=True,
        timeout=240,
        check=False,
        cwd=str(root),
        env=env,
    )


def _command_failure_detail(
    proc: subprocess.CompletedProcess[str], fallback: str
) -> str:
    return (proc.stderr or proc.stdout or fallback).strip()[:500]


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
        proc = _run_backend_only_ensure(dev_stack=dev_stack, root=root, env=env)
    except (OSError, subprocess.TimeoutExpired) as exc:
        return PendingDriftApplyResult("failed", str(exc))
    if proc.returncode != 0:
        detail = _command_failure_detail(proc, "backend-only ensure failed")
        if _HARNESS_IMPORT_FAILED_TOKEN in detail:
            try:
                install_proc = _run_harness_install(root=root, env=env)
            except (OSError, subprocess.TimeoutExpired) as exc:
                return PendingDriftApplyResult(
                    "failed",
                    f"auto harness install failed before retry: {exc}",
                )
            if install_proc.returncode != 0:
                install_detail = _command_failure_detail(
                    install_proc, "harness install failed"
                )
                return PendingDriftApplyResult(
                    "failed",
                    f"auto harness install failed before retry: {install_detail}",
                )
            try:
                retry_proc = _run_backend_only_ensure(
                    dev_stack=dev_stack,
                    root=root,
                    env=env,
                )
            except (OSError, subprocess.TimeoutExpired) as exc:
                return PendingDriftApplyResult(
                    "failed",
                    f"backend-only ensure retry after harness install failed: {exc}",
                )
            if retry_proc.returncode != 0:
                retry_detail = _command_failure_detail(
                    retry_proc,
                    "backend-only ensure retry failed",
                )
                return PendingDriftApplyResult(
                    "failed",
                    "backend-only ensure retry after harness install failed: "
                    f"{retry_detail}",
                )
            clear_pending_drift(resolved_state)
            return PendingDriftApplyResult(
                "applied",
                f"server_dir={resolved_server} auto_harness_install_retry=1",
            )
        return PendingDriftApplyResult("failed", detail)
    clear_pending_drift(resolved_state)
    return PendingDriftApplyResult(
        "applied",
        f"server_dir={resolved_server}",
    )


def shared_api_http_ok() -> bool:
    try:
        urllib.request.urlopen(
            "http://127.0.0.1:8080/api/v1/health",
            timeout=5,
        )
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


@contextmanager
def backend_heal_file_lock(lock_file: Path, wait_sec: float) -> Iterator[None]:
    """fcntl.flock SSOT — macOS lacks GNU flock(1)."""
    lock_file.parent.mkdir(parents=True, exist_ok=True)
    fd = os.open(str(lock_file), os.O_RDWR | os.O_CREAT, 0o644)
    deadline = time.monotonic() + wait_sec
    acquired = False
    try:
        while True:
            try:
                fcntl.flock(fd, fcntl.LOCK_EX | fcntl.LOCK_NB)
                acquired = True
                break
            except BlockingIOError:
                if time.monotonic() >= deadline:
                    raise TimeoutError(
                        f"backend heal flock timeout after {wait_sec}s"
                    ) from None
                time.sleep(0.25)
        yield
    finally:
        if acquired:
            fcntl.flock(fd, fcntl.LOCK_UN)
        os.close(fd)


def attach_backend_crash_heal_inner(
    *, monorepo_root: Path, dev_stack: Path
) -> int:
    active_leases = wave_active_lease_count(monorepo_root)
    if shared_api_http_ok():
        return 0
    print(
        "CHROME_E2E_ATTACH_HEAL: shared api down — crash heal starting "
        f"({active_leases} active leases)",
        file=sys.stderr,
        flush=True,
    )
    env = {**os.environ, "MYRM_WAVE_GATE_BYPASS": "1"}
    for attempt, backoff_sec in enumerate((0, 5, 10), start=1):
        if backoff_sec > 0:
            time.sleep(backoff_sec)
        print(
            "CHROME_E2E_ATTACH_HEAL: crash heal attempt "
            f"{attempt}/3 ({active_leases} active leases)",
            file=sys.stderr,
            flush=True,
        )
        proc = _run_backend_only_ensure(
            dev_stack=dev_stack,
            root=monorepo_root,
            env=env,
        )
        if proc.returncode == 0 and shared_api_http_ok():
            print(
                "CHROME_E2E_ATTACH_HEAL: shared api restored after crash heal "
                f"(attempt {attempt})",
                file=sys.stderr,
                flush=True,
            )
            return 0
        print(
            "CHROME_E2E_ATTACH_HEAL: crash heal attempt "
            f"{attempt}/3 failed (api still down)",
            file=sys.stderr,
            flush=True,
        )
    print(
        "CHROME_E2E_FAIL: attach backend crash heal failed after 3 attempts "
        "(api still down)",
        file=sys.stderr,
        flush=True,
    )
    return 1


def attach_backend_crash_heal(
    *,
    monorepo_root: Path,
    dev_stack: Path,
    lock_file: Path,
    wait_sec: float,
) -> int:
    if shared_api_http_ok():
        return 0
    try:
        with backend_heal_file_lock(lock_file, wait_sec):
            return attach_backend_crash_heal_inner(
                monorepo_root=monorepo_root,
                dev_stack=dev_stack,
            )
    except TimeoutError:
        print(
            f"CHROME_E2E_ATTACH_HEAL: backend heal flock timeout after {wait_sec}s",
            file=sys.stderr,
            flush=True,
        )
        return 1


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


def _cmd_attach_crash_heal(args: argparse.Namespace) -> int:
    return attach_backend_crash_heal(
        monorepo_root=Path(args.monorepo_root),
        dev_stack=Path(args.dev_stack),
        lock_file=Path(args.lock_file),
        wait_sec=float(args.wait_sec),
    )


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

    crash = sub.add_parser("attach-crash-heal")
    crash.add_argument("--monorepo-root", required=True)
    crash.add_argument("--dev-stack", required=True)
    crash.add_argument("--lock-file", required=True)
    crash.add_argument("--wait-sec", type=float, default=180.0)
    crash.set_defaults(handler=_cmd_attach_crash_heal)

    parsed = parser.parse_args(argv)
    handler = getattr(parsed, "handler", None)
    if handler is None:
        parser.error("command handler missing")
    return int(handler(parsed))


if __name__ == "__main__":
    raise SystemExit(main())
