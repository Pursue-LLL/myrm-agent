"""Browser bindings and external cleanup for owned Wave leases.

[INPUT]
- flock-protected Wave state
- exact lease page/context and resource ownership

[OUTPUT]
- browser bind/unbind operations and lock-external cleanup

[POS]
Lease side effects. State is committed under lock; CDP/HTTP cleanup runs afterward.
"""

from __future__ import annotations

from wave_orchestrator.browser_lifecycle import (
    bind_browser,
    cleanup_lease_browser,
    unbind_browser,
)
from wave_orchestrator.lease_state import (
    active_leases,
    default_agent_id,
    find_active_lease,
)
from wave_orchestrator.paths import WavePaths, resolve_wave_paths
from wave_orchestrator.resource_ledger import cleanup_lease_resources
from wave_orchestrator.store import run_locked
from wave_orchestrator.types import LeaseRecord, OrchestratorState


def clear_browser_binding(
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


def cleanup_released_lease(
    lease: LeaseRecord,
    *,
    paths: WavePaths,
    skip_resource_cleanup: bool = False,
    strict: bool = True,
) -> None:
    failures: list[str] = []
    page_id = str(lease.get("pageId", "")).strip()
    if page_id:
        attempts = cleanup_lease_browser(lease)
        if attempts and attempts[0]["ok"]:
            clear_browser_binding(lease["leaseId"], page_id, paths=paths)
        elif attempts:
            failures.append(f"browser: {attempts[0]['detail']}")
    if not skip_resource_cleanup:
        summary = cleanup_lease_resources(lease["leaseId"], paths=paths)
        if summary["failed"]:
            details = "; ".join(
                attempt["detail"] for attempt in summary["attempts"] if not attempt["ok"]
            )
            failures.append(f"resources({summary['failed']}): {details}")
    if strict and failures:
        raise RuntimeError(
            f"LEASE_CLEANUP_FAILED: lease={lease['leaseId']}: " + "; ".join(failures)
        )


def cleanup_expired_leases(*, paths: WavePaths) -> None:
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
        cleanup_released_lease(lease, paths=paths, strict=False)


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

    def _edit(
        state: OrchestratorState,
    ) -> tuple[tuple[LeaseRecord, list[LeaseRecord]], bool]:
        lease = find_active_lease(state, lease_id)
        if lease["agentId"] != holder:
            raise RuntimeError(
                f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}"
            )
        requested_context = context_id.strip()
        replaced: list[LeaseRecord] = []
        if requested_context:
            for other in list(active_leases(state)):
                if (
                    other["leaseId"] != lease_id
                    and other.get("contextId") == requested_context
                ):
                    if other["agentId"] != holder:
                        raise RuntimeError(
                            f"BROWSER_CONTEXT_CONFLICT: contextId {requested_context} is already bound"
                        )
                    other["status"] = "released"
                    replaced.append(dict(other))
        bound = bind_browser(
            lease,
            page_id=page_id,
            target_id=target_id,
            context_id=context_id,
        )
        return (bound, replaced), True

    bound, replaced = run_locked(resolved.state_file, _edit)
    for stale in replaced:
        cleanup_released_lease(stale, paths=resolved)
    return bound


def unbind_browser_lease(
    lease_id: str,
    *,
    paths: WavePaths | None = None,
    agent_id: str | None = None,
) -> LeaseRecord:
    resolved = paths or resolve_wave_paths()
    holder = agent_id or default_agent_id()

    def _edit(state: OrchestratorState) -> tuple[LeaseRecord, bool]:
        lease = find_active_lease(state, lease_id)
        if lease["agentId"] != holder:
            raise RuntimeError(
                f"LEASE_OWNER_MISMATCH: {lease_id} owner={lease['agentId']}"
            )
        return unbind_browser(lease), True

    return run_locked(resolved.state_file, _edit)
