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
    try:
        from e2e_session_registry import body_active_count, list_live_e2e_sessions

        sessions = list_live_e2e_sessions()
        if body_active_count(sessions) > 0:
            return DriftHealAction.DEFER
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    return DriftHealAction.APPLY


def should_defer_harness_install(active_leases: int) -> bool:
    """Defer under wave leases or parallel chrome_e2e ADMIT (R150 harness install dogpile)."""
    if active_leases > 0:
        return True
    try:
        from e2e_session_registry import list_live_e2e_sessions

        if len(list_live_e2e_sessions()) > 1:
            return True
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    return False


def should_defer_supervisor_backend_heal(
    *,
    active_leases: int,
    pending_drift: bool,
    api_http_ok: bool,
) -> bool:
    del pending_drift, api_http_ok
    # R143 / BUG-DG-2026-07-29-008: never backend-only heal while wave leases active.
    if active_leases > 0:
        return True
    try:
        from e2e_session_registry import body_active_count, list_live_e2e_sessions

        if body_active_count(list_live_e2e_sessions()) > 0:
            return True
    except (ImportError, OSError, RuntimeError, ValueError):
        pass
    return False


def _backend_only_ensure_timeout_sec() -> float:
    """Wall timeout for dev-stack backend-only ensure (cold app.main import can exceed 120s)."""
    raw = os.environ.get("MYRM_BACKEND_ONLY_ENSURE_TIMEOUT_SEC", "360")
    try:
        return max(120.0, float(raw))
    except ValueError:
        return 360.0


