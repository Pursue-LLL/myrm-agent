"""Validate that live E2E tests own an active immutable-wave lease."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
import time
from collections.abc import Callable, Iterator
from contextlib import contextmanager
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import TypedDict, cast

_DEV_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_DEV_LIB) not in sys.path:
    sys.path.insert(0, str(_DEV_LIB))

from e2e_lease_heartbeat import heartbeat_e2e_lease
from e2e_resource_ledger import E2EResourceLedger as _E2EResourceLedger

_E2E_HEARTBEAT_INTERVAL_SEC = 30.0
E2EResourceLedger = _E2EResourceLedger


class _LeasePayload(TypedDict):
    leaseId: str
    agentId: str
    lane: str
    runtimeId: str
    status: str
    expiresAt: str


@dataclass(frozen=True, slots=True)
class E2ERuntimeLease:
    lease_id: str
    runtime_id: str
    lane: str
    isolated: bool = False


def reap_chrome_e2e_session_hygiene() -> None:
    """Extend parent lease heartbeat only — no global wave/tab/peer reaper (P0-B)."""
    heartbeat_e2e_lease()


@contextmanager
def e2e_lease_heartbeat_loop(
    *, interval_sec: float = _E2E_HEARTBEAT_INTERVAL_SEC
) -> Iterator[None]:
    """Background heartbeat for long-running live E2E tests."""
    from e2e_unified_heartbeat import heartbeat_once, pytest_should_spawn_heartbeat_loop

    heartbeat_once()
    if not pytest_should_spawn_heartbeat_loop():
        yield
        heartbeat_once()
        return

    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(interval_sec):
            heartbeat_once()

    worker = threading.Thread(target=_loop, name="e2e-lease-heartbeat", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=2.0)


def _wave_state_path() -> Path:
    dev_lib = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
    dev_lib_str = str(dev_lib)
    if dev_lib_str not in sys.path:
        sys.path.insert(0, dev_lib_str)
    from wave_state_paths import resolve_wave_state_file

    return resolve_wave_state_file()


def _isolated_e2e_mode() -> bool:
    return os.environ.get("MYRM_E2E_ISOLATED", "").strip() == "1"


def _stack_scoped_runtime_id() -> str:
    dev_lib = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
    if str(dev_lib) not in sys.path:
        sys.path.insert(0, str(dev_lib))
    from runtime_identity import read_stack_scoped_runtime_id

    return read_stack_scoped_runtime_id()


def _stack_fingerprint_runtime_id() -> str:
    return os.environ.get("MYRM_E2E_STACK_FP", "").strip()


def _private_backend_runtime_pinned() -> bool:
    """SHPOIB private backend pins MYRM_E2E_STACK_FP; ignore shared-hot drift under parallel E2E."""
    return os.environ.get("MYRM_E2E_PRIVATE_BACKEND", "").strip() == "1" and bool(
        _stack_fingerprint_runtime_id()
    )


def _formal_chrome_e2e_runtime_heal_allowed() -> bool:
    """Allow in-place wave heal for ./myrm test chrome_e2e parent sessions."""
    dev_lib = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
    if str(dev_lib) not in sys.path:
        sys.path.insert(0, str(dev_lib))
    from dev_gate_contract import formal_chrome_e2e_runtime_heal_agent

    return formal_chrome_e2e_runtime_heal_agent(os.environ.get("MYRM_E2E_AGENT_ID", ""))


def _runtime_drift_heal_allowed() -> bool:
    return _formal_chrome_e2e_runtime_heal_allowed()


def _uses_shared_hot_runtime_probe() -> bool:
    return _runtime_drift_heal_allowed()


def _shared_hot_stack_runtime_id() -> str:
    dev_lib = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
    if str(dev_lib) not in sys.path:
        sys.path.insert(0, str(dev_lib))
    from runtime_probe import _read_shared_hot_stack_runtime_id

    return _read_shared_hot_stack_runtime_id()


def _read_open_wave_runtime_id(state_path: Path) -> str:
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return ""
    wave = payload.get("wave") if isinstance(payload, dict) else None
    if not isinstance(wave, dict) or wave.get("status") != "open":
        return ""
    return str(wave.get("runtimeId", "")).strip()


def _runtime_drift_setup_attempts() -> int:
    raw = os.environ.get("MYRM_E2E_RUNTIME_DRIFT_SETUP_RETRIES", "").strip()
    if raw.isdigit() and int(raw) > 0:
        return int(raw)
    if os.environ.get("E2E_SIGNOFF", "").strip() == "1":
        return 5
    return 3


def _global_wave_reap_allowed() -> bool:
    """P0-A: pytest body must NEVER invoke global wave reap — Coordinator-only.

    Always returns False. Wave reap is exclusively triggered by the Coordinator
    via `dev-gate coordinator-reap`, never from within a test process. This
    prevents peer session destruction under parallel execution.
    """
    return False


def _attempt_runtime_drift_heal(state_path: Path, lease_id: str) -> str | None:
    """Read-only drift detection — reap is Coordinator-only (P0-A).

    Re-reads wave state to detect if Coordinator has already healed the drift.
    Never triggers subprocess reap from within the test process.
    """
    if not _runtime_drift_heal_allowed():
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    lease = _active_lease(payload, lease_id)
    if lease is None:
        return None
    healed = str(lease.get("runtimeId", "")).strip()
    wave_runtime = _read_open_wave_runtime_id(state_path)
    if wave_runtime:
        healed = wave_runtime
    if not healed:
        return None
    os.environ["MYRM_E2E_STACK_FP"] = healed
    return healed


def _assert_runtime_matches_lease_or_heal(
    *,
    state_path: Path,
    lease_id: str,
    expected: str,
    runtime_id_reader: Callable[[], str],
) -> str:
    """Wait for Coordinator-driven drift heal; fail fast if unresolved (P0-A)."""
    resolved = expected.strip()
    current = runtime_id_reader().strip()
    if not _runtime_drift_heal_allowed():
        if not resolved or current != resolved:
            raise RuntimeError(
                f"RUNTIME_DRIFT: E2E lease expected={resolved or '<missing>'} current={current or '<missing>'}"
            )
        return resolved
    attempts = _runtime_drift_setup_attempts()
    for drift_attempt in range(attempts):
        current = runtime_id_reader().strip()
        if resolved and current == resolved:
            return resolved
        healed = _attempt_runtime_drift_heal(state_path, lease_id)
        if healed:
            resolved = healed
        wave_runtime = _read_open_wave_runtime_id(state_path)
        if wave_runtime:
            resolved = wave_runtime
        current = runtime_id_reader().strip()
        if resolved and current == resolved:
            return resolved
        if drift_attempt + 1 < attempts:
            time.sleep(2.0)
    current = runtime_id_reader().strip()
    raise RuntimeError(
        f"RUNTIME_DRIFT: E2E lease expected={resolved or '<missing>'} current={current or '<missing>'}"
    )


def _runtime_id_reader() -> str:
    if _isolated_e2e_mode():
        return _stack_scoped_runtime_id()
    if _private_backend_runtime_pinned():
        return _stack_fingerprint_runtime_id()
    if _uses_shared_hot_runtime_probe():
        return _shared_hot_stack_runtime_id()
    stack_fp = _stack_fingerprint_runtime_id()
    if stack_fp:
        return stack_fp
    dev_lib = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
    if str(dev_lib) not in sys.path:
        sys.path.insert(0, str(dev_lib))
    from runtime_probe import read_current_runtime_id

    return read_current_runtime_id()


def _assert_isolated_stack_unchanged(*, expected: str) -> None:
    current = _stack_scoped_runtime_id().strip()
    if not expected or current != expected:
        raise RuntimeError(
            f"RUNTIME_DRIFT: isolated stack expected={expected or '<missing>'} current={current or '<missing>'}"
        )


def _active_lease(payload: object, lease_id: str) -> _LeasePayload | None:
    if not isinstance(payload, dict):
        return None
    leases = payload.get("leases")
    if not isinstance(leases, list):
        return None
    for item in leases:
        if isinstance(item, dict) and item.get("leaseId") == lease_id:
            return cast(_LeasePayload, item)
    return None


def _heal_stale_e2e_lease() -> None:
    """Best-effort heal when parallel wave reap races pytest fixture setup."""
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    if not lease_id:
        return
    dev_lib = str(_DEV_LIB)
    if dev_lib not in sys.path:
        sys.path.insert(0, dev_lib)
    from e2e_lease_runtime_sync import sync_lease_runtime_with_shared_hot

    sync_lease_runtime_with_shared_hot(lease_id=lease_id)
    heartbeat_e2e_lease()
    time.sleep(0.25)


def _require_e2e_runtime_lease_once(
    *,
    runtime_id_reader: Callable[[], str] = _runtime_id_reader,
) -> E2ERuntimeLease:
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    if not lease_id:
        raise RuntimeError(
            "E2E_LEASE_REQUIRED: run live tests via ./myrm test -m e2e; direct pytest/uv entry is blocked"
        )
    state_path = _wave_state_path()
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise RuntimeError(f"E2E_LEASE_INVALID: cannot read {state_path}") from exc
    lease = _active_lease(payload, lease_id)
    wave = payload.get("wave") if isinstance(payload, dict) else None
    if not isinstance(wave, dict) or wave.get("status") != "open":
        raise RuntimeError("E2E_LEASE_INVALID: immutable test wave is not open")
    if lease is None or lease.get("status") != "active":
        raise RuntimeError(f"E2E_LEASE_INVALID: lease {lease_id} is not active")
    expected_agent = os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
    if not expected_agent:
        raise RuntimeError("E2E_AGENT_REQUIRED: run live tests via ./myrm test -m e2e")
    if lease.get("agentId") != expected_agent:
        raise RuntimeError(
            f"E2E_LEASE_INVALID: lease {lease_id} owner={lease.get('agentId')} does not match MYRM_E2E_AGENT_ID={expected_agent}"
        )
    expected_lane = os.environ.get("MYRM_E2E_LANE", "LIVE_AGENT").strip().upper()
    if expected_lane not in {"READ", "RESOURCE_WRITE", "GLOBAL_WRITE", "LIVE_AGENT"}:
        raise RuntimeError(
            f"E2E_LANE_INVALID: MYRM_E2E_LANE must be READ, RESOURCE_WRITE, GLOBAL_WRITE, or LIVE_AGENT, got {expected_lane}"
        )
    if lease.get("lane") != expected_lane:
        raise RuntimeError(
            f"E2E_LEASE_INVALID: lease {lease_id} lane={lease.get('lane')} does not match MYRM_E2E_LANE={expected_lane}"
        )
    expires_at = lease.get("expiresAt")
    try:
        expires = datetime.fromisoformat(expires_at.replace("Z", "+00:00"))
    except (AttributeError, ValueError) as exc:
        raise RuntimeError(
            f"E2E_LEASE_INVALID: lease {lease_id} expiry is invalid"
        ) from exc
    if expires <= datetime.now(UTC):
        raise RuntimeError(f"E2E_LEASE_INVALID: lease {lease_id} is expired")
    expected = lease.get("runtimeId", "").strip()
    wave_runtime = str(wave.get("runtimeId", "")).strip()
    if (
        _uses_shared_hot_runtime_probe()
        and wave_runtime
        and not _private_backend_runtime_pinned()
    ):
        expected = wave_runtime
    if wave.get("runtimeId") != expected:
        raise RuntimeError(
            f"E2E_LEASE_INVALID: lease {lease_id} runtime does not match open wave"
        )
    if _isolated_e2e_mode():
        stack_fp = (
            os.environ.get("MYRM_E2E_STACK_FP", "").strip()
            or _stack_scoped_runtime_id()
        )
        _assert_isolated_stack_unchanged(expected=stack_fp)
        return E2ERuntimeLease(
            lease_id=lease_id,
            runtime_id=stack_fp,
            lane=expected_lane,
            isolated=True,
        )
    expected = _assert_runtime_matches_lease_or_heal(
        state_path=state_path,
        lease_id=lease_id,
        expected=expected,
        runtime_id_reader=runtime_id_reader,
    )
    return E2ERuntimeLease(lease_id=lease_id, runtime_id=expected, lane=expected_lane)


def require_e2e_runtime_lease(
    *,
    runtime_id_reader: Callable[[], str] = _runtime_id_reader,
) -> E2ERuntimeLease:
    last_error: RuntimeError | None = None
    for attempt in range(3):
        try:
            return _require_e2e_runtime_lease_once(runtime_id_reader=runtime_id_reader)
        except RuntimeError as exc:
            last_error = exc
            message = str(exc)
            retryable = "is not active" in message or "is expired" in message
            if not retryable or attempt >= 2:
                raise
            _heal_stale_e2e_lease()
    if last_error is not None:
        raise last_error
    raise RuntimeError("E2E_LEASE_INVALID: lease validation failed")


def assert_e2e_runtime_unchanged(
    lease: E2ERuntimeLease,
    *,
    runtime_id_reader: Callable[[], str] = _runtime_id_reader,
) -> None:
    if lease.isolated or _isolated_e2e_mode():
        expected = (
            lease.runtime_id.strip() or os.environ.get("MYRM_E2E_STACK_FP", "").strip()
        )
        _assert_isolated_stack_unchanged(expected=expected)
        return
    current = runtime_id_reader().strip()
    expected_runtime = lease.runtime_id.strip()
    if _uses_shared_hot_runtime_probe() and not _private_backend_runtime_pinned():
        expected_runtime = _shared_hot_stack_runtime_id().strip() or expected_runtime
    if current != expected_runtime:
        healed = _attempt_runtime_drift_heal(_wave_state_path(), lease.lease_id)
        if healed and healed == runtime_id_reader().strip():
            return
        raise RuntimeError(
            f"RUNTIME_DRIFT: E2E lease expected={expected_runtime} current={current or '<missing>'}"
        )


def assert_chrome_attach_health() -> None:
    """Fail fast when Chrome mux/CDP attach snapshot is unsafe for live UI E2E."""
    script = (
        Path(__file__).resolve().parents[3]
        / "scripts"
        / "dev"
        / "lib"
        / "runtime_identity.py"
    )
    ui_base = os.environ.get("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
    api_base = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8080").rstrip("/")
    wait_sec = int(os.environ.get("MYRM_CHROME_E2E_ATTACH_WAIT_SEC", "180"))
    poll_sec = int(os.environ.get("MYRM_CHROME_E2E_ATTACH_POLL_SEC", "2"))
    if wait_sec < 0:
        wait_sec = 180
    if poll_sec <= 0:
        poll_sec = 2

    require_ready = (
        "--require-signoff-stream-ready"
        if os.environ.get("E2E_SIGNOFF", "").strip() == "1"
        else "--require-attach-ready"
    )

    cmd = [
        sys.executable,
        str(script),
        "--auto-probe",
        "--auto-hot",
        "--attach-mode",
        require_ready,
        "--ui",
        ui_base,
        "--api",
        api_base,
    ]
    deadline = time.monotonic() + float(max(wait_sec, 1))
    last_detail = "unknown attach probe failure"
    while time.monotonic() < deadline:
        remaining = deadline - time.monotonic()
        proc_timeout = min(60, max(1, int(remaining)))
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=proc_timeout,
            check=False,
        )
        if proc.returncode == 0:
            return
        last_detail = (
            proc.stderr.strip() or proc.stdout.strip() or f"exit={proc.returncode}"
        )
        if time.monotonic() >= deadline:
            break
        sleep_for = min(float(poll_sec), max(0.0, deadline - time.monotonic()))
        if sleep_for > 0:
            time.sleep(sleep_for)
    raise RuntimeError(f"CHROME_E2E_ATTACH_NOT_READY: {last_detail}")
