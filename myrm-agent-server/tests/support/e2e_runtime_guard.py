"""Validate that live E2E tests own an active immutable-wave lease."""

from __future__ import annotations

import json
import os
import subprocess
import sys
import threading
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

    def register(self, kind: ResourceKind, ref: str) -> None:
        heartbeat_e2e_lease()
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
        timeout=10,
        check=False,
    )
    if result.returncode != 0:
        message = result.stderr or result.stdout
        if "LEASE_NOT_ACTIVE" in message or "LEASE_NOT_FOUND" in message:
            return
        raise RuntimeError(f"E2E_LEASE_HEARTBEAT_FAIL: {message}")


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


def _runtime_id_reader() -> str:
    if _isolated_e2e_mode():
        return _stack_scoped_runtime_id()
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
        raise RuntimeError(f"RUNTIME_DRIFT: E2E lease expected={expected or '<missing>'} current={current or '<missing>'}")
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
    if current != lease.runtime_id:
        raise RuntimeError(f"RUNTIME_DRIFT: E2E lease expected={lease.runtime_id} current={current or '<missing>'}")
