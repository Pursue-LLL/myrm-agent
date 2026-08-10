"""Stack mutation policy SSOT for shared dev stack during parallel Chrome E2E.

[INPUT]
- stack-epoch.sh::_wave_active_lease_count (POS: Wave lease 计数)
- dev_gate_contract.py::chrome_e2e_pytest_safe_timeout_sec (POS: session 预算 SSOT)

[OUTPUT]
- decide_drift_heal / pending-stack-drift.json persistence
- ensure_lock_active / apply_pending_drift_if_idle (defer while ensure.lock.d held)
- shared_api_http_ok via E2E_API_BASE / MYRM_BACKEND_PORT SSOT
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


def maybe_detect_and_record_source_drift(
    *,
    monorepo_root: Path,
    state_dir: Path,
    server_dir: Path | None = None,
) -> bool:
    """Detect shared-backend source drift and record it as pending.

    Coordinator calls this each reap cycle so a code change heals the shared
    backend even when no new attach ever happens (attach is the other recorder).
    Returns True when drift was recorded or already pending; False when fresh.
    """
    resolved_state = state_dir.resolve()
    resolved_server = (
        server_dir or (monorepo_root / "myrm-agent" / "myrm-agent-server")
    ).resolve()
    if pending_drift_exists(resolved_state):
        return True
    # Active leases defer apply anyway — skip the git walk until idle to avoid
    # burning CPU under parallel load (detection is re-armed once pending clears).
    from e2e_lease_liveness import (
        load_wave_snapshot,
        wave_lease_counts,
    )  # noqa: PLC0415

    if wave_lease_counts(load_wave_snapshot()).effective_total > 0:
        return False
    from runtime_identity import _backend_source_fingerprint  # noqa: PLC0415

    epoch_file = resolved_state / "stack-epoch.json"
    stored_fp = ""
    if epoch_file.is_file():
        try:
            payload = json.loads(epoch_file.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            payload = {}
        if isinstance(payload, dict):
            raw_fp = payload.get("source_fingerprint")
            if isinstance(raw_fp, str):
                stored_fp = raw_fp.strip()
    current_fp = _backend_source_fingerprint()
    if not current_fp or current_fp == stored_fp:
        return False
    record_pending_drift(
        resolved_state,
        reason="backend_source_drift",
        server_dir=str(resolved_server),
    )
    return True


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
        from e2e_session_registry import list_live_e2e_sessions

        sessions = list_live_e2e_sessions()
        if len(sessions) > 0:
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
    del pending_drift
    # R143 / BUG-DG-2026-07-29-008: never restart a healthy backend while wave
    # leases are active — a heal restart could tear down parallel tests.
    # When the API is already down, every parallel session is already broken,
    # so recovering the shared backend strictly dominates deferring: waiting
    # for leases to drain can deadlock, because the very backend outage is
    # what stalls the tests that hold the leases.
    if not api_http_ok:
        return False
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


# 私池 runtime env 变量（isolated_runtime_allocator.runtime_environment 注入）。
# 共享栈 drift apply / crash heal 必须显式清除这些，否则继承私池 state dir /
# namespace / 后端端口，导致 backend_bg.sh 把共享后端写入私池 identity、
# 或 8080 owner 缺失共享 stack-epoch 指纹（§26.28-B 根因）。
_PRIVATE_RUNTIME_ENV_KEYS: Final[tuple[str, ...]] = (
    "MYRM_RUNTIME_NAMESPACE",
    "MYRM_AGENT_ROOT",
    "MYRM_SERVER_DIR",
    "MYRM_FRONTEND_DIR",
    "MYRM_WAVE_STATE_DIR",
    "MYRM_DEV_STATE_DIR",
    "MYRM_DATA_DIR",
    "MYRM_FRONTEND_PORT",
    "MYRM_BACKEND_PORT",
    "PORT",
    "API_PORT",
    "ONEBOT_PORT",
    "E2E_API_BASE",
    "E2E_UI_BASE",
    "MYRM_E2E_UI_BASE",
    "MYRM_STACK_EPOCH_FILE",
    "MYRM_BACKEND_IDENTITY_FILE",
    "MYRM_SUPERVISOR_SOCKET",
    "WEBUI_SESSION_COOKIE_NAME",
    "MYRM_E2E_PRIVATE_RUNTIME_ID",
    "MYRM_E2E_PRIVATE_BACKEND",
    "MYRM_E2E_SHPOIB",
    "MYRM_PRIVATE_BACKEND",
)


def _shared_stack_env() -> dict[str, str]:
    """Environment for shared-stack ensure: purge any inherited private-runtime vars.

    The coordinator / attach / heal processes may have been spawned inside a
    private runtime (kanban-e2e-*, verify-api-*) whose env points MYRM_DEV_STATE_DIR
    and MYRM_BACKEND_PORT at the private runtime. Running `dev-stack.sh backend-only
    ensure` with that inherited env writes the shared backend's identity into the
    private runtime dir (runtimeId=shared) and, when the private runtime's
    stack-epoch file is absent, leaves the shared :8080 health probe without a
    stack_epoch fingerprint — the §26.28-B "private pool occupies :8080" loop.
    """
    env = {k: v for k, v in os.environ.items() if k not in _PRIVATE_RUNTIME_ENV_KEYS}
    env.update(
        {
            "MYRM_WAVE_GATE_BYPASS": "1",
            "MYRM_SUPERVISOR_BYPASS": "1",
        }
    )
    return env


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
    env = _shared_stack_env()
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


def _api_port_listening() -> bool:
    port = os.environ.get("MYRM_BACKEND_PORT") or os.environ.get("PORT") or "8080"
    try:
        result = subprocess.run(
            ["lsof", f"-iTCP:{port}", "-sTCP:LISTEN", "-t"],
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (subprocess.TimeoutExpired, OSError):
        return False
    return bool(result.stdout.strip())


def shared_api_http_ok() -> bool:
    try:
        urllib.request.urlopen(_api_health_url(), timeout=5)
        return True
    except (urllib.error.URLError, TimeoutError, OSError):
        # Under parallel load the HTTP probe can time out while the backend is
        # still healthy and bound to its port. Never drive a crash-heal off a
        # transient probe failure — port ownership is the crash signal.
        return _api_port_listening()


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
        **_shared_stack_env(),
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
            timeout=2,
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
    home = _real_user_home()
    return Path(
        os.environ.get(
            "MYRM_DEV_STATE_DIR", str(home / ".local" / "state" / "myrm-dev")
        )
    )


def _real_user_home() -> Path:
    """Real login home — Cursor sandboxes HOME (~/.cursor2), splitting state."""
    try:
        import pwd

        return Path(pwd.getpwuid(os.getuid()).pw_dir)
    except (ImportError, KeyError, OSError):
        return Path.home()


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
