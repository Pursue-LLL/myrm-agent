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

import uuid
from datetime import timedelta
from typing import TypedDict

from wave_orchestrator.lease_cleanup import (
    cleanup_expired_leases as _cleanup_expired_leases,
    cleanup_released_lease as _cleanup_released_lease,
)
from wave_orchestrator.lease_state import (
    active_leases,
    close_wave_after_last_expired_lease as _close_wave_after_last_expired_lease,
    default_agent_id,
    find_active_lease as _find_active_lease,
    iso_timestamp as _iso,
    reap_abandoned_leases,
    reap_expired_leases as reaper,
    reap_runtime_drift,
    utc_now as _utc_now,
)
from wave_orchestrator.lanes import lane_conflict_reason
from wave_orchestrator.paths import WavePaths, resolve_wave_paths
from wave_orchestrator.stack_pin import clear_stack_pin, read_stack_pin, write_stack_pin
from wave_orchestrator.store import run_locked
from wave_orchestrator.types import Lane, LeaseRecord, OrchestratorState, WaveRecord


class GateBlocker(TypedDict):
    leaseId: str
    agentId: str
    lane: Lane


class StackPinBlocker(TypedDict):
    waveId: str
    runtimeId: str
    openedBy: str


class GateResult(TypedDict):
    allowed: bool
    blockers: list[GateBlocker]
    stackPin: StackPinBlocker | None


class LeaseReleaseResult(TypedDict):
    lease: LeaseRecord
    wave: WaveRecord | None
    waveClosed: bool


DEFAULT_LEASE_TTL_SEC = 3600
DEFAULT_HEARTBEAT_EXTEND_SEC = 3600


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


def _stack_pin_blocker(state: OrchestratorState) -> StackPinBlocker | None:
    wave = state["wave"]
    if wave is None or wave["status"] != "open":
        return None
    if any(lease["lane"] == "STACK_WRITE" for lease in active_leases(state)):
        return None
    return {
        "waveId": wave["waveId"],
        "runtimeId": wave["runtimeId"],
        "openedBy": wave["openedBy"],
    }


def reap(*, paths: WavePaths | None = None) -> dict[str, object]:
    """Run TTL and runtime drift reaping for the supervisor watchdog."""
    resolved = paths or resolve_wave_paths()
    current_runtime = probe_runtime_id()

    def _edit(state: OrchestratorState) -> tuple[dict[str, object], bool]:
        changed = reap_abandoned_leases(state)
        if reaper(state, cleanup=False):
            changed = True
        if reap_runtime_drift(state, current_runtime):
            changed = True
        elif _close_wave_after_last_expired_lease(state):
            changed = True
        return {
            "wave": state["wave"],
            "runtimeId": current_runtime,
            "activeLeaseCount": len(active_leases(state)),
        }, changed

    result = run_locked(resolved.state_file, _edit)
    wave = result.get("wave")
    if isinstance(wave, dict) and wave.get("status") in {"closed", "drifted"}:
        clear_stack_pin(paths=resolved)
    _cleanup_expired_leases(paths=resolved)
    return result


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
        reaper(state, cleanup=False)
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

    wave = run_locked(resolved.state_file, _edit)
    write_stack_pin(wave, paths=resolved, pinned_at=_iso(_utc_now()))
    return wave


def close_wave(
    *,
    paths: WavePaths | None = None,
    force: bool = False,
    agent_id: str | None = None,
) -> WaveRecord | None:
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()
    released_leases: list[LeaseRecord] = []

    def _edit(state: OrchestratorState) -> tuple[WaveRecord | None, bool]:
        reaper(state, cleanup=False)
        wave = state["wave"]
        if wave is None or wave["status"] not in {"open", "drifted"}:
            raise RuntimeError("WAVE_NOT_OPEN")
        blockers = active_leases(state) if wave["status"] == "open" else []
        if blockers and not force:
            owners = ", ".join(
                f"{item['leaseId']}({item['agentId']}/{item['lane']})"
                for item in blockers
            )
            raise RuntimeError(f"WAVE_CLOSE_BLOCKED: active leases: {owners}")
        foreign_owners = sorted(
            {item["agentId"] for item in blockers if item["agentId"] != holder}
        )
        if force and foreign_owners:
            raise RuntimeError(
                "WAVE_FORCE_OWNER_MISMATCH: active leases owned by "
                + ", ".join(foreign_owners)
            )
        now = _utc_now()
        for lease in blockers:
            lease["status"] = "released"
            released_leases.append(dict(lease))
        closed: WaveRecord = {**wave, "status": "closed", "closedAt": _iso(now)}
        state["wave"] = closed
        return closed, True

    closed = run_locked(resolved.state_file, _edit)
    clear_stack_pin(paths=resolved)
    if force:
        for lease in released_leases:
            _cleanup_released_lease(lease, paths=resolved)
    return closed


