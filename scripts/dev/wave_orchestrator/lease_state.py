"""Pure lease-state transitions shared by Wave orchestration modules.

[INPUT]
- dev_gate_contract::SIGNOFF_MATRIX_AGENT_PREFIX (POS: Dev Gate v2 contract SSOT)
- wave_orchestrator.types state records
- browser/resource expiry helpers

[OUTPUT]
- time/owner helpers, active lease lookup, TTL and runtime-drift transitions
- reap_runtime_drift, signoff_chrome_lock_active, signoff_matrix_runtime_heal_allowed, signoff_wave_close_blocked, heal_open_wave_runtime_id, restore_drifted_signoff_wave (signoff lock / matrix 活跃时原地 heal runtimeId 且永不 drift-invalidate；signoff 期间禁止 idle close)

[POS]
Lock-free state policy. Callers own persistence and all external cleanup I/O.
"""

from __future__ import annotations

import os
import re
import socket
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

_dev_lib = Path(__file__).resolve().parent.parent / "lib"
_dev_lib_str = str(_dev_lib)
if _dev_lib_str not in sys.path:
    sys.path.insert(0, _dev_lib_str)

from dev_gate_contract import (
    SIGNOFF_MATRIX_AGENT_PREFIX,
    formal_chrome_e2e_runtime_heal_agent,
)
from wave_orchestrator.browser_lifecycle import cleanup_expired_browser
from wave_orchestrator.resource_ledger import cleanup_expired_lease_resources
from wave_orchestrator.types import LeaseRecord, OrchestratorState

_AGENT_ID_NONCE_RE = re.compile(r"-[0-9a-f]{8}$")
_DEAD_OWNER_HEARTBEAT_GRACE_SEC = 90


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_timestamp(moment: datetime) -> str:
    return moment.replace(microsecond=0).isoformat()


