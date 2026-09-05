"""First-party Browser Orchestrator interface (P0-B SSOT).

[INPUT]
mux.upstream_admission (POS: mux cold-attach active operations probe — bridge until full daemon migration)
mux.transport_supervisor (POS: recovery budget)
dev_gate.contract (POS: MUX_COLD_ATTACH_SLOTS constant)

[OUTPUT]
browser_orchestrator_snapshot(): health/credits/in-flight status for e2e-context
browser_operation_credit_slot(): context manager for acquiring an operation credit
wait_for_operation_credit(): block until a credit is available
prune_self_owned_blanks(): cleanup helper delegating to tab hygiene

[POS]
唯一浏览器数据面的 Python 客户端接口。
启用 MYRM_BROWSER_ORCHESTRATOR=1 时直接读取 Browser Orchestrator daemon；
未启用时使用本地 mux 适配器。两条路径都是显式运行模式，业务层不直接依赖任一实现。
"""

from __future__ import annotations

import enum
import logging
import os
import sys
import time
from contextlib import contextmanager
from typing import Generator

_LOGGER = logging.getLogger(__name__)

MAX_OPERATION_CREDITS = 4
OPERATION_QUEUE_SLO_SEC = 20.0
_MEAN_OPERATION_TURNAROUND_SEC = 12.0


def estimate_operation_wait_sec(
    *,
    queued: int,
    effective_credits: int,
) -> float:
    """DRR-inspired wait estimate for queued browser operations (§19.11.3 TAB-7)."""
    if queued <= 0:
        return 0.0
    credits = max(1, effective_credits)
    batches = (queued + credits - 1) // credits
    return min(900.0, float(batches) * _MEAN_OPERATION_TURNAROUND_SEC)


def orchestrator_queue_observability(
    snap: dict[str, object],
) -> dict[str, object]:
    """Operation queue fields for e2e-context / capHeadroom (TAB-7)."""
    queued_raw = snap.get("operation_credits_queued", 0)
    in_flight_raw = snap.get("operation_credits_in_flight", 0)
    effective_raw = snap.get("operation_credits_effective", MAX_OPERATION_CREDITS)
    queued = queued_raw if isinstance(queued_raw, int) else 0
    in_flight = in_flight_raw if isinstance(in_flight_raw, int) else 0
    effective = (
        effective_raw if isinstance(effective_raw, int) else MAX_OPERATION_CREDITS
    )
    estimated = estimate_operation_wait_sec(
        queued=queued,
        effective_credits=effective,
    )
    saturated = queued > 0 or in_flight >= effective
    return {
        "queueDepth": queued,
        "estimatedWaitSec": round(estimated, 1),
        "operationSloSec": OPERATION_QUEUE_SLO_SEC,
        "withinOperationSlo": estimated <= OPERATION_QUEUE_SLO_SEC,
        "operationSaturated": saturated,
        "activeOps": in_flight,
        "effectiveCredits": effective,
    }


