"""First-party Browser Orchestrator interface (P0-B SSOT).

[INPUT]
mux_upstream_admission (POS: mux cold-attach active operations probe — bridge until full daemon migration)
transport_supervisor (POS: recovery budget)
dev_gate_contract (POS: MUX_COLD_ATTACH_SLOTS constant)

[OUTPUT]
browser_orchestrator_snapshot(): health/credits/in-flight status for e2e-context
browser_operation_credit_slot(): context manager for acquiring an operation credit
wait_for_operation_credit(): block until a credit is available
prune_self_owned_blanks(): cleanup helper delegating to tab hygiene

[POS]
唯一浏览器数据面的 Python 客户端接口。
当前为过渡实现：通过 mux probe + mux_upstream_admission 提供 snapshot；
完整 Browser Orchestrator daemon 启用后，切换为直接读取 daemon socket 状态。
"""

from __future__ import annotations

import enum
import logging
import os
import time
import urllib.error
import urllib.request
from contextlib import contextmanager
from typing import Generator

_LOGGER = logging.getLogger(__name__)

MAX_OPERATION_CREDITS = 4


class BrowserPlaneHealth(enum.Enum):
    READY = "READY"
    DEGRADED = "DEGRADED"
    RECOVERING = "RECOVERING"
    UNKNOWN = "UNKNOWN"
    FAILED = "FAILED"


def _mux_probe() -> tuple[bool, int, int]:
    """Probe mux daemon via HTTP status endpoint.

    Returns (alive, active_ops, queued_ops).
    """
    port = int(os.environ.get("CDMCP_MUX_STATUS_PORT", "0"))
    if not port:
        return False, 0, 0
    try:
        url = f"http://127.0.0.1:{port}/status"
        with urllib.request.urlopen(url, timeout=2.0) as resp:
            import json
            data = json.loads(resp.read())
            scheduler = data.get("scheduler", {})
            return True, scheduler.get("active", 0), scheduler.get("queued", 0)
    except (urllib.error.URLError, OSError, ValueError):
        return False, 0, 0


def _effective_operation_credit_cap() -> int:
    """Current effective max operation credits.

    For now returns MAX_OPERATION_CREDITS; Host Resource Governor (P1)
    will dynamically adjust this between 1 and MAX_OPERATION_CREDITS.
    """
    override = os.environ.get("CDMCP_MUX_MAX_IN_FLIGHT")
    if override:
        return max(1, min(MAX_OPERATION_CREDITS, int(override)))
    return MAX_OPERATION_CREDITS


def browser_orchestrator_snapshot() -> dict[str, object]:
    """Produce a snapshot of the browser data plane for e2e-context.

    Health determination:
    - UNKNOWN: mux not reachable or probe failed
    - READY: in-flight < effective cap, recovery budget > 0
    - DEGRADED: in-flight >= effective cap, or recovery budget exhausted
    - RECOVERING: recovery in progress (detected via mux generation change)
    """
    alive, active, queued = _mux_probe()

    from mux_upstream_admission import list_active_upstream_operations  # noqa: PLC0415

    ops = list_active_upstream_operations()
    in_flight = min(len(ops), MAX_OPERATION_CREDITS)
    effective_cap = _effective_operation_credit_cap()

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

    from transport_supervisor import recovery_budget_remaining  # noqa: PLC0415

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


@contextmanager
def browser_operation_credit_slot(
    *,
    budget_sec: float = 180.0,
    current_node: str = "unknown",
) -> Generator[None, None, None]:
    """Acquire one browser operation credit, blocking until available.

    This is a bridge implementation. Full daemon migration will route
    through the Browser Orchestrator's fair scheduler directly.
    """
    wait_for_operation_credit(budget_sec=budget_sec, current_node=current_node)
    try:
        yield
    finally:
        pass


def wait_for_operation_credit(
    *, budget_sec: float = 180.0, current_node: str = "unknown"
) -> None:
    """Block until a browser operation credit becomes available.

    Bridge implementation: polls mux_upstream_admission active count.
    Full daemon migration will use event subscription.
    """
    from mux_upstream_admission import effective_max_slots  # noqa: PLC0415
    from mux_upstream_admission import list_active_upstream_operations  # noqa: PLC0415

    cap = effective_max_slots()
    deadline = time.monotonic() + budget_sec
    poll_interval = 0.5

    while time.monotonic() < deadline:
        active = len(list_active_upstream_operations())
        if active < cap:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        time.sleep(min(poll_interval, remaining))
        poll_interval = min(poll_interval * 1.5, 5.0)

    raise TimeoutError(
        f"Browser operation credit timeout after {budget_sec:.0f}s "
        f"(node={current_node}, cap={cap})"
    )


def prune_self_owned_blanks(
    *, cdp_port: int = 9333, threshold: int = 5
) -> tuple[int, int, int, int]:
    """Prune blank/orphan pages owned by current session only.

    Returns (infra_closed, infra_failed, orphan_closed, orphan_failed).
    Delegates to infra_browser_registry and browser_tab_hygiene
    but only for current session's pages.
    """
    from infra_browser_registry import prune_infra_registry  # noqa: PLC0415
    from browser_tab_hygiene import prune_orphan_cdp_pages  # noqa: PLC0415

    infra_closed, infra_failed = prune_infra_registry(cdp_port)
    orphan_closed, orphan_failed = prune_orphan_cdp_pages(
        cdp_port=cdp_port, threshold=threshold
    )
    return infra_closed, infra_failed, orphan_closed, orphan_failed