def parse_timestamp(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def default_agent_id() -> str:
    override = os.environ.get("MYRM_WAVE_AGENT_ID", "").strip()
    if override:
        return override
    return f"{socket.gethostname()}:{os.getpid()}"


def active_leases(state: OrchestratorState) -> list[LeaseRecord]:
    return [lease for lease in state["leases"] if lease["status"] == "active"]


def find_active_lease(state: OrchestratorState, lease_id: str) -> LeaseRecord:
    for lease in state["leases"]:
        if lease["leaseId"] == lease_id and lease["status"] == "active":
            return lease
    raise RuntimeError(f"LEASE_NOT_ACTIVE: {lease_id}")


def _process_is_alive(pid: int) -> bool:
    if pid <= 0:
        return False
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    return True


def owner_bashpid_from_agent_id(agent_id: str) -> int | None:
    """Parse test.sh BASHPID suffix from MYRM_E2E_RUN_ID-style agent ids."""
    normalized = agent_id.strip()
    if not normalized or not _AGENT_ID_NONCE_RE.search(normalized):
        return None
    without_nonce = normalized[: normalized.rfind("-")]
    owner_raw = without_nonce.rsplit("-", 1)[-1]
    try:
        owner_pid = int(owner_raw)
    except ValueError:
        return None
    return owner_pid if owner_pid > 0 else None


def reap_abandoned_leases(
    state: OrchestratorState,
    now: datetime | None = None,
    *,
    heartbeat_grace_sec: int = _DEAD_OWNER_HEARTBEAT_GRACE_SEC,
) -> bool:
    """Expire leases whose owner test.sh shell exited.

    Orphan pytest children may keep heartbeating after SIGTERM/SIGHUP; once the
    session owner BASHPID is gone the lease must not keep blocking LIVE_AGENT cap.
    """
    del heartbeat_grace_sec  # owner-dead is authoritative; heartbeats may linger
    changed = False
    for lease in state["leases"]:
        if lease["status"] != "active":
            continue
        agent_id = str(lease.get("agentId", ""))
        if is_signoff_matrix_agent_id(agent_id):
            continue
        owner_pid = owner_bashpid_from_agent_id(agent_id)
        if owner_pid is None or _process_is_alive(owner_pid):
            continue
        lease["status"] = "expired"
        changed = True
    return changed


def reap_expired_leases(
    state: OrchestratorState,
    now: datetime | None = None,
    *,
    cleanup: bool = True,
) -> bool:
    moment = now or utc_now()
    changed = False
    for lease in state["leases"]:
        if lease["status"] != "active":
            continue
        if parse_timestamp(lease["expiresAt"]) <= moment:
            lease["status"] = "expired"
            changed = True
    if cleanup:
        changed = cleanup_expired_browser(state) or changed
        changed = cleanup_expired_lease_resources(state) or changed
    return changed


def is_signoff_matrix_agent_id(agent_id: str) -> bool:
    return agent_id.startswith(SIGNOFF_MATRIX_AGENT_PREFIX)


def signoff_chrome_lock_active() -> bool:
    """True while ./myrm signoff chrome holds signoff-chrome.lock with a live owner."""
    from .paths import resolve_dev_state_dir

    lock_path = resolve_dev_state_dir() / "signoff-chrome.lock"
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


def signoff_matrix_guard_active(state: OrchestratorState) -> bool:
    """True while Dev Gate signoff matrix holds an active LIVE_AGENT session."""
    return any(
        is_signoff_matrix_agent_id(str(lease.get("agentId", "")))
        for lease in active_leases(state)
    )


def signoff_matrix_runtime_heal_allowed(state: OrchestratorState) -> bool:
    """Allow in-place runtime heal during signoff matrix parent bootstrap or active session."""
    if signoff_matrix_guard_active(state):
        return True
    if os.environ.get("MYRM_SIGNOFF_MATRIX", "").strip() == "1":
        return True
    return signoff_chrome_lock_active()


def parallel_chrome_e2e_runtime_heal_allowed(state: OrchestratorState) -> bool:
    """Allow in-place runtime heal while formal chrome E2E sessions hold active leases."""
    if signoff_matrix_runtime_heal_allowed(state):
        return True
    return any(
        formal_chrome_e2e_runtime_heal_agent(str(lease.get("agentId", "")))
        for lease in active_leases(state)
    )


def signoff_wave_close_blocked(state: OrchestratorState) -> bool:
    """Block idle-wave close while Dev Gate signoff chrome or matrix session is active."""
    if signoff_chrome_lock_active():
        return True
    return signoff_matrix_guard_active(state)


def heal_open_wave_runtime_id(
    state: OrchestratorState,
    current_runtime_id: str,
) -> bool:
    """Migrate open wave + active leases to a new runtimeId without invalidating tests."""
    wave = state["wave"]
    if wave is None or wave["status"] != "open":
        return False
    if not current_runtime_id or current_runtime_id == wave["runtimeId"]:
        return False
    if not parallel_chrome_e2e_runtime_heal_allowed(state):
        return False

    wave_id = wave["waveId"]
    wave["runtimeId"] = current_runtime_id
    for lease in active_leases(state):
        if lease["waveId"] == wave_id:
            lease["runtimeId"] = current_runtime_id
    return True


def restore_drifted_signoff_wave(
    state: OrchestratorState,
    current_runtime_id: str,
) -> bool:
    """Re-open a drifted wave and reactivate leases during signoff heal windows."""
    wave = state["wave"]
    if wave is None or wave["status"] != "drifted":
        return False
    if not current_runtime_id:
        return False
    if not parallel_chrome_e2e_runtime_heal_allowed(state):
        return False

    wave_id = wave["waveId"]
    wave["status"] = "open"
    wave["runtimeId"] = current_runtime_id
    wave.pop("closedAt", None)
    changed = False
    for lease in state["leases"]:
        if lease["waveId"] != wave_id or lease["status"] != "expired":
            continue
        lease["status"] = "active"
        lease["runtimeId"] = current_runtime_id
        changed = True
    return changed


def reap_runtime_drift(state: OrchestratorState, current_runtime_id: str) -> bool:
    """Invalidate an open wave on runtime drift, or heal in-place during signoff matrix."""
    wave = state["wave"]
    if wave is None:
        return False
    if wave["status"] == "drifted":
        return restore_drifted_signoff_wave(state, current_runtime_id)
    if wave["status"] != "open":
        return False
    if not current_runtime_id or current_runtime_id == wave["runtimeId"]:
        return False

    if heal_open_wave_runtime_id(state, current_runtime_id):
        return True

    if parallel_chrome_e2e_runtime_heal_allowed(state):
        # Formal chrome E2E / signoff: heal in-place; never drift-invalidate active sessions.
        return restore_drifted_signoff_wave(state, current_runtime_id)

    wave["status"] = "drifted"
    wave["closedAt"] = iso_timestamp(utc_now())
    for lease in active_leases(state):
        lease["status"] = "expired"
    return True


def close_wave_after_last_expired_lease(state: OrchestratorState) -> bool:
    wave = state["wave"]
    if wave is None or wave["status"] != "open":
        return False
    if signoff_wave_close_blocked(state):
        return False
    wave_leases = [
        lease for lease in state["leases"] if lease["waveId"] == wave["waveId"]
    ]
    if not wave_leases or any(lease["status"] == "active" for lease in wave_leases):
        return False
    if not any(lease["status"] == "expired" for lease in wave_leases):
        return False
    wave["status"] = "closed"
    wave["closedAt"] = iso_timestamp(utc_now())
    return True
