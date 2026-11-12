"""Mux-facing steps of opening a page: transport turns, cold-attach drain, threaded new_page and tool-wall deadlines."""

from __future__ import annotations

import os
import sys
import threading
import time
from pathlib import Path

from cdp_chat.support import wait_e2e_cdp_ready
from chrome_mcp.client import ChromeMcpClient, McpPage
from dev_gate.contract import MUX_RECLAIM_STALL_TOKEN, is_e2e_signoff_runtime
from e2e_core.orchestrator import touch_wall_progress

from tests.support.e2e_runtime_guard import heartbeat_once

from .open_page_budget import (
    _extend_open_page_deadlines_for_queue_wait,
    _mux_cold_attach_drain_budget_sec,
    _mux_transport_wait_budget_sec,
    _open_page_cdp_probe_budget_sec,
    _open_page_parallel_total_wall_only,
    _should_skip_attach_preflight_restart,
    _signoff_mux_drain_budget_sec,
)
from .parallel_load import _parallel_open_page_peer_count


def _restart_open_page_mux_budget(
    *,
    open_page_wall_budget_sec: float,
    open_page_total_budget_sec: float,
) -> tuple[float, float, float]:
    """Reset open_mcp_page clocks after mux restart for signoff retry."""
    heartbeat_once()
    touch_wall_progress(current_node="open_mcp_page_mux_retry")
    if os.environ.get("MYRM_BROWSER_ORCHESTRATOR", "").strip() == "1":
        transport_session_started = time.monotonic()
        return (
            transport_session_started,
            transport_session_started + open_page_wall_budget_sec,
            transport_session_started + open_page_total_budget_sec,
        )
    _force_mux_attach_restart_after_new_page_timeout()
    try:
        ChromeMcpClient().recover_mux_transport()
    except RuntimeError:
        pass
    cdp_budget = _open_page_cdp_probe_budget_sec()
    _require_e2e_cdp_ready(budget_sec=cdp_budget)
    time.sleep(min(5.0, max(2.0, cdp_budget * 0.05)))
    try:
        drain_budget = _mux_cold_attach_drain_budget_sec()
        _wait_mux_cold_attach_drain(budget_sec=drain_budget)
    except RuntimeError:
        pass
    transport_session_started = time.monotonic()
    return (
        transport_session_started,
        transport_session_started + open_page_wall_budget_sec,
        transport_session_started + open_page_total_budget_sec,
    )


def _wait_open_page_mux_turn(
    *,
    budget_sec: float,
    current_node: str,
    transport_session_started: float,
    wall_deadline: float,
    total_deadline: float,
) -> tuple[float, float, float]:
    from browser_orchestrator import wait_for_operation_credit

    wait_started = time.monotonic()
    wait_for_operation_credit(budget_sec=budget_sec, current_node=current_node)
    return _extend_open_page_deadlines_for_queue_wait(
        elapsed_sec=time.monotonic() - wait_started,
        transport_session_started=transport_session_started,
        wall_deadline=wall_deadline,
        total_deadline=total_deadline,
    )


def _force_mux_attach_restart_after_new_page_timeout() -> None:
    """Restart mux daemon when tools/list probe passes but new_page hangs (attach heal)."""
    if _should_skip_attach_preflight_restart():
        return
    import sys

    lib_dir = Path(__file__).resolve().parents[4] / "scripts" / "dev" / "lib"
    if str(lib_dir) not in sys.path:
        sys.path.insert(0, str(lib_dir))
    from mux.attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason="open_mcp_page new_page timeout")


def _wait_cold_shim_peer_pressure_drain(*, budget_sec: float, current_node: str) -> None:
    """Wait until mux peer load drops below cold-shim defer threshold."""
    try:
        from mux.transport_supervisor import (
            _cold_shim_defer_peer_load,
            cold_shim_restart_defer_peer_threshold,
        )
    except ImportError:
        return
    defer_threshold = cold_shim_restart_defer_peer_threshold()
    deadline = time.monotonic() + max(0.0, budget_sec)
    poll_sec = 1.0
    while time.monotonic() < deadline:
        peers = _cold_shim_defer_peer_load()
        if peers < defer_threshold:
            return
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        print(
            f"E2E_COLD_SHIM_PEER_WAIT: peers={peers} threshold={defer_threshold} remaining={remaining:.0f}s node={current_node}",
            file=sys.stderr,
            flush=True,
        )
        time.sleep(min(poll_sec, remaining))
        poll_sec = min(poll_sec * 1.2, 5.0)
    peers = _cold_shim_defer_peer_load()
    if peers >= defer_threshold:
        if is_e2e_signoff_runtime():
            print(
                f"E2E_COLD_SHIM_PEER_WAIT: peers={peers} "
                f">= {defer_threshold} after {budget_sec:.0f}s — "
                f"signoff proceed to mux recovery lock (node={current_node})",
                file=sys.stderr,
                flush=True,
            )
            return
        raise RuntimeError(
            f"E2E_COLD_SHIM_PEER_PRESSURE: defer_peer_load={peers} "
            f">= {defer_threshold} after {budget_sec:.0f}s "
            f"(node={current_node}; do not stop other pytest)"
        )


