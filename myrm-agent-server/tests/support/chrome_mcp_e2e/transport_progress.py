"""Heartbeat and stall tripwire around a blocking MCP call."""

from __future__ import annotations

import sys
import threading
import time
from collections.abc import Iterator
from contextlib import contextmanager

from dev_gate.contract import is_e2e_signoff_runtime
from e2e_core.orchestrator import touch_wall_progress

from tests.support.e2e_runtime_guard import heartbeat_once

from .open_page_budget import (
    _OPEN_PAGE_NEW_PAGE_TIMEOUT_MS,
    _OPEN_PAGE_REQUEST_TIMEOUT_SEC,
    _dev_private_shpoib_bootstrap_phase,
    _open_page_body_fraction_cap_sec,
    _open_page_parallel_budgets,
)
from .parallel_load import _parallel_open_page_peer_count

_PROGRESS_HEARTBEAT_INTERVAL_SEC = 15.0
_TRANSPORT_PROGRESS_INTERVAL_SEC = 30.0


def _emit_transport_progress(*, current_node: str, node_started: float) -> None:
    from dev_gate.contract import E2E_TRANSPORT_PROGRESS_TOKEN

    elapsed = time.monotonic() - node_started
    print(
        f"{E2E_TRANSPORT_PROGRESS_TOKEN}: node={current_node} node_elapsed={int(elapsed)}s (do not stop other pytest)",
        file=sys.stderr,
        flush=True,
    )


@contextmanager
def _blocking_progress_loop(
    *,
    current_node: str,
    transport_session_started: float | None = None,
) -> Iterator[None]:
    """Keep lease + wall progress fresh while mux MCP calls may block (anti hung-reap)."""
    import os
    import signal

    from dev_gate.contract import signoff_open_page_transport_stall_cap_sec
    from e2e_core.stall_guard import assert_transport_node_not_stuck, transport_stall_cap_sec

    del transport_session_started
    stop = threading.Event()
    node_started = time.monotonic()
    last_transport_emit = node_started
    (
        _client_timeout,
        _page_timeout_ms,
        _wall_budget,
        open_page_total_budget,
        _attempts,
    ) = _open_page_parallel_budgets(
        _OPEN_PAGE_REQUEST_TIMEOUT_SEC,
        new_page_timeout_ms=_OPEN_PAGE_NEW_PAGE_TIMEOUT_MS,
    )
    if is_e2e_signoff_runtime():
        # do not min() against per-attempt transport budget — signoff stall cap
        # already scales with MYRM_E2E_SIGNOFF_BATCH_BODY_SEC.
        stall_cap = signoff_open_page_transport_stall_cap_sec()
    else:
        stall_cap = max(transport_stall_cap_sec(), open_page_total_budget + 15.0)
        if _parallel_open_page_peer_count() >= 2:
            # mux queue may block longer than NODE_STUCK peer cap — use body
            # fraction budget so parallel LIVE can reach outer transport retry.
            stall_cap = max(
                transport_stall_cap_sec(),
                _open_page_body_fraction_cap_sec(),
            )
    try:
        from e2e_session_runtime.lifecycle import current_phase

        if current_phase() == "bootstrap":
            if is_e2e_signoff_runtime() or _dev_private_shpoib_bootstrap_phase():
                from dev_gate.contract import signoff_bootstrap_transport_stall_cap_sec

                # dev PRIVATE SHPOIB bootstrap — align stall with mux queue headroom.
                stall_cap = max(
                    stall_cap,
                    signoff_bootstrap_transport_stall_cap_sec(
                        parallel_peers=_parallel_open_page_peer_count(),
                        page_timeout_ms=min(_OPEN_PAGE_NEW_PAGE_TIMEOUT_MS, 90_000),
                    ),
                )
            else:
                from mux.transport_supervisor import bootstrap_wall_cap_sec

                bootstrap_cap = float(bootstrap_wall_cap_sec(pessimistic=True))
                stall_cap = min(stall_cap, bootstrap_cap)
    except ImportError:
        pass

    def _loop() -> None:
        nonlocal last_transport_emit
        while not stop.wait(_PROGRESS_HEARTBEAT_INTERVAL_SEC):
            try:
                assert_transport_node_not_stuck(
                    current_node=current_node,
                    node_started=node_started,
                    stall_cap=stall_cap,
                )
            except RuntimeError:
                # Stall tripwire must interrupt the main thread blocked in MCP I/O.
                os.kill(os.getpid(), signal.SIGINT)
                continue
            heartbeat_once()
            touch_wall_progress(current_node=current_node)
            now = time.monotonic()
            if now - last_transport_emit >= _TRANSPORT_PROGRESS_INTERVAL_SEC:
                _emit_transport_progress(current_node=current_node, node_started=node_started)
                last_transport_emit = now

    worker = threading.Thread(target=_loop, name="open-mcp-page-progress", daemon=True)
    worker.start()
    try:
        yield
    finally:
        stop.set()
        worker.join(timeout=2.0)