def wave_status(*, paths: WavePaths | None = None) -> dict[str, object]:
    resolved = paths or resolve_wave_paths()

    def _view(state: OrchestratorState) -> tuple[dict[str, object], bool]:
        changed = reaper(state, cleanup=False)
        active = active_leases(state)
        payload = {
            "wave": state["wave"],
            "activeLeaseCount": len(active),
            "activeLeases": active,
            "leaseHistoryCount": len(state["leases"]),
            "activeResourceCount": len(
                [
                    item
                    for item in state.get("resources", [])
                    if item.get("status") == "active"
                ]
            ),
            "resourceHistoryCount": len(state.get("resources", [])),
            "stackPin": read_stack_pin(paths=resolved),
        }
        return payload, changed

    result = run_locked(resolved.state_file, _view)
    _cleanup_expired_leases(paths=resolved)
    return result


def acquire_lease(
    lane: Lane,
    *,
    paths: WavePaths | None = None,
    agent_id: str | None = None,
    ttl_sec: int = DEFAULT_LEASE_TTL_SEC,
    runtime_id: str | None = None,
    namespace: str = "",
    parent_lease_id: str = "",
) -> LeaseRecord:
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()
    current_runtime = (runtime_id or probe_runtime_id()).strip()
    ns = namespace.strip()
    parent_id = parent_lease_id.strip()

    def _edit(state: OrchestratorState) -> tuple[LeaseRecord, bool]:
        reaper(state, cleanup=False)
        wave = state["wave"]
        if wave is None or wave["status"] != "open":
            raise RuntimeError("LEASE_DENIED: no open wave")
        if current_runtime != wave["runtimeId"]:
            raise RuntimeError(
                f"LEASE_DENIED: RUNTIME_DRIFT expected={wave['runtimeId']} current={current_runtime}"
            )
        if parent_id:
            parent = _find_active_lease(state, parent_id)
            if parent["agentId"] != holder:
                raise RuntimeError(
                    f"PARENT_LEASE_OWNER_MISMATCH: {parent_id} owner={parent['agentId']}"
                )
            if parent["waveId"] != wave["waveId"]:
                raise RuntimeError(
                    f"PARENT_LEASE_WAVE_MISMATCH: {parent_id} wave={parent['waveId']}"
                )
        active = active_leases(state)
        foreign_leases = [lease for lease in active if lease["agentId"] != holder]
        conflict = lane_conflict_reason(lane, foreign_leases, namespace=ns)
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
        if parent_id:
            lease["parentLeaseId"] = parent_id
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
        reaper(state, cleanup=False)
        for lease in state["leases"]:
            if lease["leaseId"] != lease_id:
                continue
            if lease["agentId"] != holder:
                raise RuntimeError(
                    f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}"
                )
            if lease["status"] != "active":
                return dict(lease), False
            lease["status"] = "released"
            return dict(lease), True
        raise RuntimeError(f"LEASE_NOT_FOUND: {lease_id}")

    lease = run_locked(resolved.state_file, _edit)
    _cleanup_released_lease(lease, paths=resolved, skip_resource_cleanup=skip_cleanup)
    return lease