def _signoff_wait_mux_before_new_page(*, budget_sec: float | None = None) -> None:
    """Signoff pre-new_page mux gate — operation-credit transport SSOT (P0-B)."""
    from browser_orchestrator import wait_for_operation_credit

    wait_budget = float(budget_sec if budget_sec is not None else _signoff_mux_drain_budget_sec())
    gate_started = time.monotonic()
    credit_budget = min(wait_budget, _mux_transport_wait_budget_sec())
    wait_for_operation_credit(
        budget_sec=credit_budget,
        current_node="open_mcp_page_signoff_gate",
    )
    peer_budget = max(30.0, wait_budget - (time.monotonic() - gate_started))
    _wait_cold_shim_peer_pressure_drain(
        budget_sec=peer_budget,
        current_node="open_mcp_page_signoff_peer_gate",
    )


def _signoff_threaded_new_page(
    client: ChromeMcpClient,
    url: str,
    *,
    timeout_ms: int,
    join_timeout_sec: float,
) -> McpPage:
    """Run new_page off the main thread so stall tripwire can abandon without SIGINT."""
    outcome: list[McpPage | BaseException] = []

    def _worker() -> None:
        try:
            outcome.append(client.new_page(url, timeout_ms=timeout_ms))
        except BaseException as exc:
            outcome.append(exc)

    worker = threading.Thread(
        target=_worker,
        name="signoff-new-page",
        daemon=True,
    )
    worker.start()
    from dev_gate.contract import (
        E2E_SIGNOFF_NEW_PAGE_JOIN_EXCEEDED_TOKEN,
        signoff_new_page_join_stall_abandon_sec,
    )

    stall_abandon_sec = signoff_new_page_join_stall_abandon_sec(
        join_timeout_sec=join_timeout_sec,
    )
    join_deadline = time.monotonic() + join_timeout_sec
    stall_deadline = time.monotonic() + stall_abandon_sec
    poll_sec = 5.0
    while worker.is_alive():
        now = time.monotonic()
        if now >= join_deadline or now >= stall_deadline:
            break
        worker.join(timeout=min(poll_sec, join_deadline - now, stall_deadline - now))
    if worker.is_alive():
        try:
            client.abandon_inflight_requests(cdp_drift=True)
        except RuntimeError:
            pass
        _force_mux_attach_restart_after_new_page_timeout()
        elapsed = min(join_timeout_sec, stall_abandon_sec)
        if time.monotonic() >= stall_deadline and time.monotonic() < join_deadline:
            elapsed = stall_abandon_sec
            print(
                f"E2E_SIGNOFF_NEW_PAGE_JOIN_STALL: "
                f"stall_abandon={stall_abandon_sec:.0f}s join_cap={join_timeout_sec:.0f}s url={url}",
                file=sys.stderr,
                flush=True,
            )
        else:
            print(
                f"{E2E_SIGNOFF_NEW_PAGE_JOIN_EXCEEDED_TOKEN}: join={join_timeout_sec:.0f}s url={url}",
                file=sys.stderr,
                flush=True,
            )
        raise TimeoutError(f"Chrome MCP new_page thread join timed out after {elapsed:.0f}s")
    if not outcome:
        raise RuntimeError("Chrome MCP new_page worker exited without result")
    result = outcome[0]
    if isinstance(result, BaseException):
        raise result
    return result


def _open_page_new_page(
    client: ChromeMcpClient,
    url: str,
    *,
    timeout_ms: int,
    attempt_wall_deadline: float,
) -> McpPage:
    if is_e2e_signoff_runtime():
        from dev_gate.contract import (
            signoff_new_page_join_timeout_sec,
            signoff_open_mcp_budgets,
        )

        signoff_open_mcp_budgets(
            parallel_peers=_parallel_open_page_peer_count(),
        )
        _signoff_wait_mux_before_new_page(
            budget_sec=_signoff_mux_drain_budget_sec(),
        )
        join_timeout_sec = signoff_new_page_join_timeout_sec(
            page_timeout_ms=timeout_ms,
            parallel_peers=_parallel_open_page_peer_count(),
        )
        return _signoff_threaded_new_page(
            client,
            url,
            timeout_ms=timeout_ms,
            join_timeout_sec=join_timeout_sec,
        )
    return client.new_page(url, timeout_ms=timeout_ms)


