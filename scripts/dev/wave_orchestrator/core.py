"""Wave lifecycle, lease management, and STACK_WRITE gate.

[INPUT]
- wave_orchestrator.store::run_locked (POS: flock-protected JSON state I/O)
- runtime_probe.read_current_runtime_id (POS: live stack identity probe)

[OUTPUT]
- open_wave() / close_wave() / acquire_lease() / release_lease() / heartbeat_lease()
- check_stack_write_gate() — active lease blocks dev-stack reset

[POS]
Dev test wave orchestrator core. Enforces immutable test waves for Chrome MCP E2E.
"""

from __future__ import annotations

import os
import socket
import uuid
from datetime import datetime, timedelta, timezone
from typing import TypedDict

from wave_orchestrator.lanes import lane_conflict_reason
from wave_orchestrator.browser_lifecycle import (
    bind_browser,
    cleanup_expired_browser,
    cleanup_lease_browser,
    unbind_browser,
)
from wave_orchestrator.paths import WavePaths, resolve_wave_paths
from wave_orchestrator.resource_ledger import cleanup_lease_resources, cleanup_expired_lease_resources
from wave_orchestrator.store import run_locked
from wave_orchestrator.types import Lane, LeaseRecord, OrchestratorState, WaveRecord


class GateBlocker(TypedDict):
    leaseId: str
    agentId: str
    lane: Lane


class GateResult(TypedDict):
    allowed: bool
    blockers: list[GateBlocker]


DEFAULT_LEASE_TTL_SEC = 3600
DEFAULT_HEARTBEAT_EXTEND_SEC = 3600


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _parse_iso(value: str) -> datetime:
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def default_agent_id() -> str:
    override = os.environ.get("MYRM_WAVE_AGENT_ID", "").strip()
    if override:
        return override
    host = socket.gethostname()
    return f"{host}:{os.getpid()}"


def _import_runtime_probe():
    import sys
    from pathlib import Path

    lib_dir = Path(__file__).resolve().parent.parent / "lib"
    lib_str = str(lib_dir)
    if lib_str not in sys.path:
        sys.path.insert(0, lib_str)
    import runtime_probe

    return runtime_probe


def probe_runtime_id() -> str:
    runtime_probe = _import_runtime_probe()
    return runtime_probe.read_current_runtime_id()


def reaper(state: OrchestratorState, now: datetime | None = None) -> bool:
    moment = now or _utc_now()
    changed = False
    for lease in state["leases"]:
        if lease["status"] != "active":
            continue
        if _parse_iso(lease["expiresAt"]) <= moment:
            lease["status"] = "expired"
            changed = True
    if cleanup_expired_browser(state):
        changed = True
    if cleanup_expired_lease_resources(state):
        changed = True
    return changed


def reap_runtime_drift(state: OrchestratorState, current_runtime_id: str) -> bool:
    """Invalidate an open wave before stale test leases can report success."""
    wave = state["wave"]
    if wave is None or wave["status"] != "open":
        return False
    if not current_runtime_id or current_runtime_id == wave["runtimeId"]:
        return False

    now = _utc_now()
    wave["status"] = "drifted"
    wave["closedAt"] = _iso(now)
    for lease in active_leases(state):
        lease["status"] = "expired"
    cleanup_expired_browser(state)
    cleanup_expired_lease_resources(state)
    return True


def reap(*, paths: WavePaths | None = None) -> dict[str, object]:
    """Run TTL and runtime drift reaping for the supervisor watchdog."""
    resolved = paths or resolve_wave_paths()
    current_runtime = probe_runtime_id()

    def _edit(state: OrchestratorState) -> tuple[dict[str, object], bool]:
        changed = reaper(state)
        if reap_runtime_drift(state, current_runtime):
            changed = True
        return {
            "wave": state["wave"],
            "runtimeId": current_runtime,
            "activeLeaseCount": len(active_leases(state)),
        }, changed

    return run_locked(resolved.state_file, _edit)


def active_leases(state: OrchestratorState) -> list[LeaseRecord]:
    return [lease for lease in state["leases"] if lease["status"] == "active"]