class BrowserPlaneHealth(enum.Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


def _mux_scheduler_probe() -> tuple[bool, int, int]:
    """Probe mux daemon via cdmcp-mux-autoconnect status (SSOT).

    Returns (available, scheduler_active, scheduler_queued).
    """
    try:
        from mux.load import read_mux_status  # noqa: PLC0415
    except ImportError:
        return False, 0, 0
    status = read_mux_status()
    if not isinstance(status, dict) or status.get("ok") is not True:
        return False, 0, 0
    scheduler = status.get("requestScheduler")
    if isinstance(scheduler, dict):
        active_raw = scheduler.get("active", 0)
        queued_raw = scheduler.get("queued", 0)
        active = active_raw if isinstance(active_raw, int) else 0
        queued = queued_raw if isinstance(queued_raw, int) else 0
        return True, active, queued
    return True, 0, 0


def _effective_operation_credit_cap() -> int:
    """Current effective max operation credits (Host Resource Governor when available)."""
    try:
        from e2e_core.host_resource_governor import effective_browser_operation_credits

        return max(1, min(MAX_OPERATION_CREDITS, effective_browser_operation_credits()))
    except ImportError:
        pass
    override = os.environ.get("CDMCP_MUX_MAX_IN_FLIGHT")
    if override:
        return max(1, min(MAX_OPERATION_CREDITS, int(override)))
    return MAX_OPERATION_CREDITS


def _facade_override(name: str, fallback: object) -> object:
    """Read test/compatibility overrides from the public package facade."""
    facade = sys.modules.get("browser_orchestrator")
    if facade is None:
        return fallback
    override = getattr(facade, name, fallback)
    return override if override is not fallback else fallback


def _browser_orchestrator_daemon_required() -> bool:
    return os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() == "1"


def assert_browser_orchestrator_daemon_ready(*, wait_sec: float = 0.0) -> None:
    """Fail-fast when MYRM_BROWSER_ORCHESTRATOR=1 but daemon is unreachable."""
    if not _browser_orchestrator_daemon_required():
        return
    try:
        from browser_orchestrator.client import (
            BrowserOrchestratorClient,
        )  # noqa: PLC0415
    except ImportError as exc:
        raise RuntimeError(
            "BROWSER_ORCHESTRATOR_REQUIRED: browser_orchestrator.client unavailable"
        ) from exc
    client = BrowserOrchestratorClient()
    deadline = time.time() + max(0.0, wait_sec)
    while True:
        if client.is_alive():
            return
        if time.time() >= deadline:
            break
        time.sleep(0.25)
    raise RuntimeError(
        "BROWSER_ORCHESTRATOR_REQUIRED: daemon not running — "
        "run MYRM_BROWSER_ORCHESTRATOR=1 ./myrm ready --chrome"
    )


def _scheduler_int(scheduler: dict[str, object], key: str) -> int:
    raw = scheduler.get(key)
    return raw if isinstance(raw, int) else 0


def _snapshot_from_daemon_status(
    status: dict[str, object], *, governor_bound: bool
) -> dict[str, object]:
    scheduler = status.get("scheduler")
    sched: dict[str, object] = scheduler if isinstance(scheduler, dict) else {}
    recovery = status.get("recovery")
    recovery_map: dict[str, object] = recovery if isinstance(recovery, dict) else {}
    in_flight = _scheduler_int(sched, "activeOps")
    queued = _scheduler_int(sched, "queuedOps")
    effective_cap = (
        _scheduler_int(sched, "effectiveCredits") or _effective_operation_credit_cap()
    )
    max_credits = _scheduler_int(sched, "maxCredits") or MAX_OPERATION_CREDITS
    active_operations_raw = sched.get("activeOperations")
    active_operations = (
        active_operations_raw if isinstance(active_operations_raw, list) else []
    )
    queued_operations_raw = sched.get("queuedOperations")
    queued_operations = (
        queued_operations_raw if isinstance(queued_operations_raw, list) else []
    )
    recent_queue_waits_raw = sched.get("recentQueueWaits")
    recent_queue_waits = (
        recent_queue_waits_raw if isinstance(recent_queue_waits_raw, list) else []
    )
    daemon_state = str(status.get("state", "UNKNOWN"))
    if recovery_map.get("recovering") is True:
        health = BrowserPlaneHealth.RECOVERING
    elif daemon_state in {"FAILED"}:
        health = BrowserPlaneHealth.FAILED
    elif in_flight >= effective_cap:
        health = BrowserPlaneHealth.DEGRADED
    else:
        health = BrowserPlaneHealth.READY
    return {
        "health": health.value,
        "mux_snapshot_available": True,
        "operation_credits_max": max_credits,
        "operation_credits_effective": effective_cap,
        "operation_credits_in_flight": in_flight,
        "operation_credits_available": max(0, effective_cap - in_flight),
        "operation_credits_queued": queued,
        "active_operations": active_operations,
        "queued_operations": queued_operations,
        "recent_queue_waits": recent_queue_waits,
        "credit_registry": "browser_orchestrator_daemon",
        "governor_bound": governor_bound,
        "daemon_state": daemon_state,
        "daemon_generation": status.get("generation", 0),
    }


def _try_daemon_snapshot() -> dict[str, object] | None:
    try:
        from browser_orchestrator.client import (
            BrowserOrchestratorClient,
        )  # noqa: PLC0415
    except ImportError:
        return None
    client = BrowserOrchestratorClient()
    if not client.is_alive():
        return None
    governor_bound = False
    try:
        from e2e_core.host_resource_governor import host_resource_governor_snapshot

        governor = host_resource_governor_snapshot()
        effective = governor.get("effective_browser_slots")
        if isinstance(effective, int):
            client.set_effective_credits(effective)
            governor_bound = True
    except (AttributeError, OSError, TimeoutError, RuntimeError, ValueError):
        governor_bound = False
    status = client.status()
    return _snapshot_from_daemon_status(dict(status), governor_bound=governor_bound)


def browser_orchestrator_snapshot() -> dict[str, object]:
    """Produce a snapshot of the browser data plane for e2e-context.

    Health determination:
    - UNKNOWN: mux not reachable or probe failed
    - READY: in-flight < effective cap, recovery budget > 0
    - DEGRADED: in-flight >= effective cap, or recovery budget exhausted
    - RECOVERING: recovery in progress (detected via mux generation change)
    """
    daemon_probe = _facade_override("_try_daemon_snapshot", _try_daemon_snapshot)
    daemon_snap = daemon_probe() if callable(daemon_probe) else None
    if daemon_snap is not None:
        return daemon_snap
    if _browser_orchestrator_daemon_required():
        cap_probe = _facade_override(
            "_effective_operation_credit_cap", _effective_operation_credit_cap
        )
        effective_cap = cap_probe() if callable(cap_probe) else MAX_OPERATION_CREDITS
        return {
            "health": BrowserPlaneHealth.UNKNOWN.value,
            "mux_snapshot_available": False,
            "operation_credits_max": MAX_OPERATION_CREDITS,
            "operation_credits_effective": effective_cap,
            "operation_credits_in_flight": 0,
            "operation_credits_available": effective_cap,
            "operation_credits_queued": 0,
            "credit_registry": "browser_orchestrator_daemon",
            "governor_bound": True,
        }

    mux_probe = _facade_override("_mux_scheduler_probe", _mux_scheduler_probe)
    alive, active, queued = (
        mux_probe() if callable(mux_probe) else (False, 0, 0)
    )

    from mux.upstream_admission import list_active_upstream_operations  # noqa: PLC0415

    try:
        ops = list_active_upstream_operations()
    except OSError:
        cap_probe = _facade_override(
            "_effective_operation_credit_cap", _effective_operation_credit_cap
        )
        effective_cap = cap_probe() if callable(cap_probe) else MAX_OPERATION_CREDITS
        return {
            "health": BrowserPlaneHealth.UNKNOWN.value,
            "mux_snapshot_available": False,
            "operation_credits_max": MAX_OPERATION_CREDITS,
            "operation_credits_effective": effective_cap,
            "operation_credits_in_flight": 0,
            "operation_credits_available": 0,
            "operation_credits_queued": 0,
            "credit_registry": "unavailable",
            "governor_bound": False,
        }
    in_flight = min(len(ops), MAX_OPERATION_CREDITS)
    cap_probe = _facade_override(
        "_effective_operation_credit_cap", _effective_operation_credit_cap
    )
    effective_cap = cap_probe() if callable(cap_probe) else MAX_OPERATION_CREDITS

    if not alive:
        return {
            "health": BrowserPlaneHealth.UNKNOWN.value,
            "mux_snapshot_available": False,
            "operation_credits_max": MAX_OPERATION_CREDITS,
            "operation_credits_effective": effective_cap,
            "operation_credits_in_flight": 0,
            "operation_credits_available": effective_cap,
            "operation_credits_queued": 0,
            "credit_registry": "mux_upstream_admission",
            "governor_bound": True,
        }

    from mux.transport_supervisor import recovery_budget_remaining  # noqa: PLC0415

    budget = recovery_budget_remaining()
    if in_flight >= effective_cap:
        health = BrowserPlaneHealth.DEGRADED
    elif budget <= 0:
        health = BrowserPlaneHealth.DEGRADED
    else:
        health = BrowserPlaneHealth.READY

    return {
        "health": health.value,
        "mux_snapshot_available": True,
        "operation_credits_max": MAX_OPERATION_CREDITS,
        "operation_credits_effective": effective_cap,
        "operation_credits_in_flight": in_flight,
        "operation_credits_available": max(0, effective_cap - in_flight),
        "operation_credits_queued": queued,
        "credit_registry": "mux_upstream_admission",
        "governor_bound": True,
    }


def _wait_daemon_operation_credit(*, budget_sec: float) -> None:
    deadline = time.time() + max(0.1, budget_sec)
    while time.time() < deadline:
        snap = _try_daemon_snapshot()
        if snap is None:
            raise RuntimeError(
                "BROWSER_ORCHESTRATOR_REQUIRED: daemon not running — "
                "run MYRM_BROWSER_ORCHESTRATOR=1 ./myrm ready --chrome"
            )
        available_raw = snap.get("operation_credits_available", 0)
        available = available_raw if isinstance(available_raw, int) else 0
        if available > 0:
            return
        time.sleep(0.05)
    raise TimeoutError(f"daemon operation credit unavailable within {budget_sec:.1f}s")


@contextmanager
def browser_operation_credit_slot(
    *,
    budget_sec: float = 180.0,
    current_node: str = "unknown",
) -> Generator[None, None, None]:
    """Acquire one browser operation credit, blocking until available."""
    if _browser_orchestrator_daemon_required():
        _wait_daemon_operation_credit(budget_sec=budget_sec)
        yield
        return
    del current_node
    from mux.upstream_admission import upstream_cold_attach_slot  # noqa: PLC0415

    with upstream_cold_attach_slot():
        yield


def wait_for_operation_credit(
    *, budget_sec: float = 180.0, current_node: str = "unknown"
) -> None:
    """Block until no peer holds an upstream operation credit (fair queue SSOT)."""
    if _browser_orchestrator_daemon_required():
        _wait_daemon_operation_credit(budget_sec=budget_sec)
        return
    from e2e_core.mux_transport_queue import wait_mux_transport_turn  # noqa: PLC0415

    wait_mux_transport_turn(budget_sec=budget_sec, current_node=current_node)


def prune_self_owned_blanks(
    *, cdp_port: int = 9333, threshold: int = 5
) -> tuple[int, int, int, int]:
    """Prune blank/orphan pages owned by current session only.

    Returns (infra_closed, infra_failed, orphan_closed, orphan_failed).
    Delegates to infra_browser_registry and browser_tab_hygiene
    but only for current session's pages.
    """
    from e2e_core.infra_browser_registry import prune_infra_registry  # noqa: PLC0415
    from e2e_core.browser_tab_hygiene import prune_orphan_cdp_pages  # noqa: PLC0415

    infra_closed, infra_failed = prune_infra_registry(cdp_port)
    orphan_closed, orphan_failed = prune_orphan_cdp_pages(
        cdp_port=cdp_port, threshold=threshold
    )
    return infra_closed, infra_failed, orphan_closed, orphan_failed
