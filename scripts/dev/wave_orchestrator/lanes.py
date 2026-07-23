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
import sys
from pathlib import Path

_dev_lib = Path(__file__).resolve().parent.parent / "lib"
_dev_lib_str = str(_dev_lib)
if _dev_lib_str not in sys.path:
    sys.path.insert(0, _dev_lib_str)

from dev_gate_contract import (
    LIVE_SHARED_HOT_MAX_CONCURRENT,
    LIVE_SHPOIB_MAX_CONCURRENT,
)
from wave_orchestrator.types import Lane, LeaseRecord

ALL_LANES: frozenset[Lane] = frozenset(
    {"READ", "RESOURCE_WRITE", "GLOBAL_WRITE", "LIVE_AGENT", "STACK_WRITE"}
)

LIVE_E2E_SHPOIB_NAMESPACE = "e2e:shpoib"
LIVE_E2E_SHARED_HOT_NAMESPACE = "e2e:shared_hot"


def live_agent_max_concurrent() -> int:
    raw = os.environ.get("MYRM_LIVE_AGENT_MAX_CONCURRENT", "4").strip()
    try:
        value = int(raw)
    except ValueError:
        return 1
    return max(value, 1)


def _live_agent_bucket(lease: LeaseRecord) -> str:
    ns = str(lease.get("namespace", "")).strip()
    if ns == LIVE_E2E_SHARED_HOT_NAMESPACE:
        return "shared_hot"
    return "shpoib"


def _live_agent_bucket_for_namespace(namespace: str) -> str:
    ns = namespace.strip()
    if ns == LIVE_E2E_SHARED_HOT_NAMESPACE:
        return "shared_hot"
    return "shpoib"


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
        live_leases = [item for item in active if item["lane"] == "LIVE_AGENT"]
        acquiring_bucket = _live_agent_bucket_for_namespace(ns)
        if acquiring_bucket == "shared_hot":
            shared_hot_count = sum(
                1 for item in live_leases if _live_agent_bucket(item) == "shared_hot"
            )
            if shared_hot_count >= LIVE_SHARED_HOT_MAX_CONCURRENT:
                return (
                    "LEASE_DENIED: LIVE_AGENT shared_hot cap "
                    f"{LIVE_SHARED_HOT_MAX_CONCURRENT} reached"
                )
            return None
        shpoib_count = sum(
            1 for item in live_leases if _live_agent_bucket(item) == "shpoib"
        )
        cap = live_agent_max_concurrent()
        shpoib_cap = min(LIVE_SHPOIB_MAX_CONCURRENT, cap)
        if shpoib_count >= shpoib_cap:
            return f"LEASE_DENIED: LIVE_AGENT SHPOIB cap {shpoib_cap} reached"
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
