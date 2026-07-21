"""Typed lane conflict rules for wave orchestrator.

[INPUT]
- wave_orchestrator.types::Lane / LeaseRecord (POS: wave/lease schema)

[OUTPUT]
- lane_conflict_reason() — why acquire is denied
- live_agent_max_concurrent() — env-tunable cap

[POS]
Lane scheduling policy. Encodes READ/RESOURCE_WRITE/GLOBAL_WRITE/LIVE_AGENT/STACK_WRITE matrix.
"""

from __future__ import annotations

import os

from wave_orchestrator.types import Lane, LeaseRecord

ALL_LANES: frozenset[Lane] = frozenset(
    {"READ", "RESOURCE_WRITE", "GLOBAL_WRITE", "LIVE_AGENT", "STACK_WRITE"}
)


def live_agent_max_concurrent() -> int:
    raw = os.environ.get("MYRM_LIVE_AGENT_MAX_CONCURRENT", "4").strip()
    try:
        value = int(raw)
    except ValueError:
        return 1
    return max(value, 1)


def lane_conflict_reason(
    lane: Lane,
    active: list[LeaseRecord],
    *,
    namespace: str = "",
) -> str | None:
    ns = namespace.strip()
    if lane not in ALL_LANES:
        return f"LEASE_DENIED: invalid lane {lane}"

    if lane == "STACK_WRITE":
        if active:
            owners = ", ".join(f"{item['agentId']}/{item['lane']}" for item in active)
            return f"LEASE_DENIED: STACK_WRITE blocked by active leases: {owners}"
        return None

    stack_holders = [item for item in active if item["lane"] == "STACK_WRITE"]
    if stack_holders:
        return "LEASE_DENIED: STACK_WRITE lease holds the stack"

    if lane == "READ":
        global_holders = [item for item in active if item["lane"] == "GLOBAL_WRITE"]
        if global_holders:
            return "LEASE_DENIED: GLOBAL_WRITE lease active"
        return None

    if lane == "GLOBAL_WRITE":
        blockers = [
            item
            for item in active
            if item["lane"] in {"GLOBAL_WRITE", "LIVE_AGENT", "RESOURCE_WRITE", "READ"}
        ]
        if blockers:
            owners = ", ".join(f"{item['agentId']}/{item['lane']}" for item in blockers)
            return f"LEASE_DENIED: GLOBAL_WRITE blocked by: {owners}"
        return None

    if lane == "LIVE_AGENT":
        global_holders = [item for item in active if item["lane"] == "GLOBAL_WRITE"]
        if global_holders:
            return "LEASE_DENIED: GLOBAL_WRITE lease active"
        live_count = sum(1 for item in active if item["lane"] == "LIVE_AGENT")
        cap = live_agent_max_concurrent()
        if live_count >= cap:
            return f"LEASE_DENIED: LIVE_AGENT cap {cap} reached"
        return None

    if lane == "RESOURCE_WRITE":
        if not ns:
            return "LEASE_DENIED: RESOURCE_WRITE requires --namespace"
        global_holders = [item for item in active if item["lane"] == "GLOBAL_WRITE"]
        if global_holders:
            return "LEASE_DENIED: GLOBAL_WRITE lease active"
        for item in active:
            if item["lane"] != "RESOURCE_WRITE":
                continue
            item_ns = str(item.get("namespace", "")).strip()
            if item_ns == ns:
                return f"LEASE_DENIED: RESOURCE_WRITE namespace {ns} already held by {item['agentId']}"
        return None

    return f"LEASE_DENIED: unsupported lane {lane}"