def _find_active_lease(state: OrchestratorState, lease_id: str) -> LeaseRecord:
    for lease in state["leases"]:
        if lease["leaseId"] == lease_id and lease["status"] == "active":
            return lease
    raise RuntimeError(f"LEASE_NOT_ACTIVE: {lease_id}")


def open_wave(
    *,
    paths: WavePaths | None = None,
    agent_id: str | None = None,
    runtime_id: str | None = None,
) -> WaveRecord:
    resolved = paths or resolve_wave_paths()
    frozen_runtime = (runtime_id or probe_runtime_id()).strip()
    if not frozen_runtime:
        raise RuntimeError("WAVE_OPEN_FAIL: runtimeId probe returned empty")

    def _edit(state: OrchestratorState) -> tuple[WaveRecord, bool]:
        reaper(state)
        if state["wave"] is not None and state["wave"]["status"] == "open":
            raise RuntimeError(
                f"WAVE_ALREADY_OPEN: waveId={state['wave']['waveId']} "
                f"runtimeId={state['wave']['runtimeId']}"
            )
        now = _utc_now()
        wave: WaveRecord = {
            "waveId": str(uuid.uuid4()),
            "status": "open",
            "runtimeId": frozen_runtime,
            "openedAt": _iso(now),
            "closedAt": None,
            "openedBy": agent_id or default_agent_id(),
        }
        state["wave"] = wave
        return wave, True

    return run_locked(resolved.state_file, _edit)


def close_wave(*, paths: WavePaths | None = None, force: bool = False) -> WaveRecord | None:
    resolved = paths or resolve_wave_paths()
    released_ids: list[str] = []

    def _edit(state: OrchestratorState) -> tuple[WaveRecord | None, bool]:
        reaper(state)
        wave = state["wave"]
        if wave is None or wave["status"] != "open":
            raise RuntimeError("WAVE_NOT_OPEN")
        blockers = active_leases(state)
        if blockers and not force:
            owners = ", ".join(
                f"{item['leaseId']}({item['agentId']}/{item['lane']})" for item in blockers
            )
            raise RuntimeError(f"WAVE_CLOSE_BLOCKED: active leases: {owners}")
        now = _utc_now()
        for lease in blockers:
            released_ids.append(lease["leaseId"])
            lease["status"] = "released"
            cleanup_lease_browser(lease)
        closed: WaveRecord = {**wave, "status": "closed", "closedAt": _iso(now)}
        state["wave"] = closed
        return closed, True

    closed = run_locked(resolved.state_file, _edit)
    if force:
        for lease_id in released_ids:
            cleanup_lease_resources(lease_id, paths=resolved)
    return closed


def wave_status(*, paths: WavePaths | None = None) -> dict[str, object]:
    resolved = paths or resolve_wave_paths()

    def _view(state: OrchestratorState) -> tuple[dict[str, object], bool]:
        changed = reaper(state)
        active = active_leases(state)
        payload = {
            "wave": state["wave"],
            "activeLeaseCount": len(active),
            "activeLeases": active,
            "leaseHistoryCount": len(state["leases"]),
            "activeResourceCount": len(
                [item for item in state.get("resources", []) if item.get("status") == "active"]
            ),
            "resourceHistoryCount": len(state.get("resources", [])),
        }
        return payload, changed

    return run_locked(resolved.state_file, _view)


def acquire_lease(
    lane: Lane,
    *,
    paths: WavePaths | None = None,
    agent_id: str | None = None,
    ttl_sec: int = DEFAULT_LEASE_TTL_SEC,
    runtime_id: str | None = None,
    namespace: str = "",
) -> LeaseRecord:
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()
    current_runtime = (runtime_id or probe_runtime_id()).strip()
    ns = namespace.strip()

    def _edit(state: OrchestratorState) -> tuple[LeaseRecord, bool]:
        reaper(state)
        wave = state["wave"]
        if wave is None or wave["status"] != "open":
            raise RuntimeError("LEASE_DENIED: no open wave")
        if current_runtime != wave["runtimeId"]:
            raise RuntimeError(
                f"LEASE_DENIED: RUNTIME_DRIFT expected={wave['runtimeId']} current={current_runtime}"
            )
        active = active_leases(state)
        conflict = lane_conflict_reason(lane, active, namespace=ns)
        if conflict:
            raise RuntimeError(conflict)
        now = _utc_now()
        lease: LeaseRecord = {
            "leaseId": str(uuid.uuid4()),
            "waveId": wave["waveId"],
            "agentId": holder,
            "lane": lane,
            "runtimeId": wave["runtimeId"],
            "createdAt": _iso(now),
            "expiresAt": _iso(now + timedelta(seconds=max(ttl_sec, 60))),
            "lastHeartbeatAt": _iso(now),
            "status": "active",
        }
        if ns:
            lease["namespace"] = ns
        state["leases"].append(lease)
        return lease, True

    return run_locked(resolved.state_file, _edit)