def release_lease_and_close_wave_if_idle(
    lease_id: str,
    *,
    paths: WavePaths | None = None,
    agent_id: str | None = None,
) -> LeaseReleaseResult:
    """Release a lease, its explicit children, and close the wave when idle."""
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()
    dependent_leases: list[LeaseRecord] = []

    def _edit(state: OrchestratorState) -> tuple[LeaseReleaseResult, bool]:
        reaper(state, cleanup=False)
        released: LeaseRecord | None = None
        changed = False
        for lease in state["leases"]:
            if lease["leaseId"] != lease_id:
                continue
            if lease["agentId"] != holder:
                raise RuntimeError(
                    f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}"
                )
            if lease["status"] == "active":
                lease["status"] = "released"
                changed = True
            released = dict(lease)
            break
        if released is None:
            raise RuntimeError(f"LEASE_NOT_FOUND: {lease_id}")

        parent_ids = {released["leaseId"]}
        visited: set[str] = set()
        while parent_ids:
            child_ids: set[str] = set()
            for lease in state["leases"]:
                if (
                    lease["leaseId"] in visited
                    or lease.get("parentLeaseId") not in parent_ids
                ):
                    continue
                if lease["agentId"] != holder or lease["waveId"] != released["waveId"]:
                    raise RuntimeError(
                        "CHILD_LEASE_OWNERSHIP_MISMATCH: "
                        f"{lease['leaseId']} parent={lease.get('parentLeaseId')}"
                    )
                if lease["status"] == "active":
                    lease["status"] = "released"
                    changed = True
                dependent_leases.append(dict(lease))
                visited.add(lease["leaseId"])
                child_ids.add(lease["leaseId"])
            parent_ids = child_ids

        wave = state["wave"]
        closed: WaveRecord | None = None
        if (
            wave is not None
            and wave["status"] == "open"
            and wave["waveId"] == released["waveId"]
            and not active_leases(state)
        ):
            closed = {**wave, "status": "closed", "closedAt": _iso(_utc_now())}
            state["wave"] = closed
            changed = True
        return {
            "lease": released,
            "wave": closed,
            "waveClosed": closed is not None,
        }, changed

    result = run_locked(resolved.state_file, _edit)
    _cleanup_released_lease(result["lease"], paths=resolved)
    for lease in dependent_leases:
        _cleanup_released_lease(lease, paths=resolved)
    if result["waveClosed"]:
        clear_stack_pin(paths=resolved)
    return result


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
        reaper(state, cleanup=False)
        for lease in state["leases"]:
            if lease["leaseId"] != lease_id:
                continue
            if lease["status"] != "active":
                raise RuntimeError(f"LEASE_NOT_ACTIVE: {lease_id}")
            if lease["agentId"] != holder:
                raise RuntimeError(
                    f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}"
                )
            now = _utc_now()
            lease["lastHeartbeatAt"] = _iso(now)
            lease["expiresAt"] = _iso(now + timedelta(seconds=max(extend_sec, 60)))
            return lease, True
        raise RuntimeError(f"LEASE_NOT_FOUND: {lease_id}")

    result = run_locked(resolved.state_file, _edit)
    _cleanup_expired_leases(paths=resolved)
    return result


def check_stack_write_gate(*, paths: WavePaths | None = None) -> GateResult:
    resolved = paths or resolve_wave_paths()

    def _view(state: OrchestratorState) -> tuple[GateResult, bool]:
        changed = reaper(state, cleanup=False)
        active = active_leases(state)
        stack_write_only = bool(active) and all(
            lease["lane"] == "STACK_WRITE" for lease in active
        )
        blockers: list[GateBlocker] = []
        if active and not stack_write_only:
            for lease in active:
                blockers.append(
                    {
                        "leaseId": lease["leaseId"],
                        "agentId": lease["agentId"],
                        "lane": lease["lane"],
                    }
                )
        stack_pin = None if stack_write_only else _stack_pin_blocker(state)
        allowed = len(blockers) == 0 and stack_pin is None
        return {
            "allowed": allowed,
            "blockers": blockers,
            "stackPin": stack_pin,
        }, changed

    result = run_locked(resolved.state_file, _view)
    _cleanup_expired_leases(paths=resolved)
    return result
