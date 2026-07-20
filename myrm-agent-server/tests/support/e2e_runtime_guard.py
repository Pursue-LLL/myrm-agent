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
from typing import Literal, TypedDict, cast

ResourceKind = Literal["chat", "project", "agent", "cron", "file", "kanban_board", "kanban_task"]

_E2E_HEARTBEAT_INTERVAL_SEC = 30.0
_E2E_HEARTBEAT_EXTEND_SEC = 900


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


@dataclass(frozen=True, slots=True)
class E2EResourceLedger:
    lease_id: str
    namespace: str
    ephemeral_runtime: bool = False

    def register(self, kind: ResourceKind, ref: str) -> None:
        heartbeat_e2e_lease()
        if self.ephemeral_runtime:
            return
        register_e2e_resource(
            self.lease_id,
            kind=kind,
            ref=ref,
            namespace=self.namespace,
        )


def _wave_script() -> Path:
    return Path(__file__).resolve().parents[3] / "scripts/dev/wave.sh"


def _ledger_agent_id() -> str:
    return os.environ.get("MYRM_E2E_AGENT_ID", "").strip() or f"pytest-ledger:{os.getpid()}"


def heartbeat_e2e_lease() -> None:
    """Extend the active LIVE_AGENT (or other) lease TTL during long UI E2E runs."""
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    agent_id = os.environ.get("MYRM_E2E_AGENT_ID", "").strip()
    if not lease_id or not agent_id:
        return
    result = subprocess.run(
        [
            "bash",
            str(_wave_script()),
            "--agent",
            agent_id,
            "lease",
            "heartbeat",
            lease_id,
            "--extend",
            str(_E2E_HEARTBEAT_EXTEND_SEC),
        ],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr or result.stdout
        if "LEASE_NOT_ACTIVE" in message or "LEASE_NOT_FOUND" in message:
            return
        if "TimeoutError" in message or "timed out" in message:
            return
        raise RuntimeError(f"E2E_LEASE_HEARTBEAT_FAIL: {message}")


def reap_chrome_e2e_session_hygiene() -> None:
    """Extend parent lease and reap stale page leases between formal chrome_e2e items."""
    heartbeat_e2e_lease()
    wave_script = _wave_script()
    subprocess.run(
        ["bash", str(wave_script), "reap"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    dev_scripts = Path(__file__).resolve().parents[3] / "scripts" / "dev"
    prune_script = dev_scripts / "prune-myrm-chrome-e2e-blank-tabs.sh"
    if prune_script.is_file():
        subprocess.run(
            ["bash", str(prune_script)],
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )


def register_e2e_resource(
    lease_id: str,
    *,
    kind: ResourceKind,
    ref: str,
    namespace: str,
) -> None:
    resource_ref = ref.strip()
    if not resource_ref:
        raise ValueError("E2E resource ref must not be empty")
    ns = namespace.strip()
    if not ns:
        raise ValueError("E2E resource namespace must not be empty")
    result = subprocess.run(
        [
            "bash",
            str(_wave_script()),
            "--agent",
            _ledger_agent_id(),
            "ledger",
            "register",
            lease_id,
            kind,
            resource_ref,
            "--namespace",
            ns,
        ],
        capture_output=True,
        text=True,
        timeout=10,
        check=False,
    )
    if result.returncode == 0:
        return
    message = result.stderr or result.stdout
    if "already registered" in message:
        return
    if "active lease not found" in message or "LEASE_NOT_ACTIVE" in message:
        return
    raise RuntimeError(f"E2E_LEDGER_REGISTER_FAIL: {message}")


@contextmanager
def e2e_lease_heartbeat_loop(*, interval_sec: float = _E2E_HEARTBEAT_INTERVAL_SEC) -> Iterator[None]:
    """Background heartbeat for long-running live E2E tests."""
    stop = threading.Event()

    def _loop() -> None:
        while not stop.wait(interval_sec):
            heartbeat_e2e_lease()

    heartbeat_e2e_lease()
    worker = threading.Thread(target=_loop, name="e2e-lease-heartbeat", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=2.0)


def _state_file() -> Path:
    wave_override = os.environ.get("MYRM_WAVE_STATE_DIR", "").strip()
    if wave_override:
        root = Path(wave_override)
    else:
        override = os.environ.get("MYRM_DEV_STATE_DIR", "").strip()
        root = Path(override) if override else Path.home() / ".local/state/myrm-dev"
    return root / "wave-orchestrator.json"


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


def _signoff_shared_hot_runtime_probe_active() -> bool:
    """Match wave_orchestrator.core._signoff_shared_hot_runtime_probe during signoff."""
    if os.environ.get("MYRM_SIGNOFF_MATRIX", "").strip() == "1":
        return True
    state_dir = Path(
        os.environ.get("MYRM_DEV_STATE_DIR", str(Path.home() / ".local/state/myrm-dev"))
    )
    lock_path = state_dir / "signoff-chrome.lock"
    if not lock_path.is_file():
        return False
    try:
        owner_raw = lock_path.read_text(encoding="utf-8").strip().split()[0]
        owner_pid = int(owner_raw)
    except (OSError, ValueError):
        return True
    if owner_pid <= 0:
        return True
    try:
        os.kill(owner_pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def _shared_hot_stack_runtime_id() -> str:
    dev_lib = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
    if str(dev_lib) not in sys.path:
        sys.path.insert(0, str(dev_lib))
    from runtime_probe import _read_shared_hot_stack_runtime_id

    return _read_shared_hot_stack_runtime_id()


def _attempt_signoff_runtime_heal(state_path: Path, lease_id: str) -> str | None:
    """In-place heal wave + active leases when shared-hot runtime drifts during signoff."""
    if not _signoff_shared_hot_runtime_probe_active():
        return None
    result = subprocess.run(
        ["bash", str(_wave_script()), "reap"],
        capture_output=True,
        text=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        return None
    try:
        payload = json.loads(state_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        return None
    lease = _active_lease(payload, lease_id)
    if lease is None:
        return None
    healed = str(lease.get("runtimeId", "")).strip()
    if not healed:
        return None
    os.environ["MYRM_E2E_STACK_FP"] = healed
    return healed


def _runtime_id_reader() -> str:
    if _isolated_e2e_mode():
        return _stack_scoped_runtime_id()
    if _signoff_shared_hot_runtime_probe_active():
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


def require_e2e_runtime_lease(
    *,
    runtime_id_reader: Callable[[], str] = _runtime_id_reader,
) -> E2ERuntimeLease:
    lease_id = os.environ.get("MYRM_E2E_LEASE_ID", "").strip()
    if not lease_id:
        raise RuntimeError("E2E_LEASE_REQUIRED: run live tests via ./myrm test -m e2e; direct pytest/uv entry is blocked")
    state_path = _state_file()
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
        raise RuntimeError(f"E2E_LEASE_INVALID: lease {lease_id} expiry is invalid") from exc
    if expires <= datetime.now(UTC):
        raise RuntimeError(f"E2E_LEASE_INVALID: lease {lease_id} is expired")
    expected = lease.get("runtimeId", "").strip()
    wave_runtime = str(wave.get("runtimeId", "")).strip()
    if _signoff_shared_hot_runtime_probe_active() and wave_runtime:
        expected = wave_runtime
    if wave.get("runtimeId") != expected:
        raise RuntimeError(f"E2E_LEASE_INVALID: lease {lease_id} runtime does not match open wave")
    if _isolated_e2e_mode():
        stack_fp = os.environ.get("MYRM_E2E_STACK_FP", "").strip() or _stack_scoped_runtime_id()
        _assert_isolated_stack_unchanged(expected=stack_fp)
        return E2ERuntimeLease(
            lease_id=lease_id,
            runtime_id=stack_fp,
            lane=expected_lane,
            isolated=True,
        )
    current = runtime_id_reader().strip()
    if not expected or current != expected:
        healed = _attempt_signoff_runtime_heal(state_path, lease_id)
        if healed:
            expected = healed
            current = runtime_id_reader().strip()
        if not expected or current != expected:
            raise RuntimeError(
                f"RUNTIME_DRIFT: E2E lease expected={expected or '<missing>'} current={current or '<missing>'}"
            )
    return E2ERuntimeLease(lease_id=lease_id, runtime_id=expected, lane=expected_lane)


def assert_e2e_runtime_unchanged(
    lease: E2ERuntimeLease,
    *,
    runtime_id_reader: Callable[[], str] = _runtime_id_reader,
) -> None:
    if lease.isolated or _isolated_e2e_mode():
        expected = lease.runtime_id.strip() or os.environ.get("MYRM_E2E_STACK_FP", "").strip()
        _assert_isolated_stack_unchanged(expected=expected)
        return
    current = runtime_id_reader().strip()
    expected_runtime = lease.runtime_id.strip()
    if _signoff_shared_hot_runtime_probe_active():
        dev_lib = Path(__file__).resolve().parents[3] / "scripts/dev/lib"
        if str(dev_lib) not in sys.path:
            sys.path.insert(0, str(dev_lib))
        from runtime_probe import _read_shared_hot_stack_runtime_id

        expected_runtime = _read_shared_hot_stack_runtime_id().strip() or expected_runtime
    if current != expected_runtime:
        healed = _attempt_signoff_runtime_heal(_state_file(), lease.lease_id)
        if healed and healed == runtime_id_reader().strip():
            return
        raise RuntimeError(f"RUNTIME_DRIFT: E2E lease expected={expected_runtime} current={current or '<missing>'}")


def assert_chrome_attach_health() -> None:
    """Fail fast when Chrome mux/CDP attach snapshot is unsafe for live UI E2E."""
    script = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib" / "runtime_identity.py"
    ui_base = os.environ.get("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
    api_base = os.environ.get("E2E_API_BASE", "http://127.0.0.1:8080").rstrip("/")
    wait_sec = int(os.environ.get("MYRM_CHROME_E2E_ATTACH_WAIT_SEC", "180"))
    poll_sec = int(os.environ.get("MYRM_CHROME_E2E_ATTACH_POLL_SEC", "2"))
    if wait_sec < 0:
        wait_sec = 180
    if poll_sec <= 0:
        poll_sec = 2

    cmd = [
        sys.executable,
        str(script),
        "--auto-probe",
        "--auto-hot",
        "--attach-mode",
        "--require-attach-ready",
        "--ui",
        ui_base,
        "--api",
        api_base,
    ]
    waited = 0
    last_detail = "unknown attach probe failure"
    while waited <= wait_sec:
        proc = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            timeout=60,
            check=False,
        )
        if proc.returncode == 0:
            return
        last_detail = proc.stderr.strip() or proc.stdout.strip() or f"exit={proc.returncode}"
        if waited >= wait_sec:
            break
        time.sleep(poll_sec)
        waited += poll_sec
    raise RuntimeError(f"CHROME_E2E_ATTACH_NOT_READY: {last_detail}")