def release_lease(
    lease_id: str,
    *,
    paths: WavePaths | None = None,
    agent_id: str | None = None,
    skip_cleanup: bool = False,
) -> LeaseRecord:
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()

    def _edit(state: OrchestratorState) -> tuple[LeaseRecord, bool]:
        reaper(state)
        for lease in state["leases"]:
            if lease["leaseId"] != lease_id:
                continue
            if lease["status"] != "active":
                raise RuntimeError(f"LEASE_NOT_ACTIVE: {lease_id}")
            if lease["agentId"] != holder:
                raise RuntimeError(f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}")
            lease["status"] = "released"
            cleanup_lease_browser(lease)
            return lease, True
        raise RuntimeError(f"LEASE_NOT_FOUND: {lease_id}")

    lease = run_locked(resolved.state_file, _edit)
    if not skip_cleanup:
        cleanup_lease_resources(lease_id, paths=resolved)
    return lease


def bind_browser_lease(
    lease_id: str,
    *,
    page_id: str,
    context_id: str = "",
    paths: WavePaths | None = None,
    agent_id: str | None = None,
) -> LeaseRecord:
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()

    def _edit(state: OrchestratorState) -> tuple[LeaseRecord, bool]:
        lease = _find_active_lease(state, lease_id)
        if lease["agentId"] != holder:
            raise RuntimeError(f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}")
        return bind_browser(lease, page_id=page_id, context_id=context_id), True

    return run_locked(resolved.state_file, _edit)


def unbind_browser_lease(
    lease_id: str,
    *,
    paths: WavePaths | None = None,
    agent_id: str | None = None,
) -> LeaseRecord:
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()

    def _edit(state: OrchestratorState) -> tuple[LeaseRecord, bool]:
        lease = _find_active_lease(state, lease_id)
        if lease["agentId"] != holder:
            raise RuntimeError(f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}")
        return unbind_browser(lease), True

    return run_locked(resolved.state_file, _edit)


def heartbeat_lease(
    lease_id: str,
    *,
    paths: WavePaths | None = None,
    agent_id: str | None = None,
    extend_sec: int = DEFAULT_HEARTBEAT_EXTEND_SEC,
) -> LeaseRecord:
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()

    def _edit(state: OrchestratorState) -> tuple[LeaseRecord, bool]:
        reaper(state)
        for lease in state["leases"]:
            if lease["leaseId"] != lease_id:
                continue
            if lease["status"] != "active":
                raise RuntimeError(f"LEASE_NOT_ACTIVE: {lease_id}")
            if lease["agentId"] != holder:
                raise RuntimeError(f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}")
            now = _utc_now()
            lease["lastHeartbeatAt"] = _iso(now)
            lease["expiresAt"] = _iso(now + timedelta(seconds=max(extend_sec, 60)))
            return lease, True
        raise RuntimeError(f"LEASE_NOT_FOUND: {lease_id}")

    return run_locked(resolved.state_file, _edit)


def check_stack_write_gate(*, paths: WavePaths | None = None) -> GateResult:
    resolved = paths or resolve_wave_paths()

    def _view(state: OrchestratorState) -> tuple[GateResult, bool]:
        changed = reaper(state)
        blockers: list[GateBlocker] = []
        for lease in active_leases(state):
            blockers.append(
                {
                    "leaseId": lease["leaseId"],
                    "agentId": lease["agentId"],
                    "lane": lease["lane"],
                }
            )
        return {"allowed": len(blockers) == 0, "blockers": blockers}, changed

    return run_locked(resolved.state_file, _view)
