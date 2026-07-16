"""Resource ledger for wave test namespaces.

[INPUT]
- wave_orchestrator.store::run_locked (POS: flock-protected JSON state I/O)
- wave_orchestrator.resource_cleanup::cleanup_resource_ref (POS: server HTTP cleanup)

[OUTPUT]
- register_resource() / list_resources() / cleanup_lease_resources()
- cleanup_namespace_resources() — purge by namespace

[POS]
Dev test resource ownership ledger. Ties business refs to RESOURCE_WRITE or
GLOBAL_WRITE leases while preserving namespace ownership and cleanup.
"""

from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import TypedDict

from wave_orchestrator.paths import WavePaths, resolve_wave_paths
from wave_orchestrator.resource_cleanup import CleanupAttempt, cleanup_resource_ref
from wave_orchestrator.store import run_locked
from wave_orchestrator.types import (
    LeaseRecord,
    OrchestratorState,
    ResourceKind,
    ResourceRecord,
    VALID_RESOURCE_KINDS,
)


class CleanupSummary(TypedDict):
    leaseId: str
    cleaned: int
    failed: int
    attempts: list[CleanupAttempt]


def _utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(dt: datetime) -> str:
    return dt.replace(microsecond=0).isoformat()


def _active_resources(
    state: OrchestratorState, *, lease_id: str = "", namespace: str = ""
) -> list[ResourceRecord]:
    items: list[ResourceRecord] = []
    for resource in state.get("resources", []):
        if resource.get("status") != "active":
            continue
        if lease_id and resource.get("leaseId") != lease_id:
            continue
        if namespace and resource.get("namespace") != namespace:
            continue
        items.append(resource)
    return items


def _cleanup_candidates(
    state: OrchestratorState, *, lease_id: str = "", namespace: str = ""
) -> list[ResourceRecord]:
    return [
        item
        for item in state.get("resources", [])
        if item.get("status") in {"active", "failed"}
        and (not lease_id or item.get("leaseId") == lease_id)
        and (not namespace or item.get("namespace") == namespace)
    ]


def register_resource(
    lease_id: str,
    *,
    kind: ResourceKind,
    ref: str,
    namespace: str = "",
    agent_id: str = "",
    paths: WavePaths | None = None,
) -> ResourceRecord:
    if kind not in VALID_RESOURCE_KINDS:
        raise RuntimeError(f"LEDGER_DENIED: invalid kind {kind}")
    resource_ref = ref.strip()
    if not resource_ref:
        raise RuntimeError("LEDGER_DENIED: empty resource ref")
    resolved = paths or resolve_wave_paths()

    def _edit(state: OrchestratorState) -> tuple[ResourceRecord, bool]:
        lease = _find_active_lease(state, lease_id)
        ns = (namespace or str(lease.get("namespace", ""))).strip()
        if not ns:
            raise RuntimeError(
                "LEDGER_DENIED: namespace required for resource registration"
            )
        if lease["lane"] not in {"RESOURCE_WRITE", "GLOBAL_WRITE", "LIVE_AGENT"}:
            raise RuntimeError(
                f"LEDGER_DENIED: lease {lease_id} cannot own resources from lane {lease['lane']}"
            )
        for item in _active_resources(state):
            if item["kind"] == kind and item["ref"] == resource_ref:
                raise RuntimeError(
                    f"LEDGER_DENIED: {kind}/{resource_ref} already registered"
                )
        now = _iso(_utc_now())
        record: ResourceRecord = {
            "resourceId": str(uuid.uuid4()),
            "leaseId": lease_id,
            "namespace": ns,
            "agentId": agent_id or lease["agentId"],
            "kind": kind,
            "ref": resource_ref,
            "createdAt": now,
            "status": "active",
        }
        state.setdefault("resources", []).append(record)
        return record, True

    return run_locked(resolved.state_file, _edit)


def list_resources(
    *,
    lease_id: str = "",
    namespace: str = "",
    paths: WavePaths | None = None,
) -> list[ResourceRecord]:
    resolved = paths or resolve_wave_paths()

    def _view(state: OrchestratorState) -> tuple[list[ResourceRecord], bool]:
        return _active_resources(state, lease_id=lease_id, namespace=namespace), False

    return run_locked(resolved.state_file, _view)