def _run_backend_only_ensure(
    *, dev_stack: Path, root: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["bash", str(dev_stack), "backend-only", "ensure"],
        capture_output=True,
        text=True,
        timeout=_backend_only_ensure_timeout_sec(),
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


def _run_backend_only_ensure_with_harness_retry(
    *, dev_stack: Path, root: Path, env: dict[str, str]
) -> subprocess.CompletedProcess[str]:
    proc = _run_backend_only_ensure(dev_stack=dev_stack, root=root, env=env)
    if proc.returncode == 0:
        return proc
    detail = _command_failure_detail(proc, "backend-only ensure failed")
    if _HARNESS_IMPORT_FAILED_TOKEN not in detail:
        return proc
    active_leases = wave_active_lease_count(root)
    if should_defer_harness_install(active_leases):
        return proc
    install_proc = _run_harness_install(root=root, env=env)
    if install_proc.returncode != 0:
        return install_proc
    return _run_backend_only_ensure(dev_stack=dev_stack, root=root, env=env)


@dataclass(frozen=True, slots=True)
class PendingDriftApplyResult:
    action: str
    detail: str = ""


def ensure_lock_active(state_dir: Path) -> bool:
    """True when dev-stack ensure holds ensure.lock.d (parallel drift apply must defer)."""
    owner_file = state_dir / "ensure.lock.d" / "pid"
    if not owner_file.is_file():
        return False
    try:
        raw = owner_file.read_text(encoding="utf-8").strip()
    except OSError:
        return False
    if not raw.isdigit():
        return False
    try:
        os.kill(int(raw), 0)
    except OSError:
        return False
    return True


def _api_health_url() -> str:
    base = os.environ.get("E2E_API_BASE", "").strip()
    if base:
        return f"{base.rstrip('/')}/api/v1/health"
    port = os.environ.get("MYRM_BACKEND_PORT") or os.environ.get("PORT") or "8080"
    return f"http://127.0.0.1:{port}/api/v1/health"


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
    if ensure_lock_active(resolved_state):
        return PendingDriftApplyResult("skipped", "ensure_in_progress")
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
        urllib.request.urlopen(_api_health_url(), timeout=5)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        return False


def _poll_shared_api_ok(*, max_wait_sec: float, interval_sec: float = 2.0) -> bool:
    """Post-ensure grace — backend bind can lag ensure exit under parallel load."""
    deadline = time.monotonic() + max_wait_sec
    while time.monotonic() < deadline:
        if shared_api_http_ok():
            return True
        time.sleep(interval_sec)
    return shared_api_http_ok()


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


def attach_backend_crash_heal_inner(*, monorepo_root: Path, dev_stack: Path) -> int:
    active_leases = wave_active_lease_count(monorepo_root)
    if shared_api_http_ok():
        return 0
    print(
        "CHROME_E2E_ATTACH_HEAL: shared api down — crash heal starting "
        f"({active_leases} active leases; SHC leader)",
        file=sys.stderr,
        flush=True,
    )
    env = {
        **os.environ,
        "MYRM_WAVE_GATE_BYPASS": "1",
        "MYRM_SUPERVISOR_BYPASS": "1",
        "MYRM_BACKEND_ONLY_ENSURE_TIMEOUT_SEC": "600",
    }
    # Parallel attach: more attempts + post-ensure api poll — transient :8080 flap under peers.
    parallel_busy = active_leases > 0
    max_attempts = 5 if parallel_busy else 3
    backoff_schedule = (0, 8, 15, 25, 40) if parallel_busy else (0, 5, 10)
    api_poll_sec = 15.0 if parallel_busy else 8.0
    for attempt, backoff_sec in enumerate(backoff_schedule[:max_attempts], start=1):
        if backoff_sec > 0:
            time.sleep(backoff_sec)
        print(
            "CHROME_E2E_ATTACH_HEAL: crash heal attempt "
            f"{attempt}/{max_attempts} ({active_leases} active leases)",
            file=sys.stderr,
            flush=True,
        )
        proc = _run_backend_only_ensure_with_harness_retry(
            dev_stack=dev_stack,
            root=monorepo_root,
            env=env,
        )
        if proc.returncode == 0 and _poll_shared_api_ok(max_wait_sec=api_poll_sec):
            print(
                "CHROME_E2E_ATTACH_HEAL: shared api restored after crash heal "
                f"(attempt {attempt})",
                file=sys.stderr,
                flush=True,
            )
            return 0
        print(
            "CHROME_E2E_ATTACH_HEAL: crash heal attempt "
            f"{attempt}/{max_attempts} failed (api still down)",
            file=sys.stderr,
            flush=True,
        )
    print(
        f"CHROME_E2E_FAIL: attach backend crash heal failed after {max_attempts} attempts "
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
    shpoib: bool = False,
) -> int:
    from stack_heal_coordinator import request_attach_crash_heal

    return request_attach_crash_heal(
        monorepo_root=monorepo_root,
        dev_stack=dev_stack,
        lock_file=lock_file,
        wait_sec=wait_sec,
        shpoib=shpoib,
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


def default_backend_heal_flock_file() -> Path:
    return _default_state_dir() / "chrome-e2e-backend-heal.flock"


def run_command_with_backend_heal_flock(
    *,
    cmd: list[str],
    lock_file: Path,
    wait_sec: float,
) -> int:
    """Run subprocess argv under backend heal flock (P0-STACK-1 / R46.2 SSOT)."""
    if not cmd:
        print("run-heal-flocked: empty command", file=sys.stderr)
        return 2
    try:
        with backend_heal_file_lock(lock_file, wait_sec):
            completed = subprocess.run(cmd, check=False)
        return int(completed.returncode)
    except TimeoutError as exc:
        print(f"GATE_STACK_HEAL_FLOCK_TIMEOUT: {exc}", file=sys.stderr)
        return 1


def _cmd_run_heal_flocked(args: argparse.Namespace) -> int:
    cmd = [str(part) for part in args.cmd if str(part)]
    while cmd and cmd[0] == "--":
        cmd.pop(0)
    return run_command_with_backend_heal_flock(
        cmd=cmd,
        lock_file=Path(args.lock_file),
        wait_sec=float(args.wait_sec),
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
        shpoib=args.shpoib == "1",
    )


def _cmd_attach_health_preflight(args: argparse.Namespace) -> int:
    from stack_heal_coordinator import run_attach_health_preflight  # noqa: PLC0415

    return run_attach_health_preflight(
        monorepo_root=Path(args.monorepo_root),
        dev_stack=Path(args.dev_stack),
        server_dir=Path(args.server_dir),
        lock_file=Path(args.lock_file),
        wait_sec=float(args.wait_sec),
        shpoib=args.shpoib == "1",
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
    crash.add_argument(
        "--shpoib",
        choices=("0", "1"),
        default="0",
        help="1 when caller is SHPOIB lane (skip shared :8080 heal)",
    )
    crash.set_defaults(handler=_cmd_attach_crash_heal)

    preflight = sub.add_parser("attach-health-preflight")
    preflight.add_argument("--monorepo-root", required=True)
    preflight.add_argument("--dev-stack", required=True)
    preflight.add_argument("--server-dir", required=True)
    preflight.add_argument("--lock-file", required=True)
    preflight.add_argument("--wait-sec", type=float, default=5.0)
    preflight.add_argument(
        "--shpoib",
        choices=("0", "1"),
        default="0",
        help="1 when caller is SHPOIB lane (skip shared :8080 preflight)",
    )
    preflight.set_defaults(handler=_cmd_attach_health_preflight)

    run_flock = sub.add_parser("run-heal-flocked")
    run_flock.add_argument(
        "--lock-file",
        default=str(default_backend_heal_flock_file()),
    )
    run_flock.add_argument("--wait-sec", type=float, default=180.0)
    run_flock.add_argument(
        "cmd",
        nargs=argparse.REMAINDER,
        help="Command after -- (e.g. run-heal-flocked -- ./myrm ready --chrome)",
    )
    run_flock.set_defaults(handler=_cmd_run_heal_flocked)

    parsed = parser.parse_args(argv)
    handler = getattr(parsed, "handler", None)
    if handler is None:
        parser.error("command handler missing")
    return int(handler(parsed))


if __name__ == "__main__":
    raise SystemExit(main())