def _require_e2e_cdp_ready(*, budget_sec: float | None = None) -> None:
    """SSOT CDP probe for open_mcp_page — mux heal deferred to new_page inner retry."""
    import os

    port = int(os.environ.get("MYRM_CHROME_E2E_PORT", "9333"))
    wait_budget = budget_sec if budget_sec is not None else _open_page_cdp_probe_budget_sec()
    deadline = time.monotonic() + wait_budget

    while time.monotonic() < deadline:
        heartbeat_once()
        touch_wall_progress(current_node="open_mcp_page_cdp_probe")
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            break
        if wait_e2e_cdp_ready(
            timeout_sec=min(5.0, max(1.0, remaining)),
            port=port,
        ):
            return
        time.sleep(1.0)
    raise RuntimeError(f"CDP endpoint not ready after {wait_budget:.0f}s on :{port}")


def _wait_mux_cold_attach_drain(*, budget_sec: float) -> None:
    """Wait until mux operation credits are free — orchestrator SSOT (P0-B)."""
    from browser_orchestrator import wait_for_operation_credit

    wait_for_operation_credit(
        budget_sec=budget_sec,
        current_node="open_mcp_page_mux_drain",
    )


def _retryable_open_page_error(exc: BaseException) -> bool:
    message = str(exc).lower()
    return (
        MUX_RECLAIM_STALL_TOKEN.lower() in message
        or "mux cold attach saturated" in message
        or "no page found" in message
        or "response timed out" in message
        or "thread join timed out" in message
        or "e2e_signoff_new_page_join_stall" in message
        or "wall budget exhausted" in message
        or "transport closed" in message
        or "transport dead" in message
        or "connection reset" in message
        or "could not connect to chrome" in message
        or "unexpected server response: 404" in message
        or "cdp endpoint not ready" in message
        or "cdp/mux endpoint not ready" in message
        or "shpoib runtime rebind after reload failed" in message
    )


def _sync_open_page_tool_wall(
    client: ChromeMcpClient,
    *,
    wall_deadline: float,
    total_deadline: float,
    steps_remaining: int,
    floor_sec: float = 90.0,
) -> None:
    """Refresh per-step tool wall budget so SHPOIB multi-hop open does not exhaust early."""
    now = time.monotonic()
    remaining = min(wall_deadline, total_deadline) - now
    if remaining <= 0:
        if is_e2e_signoff_runtime():
            return
        client.set_tool_wall_deadline(now)
        return
    if _open_page_parallel_total_wall_only():
        client.set_tool_wall_deadline(total_deadline)
        return
    parallel_peers = _parallel_open_page_peer_count()
    if parallel_peers >= 2:
        floor_sec = max(floor_sec, min(120.0 + parallel_peers * 8.0, 180.0))
    if parallel_peers >= 4:
        client.set_tool_wall_deadline(now + min(remaining, 180.0))
        return
    slice_sec = max(floor_sec, remaining / max(1, steps_remaining))
    client.set_tool_wall_deadline(now + min(remaining, slice_sec))


def _refresh_signoff_open_nav_tool_wall(
    client: ChromeMcpClient,
    *,
    wall_deadline: float,
    total_deadline: float,
) -> None:
    """refresh tool wall after mux/new_page gate consumed attempt-local remaining."""
    if not is_e2e_signoff_runtime():
        return
    from dev_gate.contract import signoff_open_mcp_budgets

    now = time.monotonic()
    peers = _parallel_open_page_peer_count()
    budgets = signoff_open_mcp_budgets(parallel_peers=peers)
    attempt_remaining = min(
        max(0.0, wall_deadline - now),
        max(0.0, total_deadline - now),
    )
    bootstrap_remaining = attempt_remaining
    try:
        from e2e_session_runtime.lifecycle import current_phase, remaining_wall_sec

        if current_phase() == "bootstrap":
            bootstrap_remaining = max(attempt_remaining, remaining_wall_sec())
    except ImportError:
        pass
    nav_floor = min(float(budgets.layout_wait_sec), budgets.wall_budget_sec * 0.6)
    if peers >= 2:
        nav_floor = max(nav_floor, 90.0 + peers * 12.0)
    if attempt_remaining < 30.0 and bootstrap_remaining < 30.0:
        # mux queue consumed attempt wall — grant fresh nav slice from SSOT.
        budget = max(nav_floor, float(budgets.layout_wait_sec), budgets.wall_budget_sec * 0.55)
    else:
        budget = max(nav_floor, min(bootstrap_remaining, budgets.wall_budget_sec))
    client.set_tool_wall_deadline(now + budget)