def _find_active_lease(state: OrchestratorState, lease_id: str) -> LeaseRecord:
    for lease in state["leases"]:
        if lease["leaseId"] == lease_id and lease["status"] == "active":
            return lease
    raise RuntimeError(f"LEDGER_DENIED: active lease not found: {lease_id}")


def _apply_cleanup_results(
    state: OrchestratorState,
    resources: list[ResourceRecord],
    attempts: list[CleanupAttempt],
) -> CleanupSummary:
    attempt_map = {(item["kind"], item["ref"]): item for item in attempts}
    cleaned = 0
    failed = 0
    now = _iso(_utc_now())
    for resource in resources:
        key = (resource["kind"], resource["ref"])
        attempt = attempt_map.get(key)
        if attempt is None:
            continue
        if attempt["ok"]:
            resource["status"] = "cleaned"
            resource["cleanedAt"] = now
            cleaned += 1
        else:
            resource["status"] = "failed"
            resource["lastError"] = attempt["detail"]
            failed += 1
    lease_id = resources[0]["leaseId"] if resources else ""
    return {
        "leaseId": lease_id,
        "cleaned": cleaned,
        "failed": failed,
        "attempts": attempts,
    }


def cleanup_lease_resources(
    lease_id: str,
    *,
    paths: WavePaths | None = None,
) -> CleanupSummary:
    resolved = paths or resolve_wave_paths()

    def _snapshot(state: OrchestratorState) -> tuple[list[ResourceRecord], bool]:
        return [dict(item) for item in _cleanup_candidates(state, lease_id=lease_id)], False

    targets = run_locked(resolved.state_file, _snapshot)
    if not targets:
        return {"leaseId": lease_id, "cleaned": 0, "failed": 0, "attempts": []}

    attempts = [cleanup_resource_ref(item["kind"], item["ref"]) for item in targets]

    def _commit(state: OrchestratorState) -> tuple[CleanupSummary, bool]:
        keys = {(item["kind"], item["ref"]) for item in targets}
        current = [
            item
            for item in state.get("resources", [])
            if item.get("leaseId") == lease_id
            and item.get("status") in {"active", "failed"}
            and (item.get("kind"), item.get("ref")) in keys
        ]
        if not current:
            return {
                "leaseId": lease_id,
                "cleaned": 0,
                "failed": 0,
                "attempts": attempts,
            }, False
        return _apply_cleanup_results(state, current, attempts), True

    return run_locked(resolved.state_file, _commit)


def cleanup_namespace_resources(
    namespace: str,
    *,
    paths: WavePaths | None = None,
) -> CleanupSummary:
    resolved = paths or resolve_wave_paths()
    ns = namespace.strip()
    if not ns:
        raise RuntimeError("LEDGER_DENIED: empty namespace")

    def _snapshot(state: OrchestratorState) -> tuple[list[ResourceRecord], bool]:
        return [dict(item) for item in _cleanup_candidates(state, namespace=ns)], False

    targets = run_locked(resolved.state_file, _snapshot)
    if not targets:
        return {"leaseId": "", "cleaned": 0, "failed": 0, "attempts": []}

    attempts = [cleanup_resource_ref(item["kind"], item["ref"]) for item in targets]
    keys = {(item["kind"], item["ref"]) for item in targets}

    def _commit(state: OrchestratorState) -> tuple[CleanupSummary, bool]:
        current = [
            item
            for item in state.get("resources", [])
            if item.get("namespace") == ns
            and item.get("status") in {"active", "failed"}
            and (item.get("kind"), item.get("ref")) in keys
        ]
        if not current:
            return {
                "leaseId": "",
                "cleaned": 0,
                "failed": 0,
                "attempts": attempts,
            }, False
        return _apply_cleanup_results(state, current, attempts), True

    return run_locked(resolved.state_file, _commit)


def cleanup_expired_lease_resources(state: OrchestratorState) -> bool:
    changed = False
    expired_ids = {
        lease["leaseId"]
        for lease in state["leases"]
        if lease["status"] in {"expired", "released"}
    }
    if not expired_ids:
        return False
    for lease_id in expired_ids:
        targets = [
            resource
            for resource in state.get("resources", [])
            if resource.get("leaseId") == lease_id
            and resource.get("status") in {"active", "failed"}
        ]
        if not targets:
            continue
        attempts = [cleanup_resource_ref(item["kind"], item["ref"]) for item in targets]
        _apply_cleanup_results(state, targets, attempts)
        changed = True
    return changed
