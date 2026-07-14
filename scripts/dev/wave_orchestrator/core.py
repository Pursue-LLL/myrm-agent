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

from wave_orchestrator.browser_lifecycle import (
    bind_browser,
    cleanup_expired_browser,
    cleanup_lease_browser,
    unbind_browser,
)
from wave_orchestrator.lanes import lane_conflict_reason
from wave_orchestrator.paths import WavePaths, resolve_wave_paths
from wave_orchestrator.resource_ledger import (
    cleanup_lease_resources,
    cleanup_expired_lease_resources,
)
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


def reaper(
    state: OrchestratorState,
    now: datetime | None = None,
    *,
    cleanup: bool = True,
) -> bool:
    moment = now or _utc_now()
    changed = False
    for lease in state["leases"]:
        if lease["status"] != "active":
            continue
        if _parse_iso(lease["expiresAt"]) <= moment:
            lease["status"] = "expired"
            changed = True
    if cleanup:
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
    return True


def _close_wave_after_last_expired_lease(state: OrchestratorState) -> bool:
    wave = state["wave"]
    if wave is None or wave["status"] != "open":
        return False
    wave_leases = [
        lease for lease in state["leases"] if lease["waveId"] == wave["waveId"]
    ]
    if not wave_leases or any(lease["status"] == "active" for lease in wave_leases):
        return False
    if not any(lease["status"] == "expired" for lease in wave_leases):
        return False
    wave["status"] = "closed"
    wave["closedAt"] = _iso(_utc_now())
    return True


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


def _cleanup_expired_leases(*, paths: WavePaths) -> None:
    def _snapshot(state: OrchestratorState) -> tuple[list[LeaseRecord], bool]:
        return [
            dict(lease)
            for lease in state["leases"]
            if lease["status"] in {"expired", "released"}
            and (
                lease.get("pageId")
                or any(
                    item.get("leaseId") == lease["leaseId"]
                    and item.get("status") in {"active", "failed"}
                    for item in state.get("resources", [])
                )
            )
        ], False

    for lease in run_locked(paths.state_file, _snapshot):
        _cleanup_released_lease(lease, paths=paths)


def reap(*, paths: WavePaths | None = None) -> dict[str, object]:
    """Run TTL and runtime drift reaping for the supervisor watchdog."""
    resolved = paths or resolve_wave_paths()
    current_runtime = probe_runtime_id()

    def _edit(state: OrchestratorState) -> tuple[dict[str, object], bool]:
        changed = reaper(state, cleanup=False)
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


def active_leases(state: OrchestratorState) -> list[LeaseRecord]:
    return [lease for lease in state["leases"] if lease["status"] == "active"]


def _clear_browser_binding(
    lease_id: str,
    page_id: str,
    *,
    paths: WavePaths,
) -> None:
    def _edit(state: OrchestratorState) -> tuple[None, bool]:
        for lease in state["leases"]:
            if (
                lease["leaseId"] == lease_id
                and lease["status"] in {"released", "expired"}
                and lease.get("pageId") == page_id
            ):
                unbind_browser(lease)
                return None, True
        return None, False

    run_locked(paths.state_file, _edit)


def _cleanup_released_lease(
    lease: LeaseRecord,
    *,
    paths: WavePaths,
    skip_resource_cleanup: bool = False,
) -> None:
    page_id = str(lease.get("pageId", "")).strip()
    if page_id:
        attempts = cleanup_lease_browser(lease)
        if attempts and attempts[0]["ok"]:
            _clear_browser_binding(lease["leaseId"], page_id, paths=paths)
    if not skip_resource_cleanup:
        cleanup_lease_resources(lease["leaseId"], paths=paths)


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
) -> LeaseRecord:
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()
    current_runtime = (runtime_id or probe_runtime_id()).strip()
    ns = namespace.strip()

    def _edit(state: OrchestratorState) -> tuple[LeaseRecord, bool]:
        reaper(state, cleanup=False)
        wave = state["wave"]
        if wave is None or wave["status"] != "open":
            raise RuntimeError("LEASE_DENIED: no open wave")
        if current_runtime != wave["runtimeId"]:
            raise RuntimeError(
                f"LEASE_DENIED: RUNTIME_DRIFT expected={wave['runtimeId']} current={current_runtime}"
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
            if lease["status"] != "active":
                raise RuntimeError(f"LEASE_NOT_ACTIVE: {lease_id}")
            if lease["agentId"] != holder:
                raise RuntimeError(
                    f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}"
                )
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
    """Release one lease and atomically close its wave when it is the last holder."""
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()

    def _edit(state: OrchestratorState) -> tuple[LeaseReleaseResult, bool]:
        reaper(state, cleanup=False)
        released: LeaseRecord | None = None
        for lease in state["leases"]:
            if lease["leaseId"] != lease_id:
                continue
            if lease["status"] != "active":
                raise RuntimeError(f"LEASE_NOT_ACTIVE: {lease_id}")
            if lease["agentId"] != holder:
                raise RuntimeError(
                    f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}"
                )
            lease["status"] = "released"
            released = dict(lease)
            break
        if released is None:
            raise RuntimeError(f"LEASE_NOT_FOUND: {lease_id}")

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
        return {
            "lease": released,
            "wave": closed,
            "waveClosed": closed is not None,
        }, True

    result = run_locked(resolved.state_file, _edit)
    _cleanup_released_lease(result["lease"], paths=resolved)
    if result["waveClosed"]:
        clear_stack_pin(paths=resolved)
    return result


def bind_browser_lease(
    lease_id: str,
    *,
    page_id: str,
    target_id: str,
    context_id: str = "",
    paths: WavePaths | None = None,
    agent_id: str | None = None,
) -> LeaseRecord:
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()

    def _edit(state: OrchestratorState) -> tuple[LeaseRecord, bool]:
        lease = _find_active_lease(state, lease_id)
        if lease["agentId"] != holder:
            raise RuntimeError(
                f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}"
            )
        requested_context = context_id.strip()
        if requested_context:
            for other in active_leases(state):
                if (
                    other["leaseId"] != lease_id
                    and other.get("contextId") == requested_context
                ):
                    raise RuntimeError(
                        f"BROWSER_CONTEXT_CONFLICT: contextId {requested_context} is already bound"
                    )
        return bind_browser(
            lease,
            page_id=page_id,
            target_id=target_id,
            context_id=context_id,
        ), True

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
            raise RuntimeError(
                f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}"
            )
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
