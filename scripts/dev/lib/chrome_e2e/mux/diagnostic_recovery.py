"""Mux transport recovery implementations — diagnostic mode only (§19.10 A4).

Production chrome_e2e uses MYRM_BROWSER_ORCHESTRATOR=1; this module is loaded only
when MYRM_CHROME_MCP_DIAGNOSTIC=1 for one-shot maintainer diagnosis.
"""

from __future__ import annotations

import logging
import time
from typing import TYPE_CHECKING

from browser_orchestrator import browser_operation_credit_slot
from dev_gate.contract import MUX_RECLAIM_STALL_TOKEN, mux_page_reclaim_hard_timeout_sec
from chrome_mcp.errors import is_page_ownership_error_message as _is_page_ownership_error
from chrome_mcp.page_helpers import (
    check_mux_reclaim_deadline,
    parallel_mux_peer_count,
    reclaim_wall_deadline,
    remaining_reclaim_sec,
)
from chrome_mcp.protocol import parse_new_page
from mux.transport_adapter import _TRANSPORT_RECOVER_ATTEMPTS

if TYPE_CHECKING:
    from chrome_mcp.client import ChromeMcpClient, McpPage

_LOGGER = logging.getLogger(__name__)


def reopen_owned_page_inner(client: ChromeMcpClient, page: McpPage) -> McpPage:
    from chrome_mcp.client import McpPage as McpPageCls

    reclaim_deadline = reclaim_wall_deadline()
    reclaim_started = time.monotonic()
    client._ensure_shim_transport()
    check_mux_reclaim_deadline(
        reclaim_deadline, "reopen_start", started=reclaim_started
    )
    reopen_url = (page.url or "http://127.0.0.1:3000").strip()
    runtime_binding = client._runtime_binding_source_for(reopen_url)
    old_target_id = page.target_id.strip()
    import chrome_mcp.client as _cmc

    if old_target_id and not _cmc._http_close_exact_target(old_target_id):
        raise RuntimeError(
            f"Chrome MCP reopen failed: could not close previous targetId={old_target_id}"
        )
    client._pages.pop(page.page_id, None)
    initial_url = "about:blank" if runtime_binding is not None else reopen_url
    arguments: dict[str, object] = {"url": initial_url, "timeout": 120_000}
    if page.context_id is not None:
        arguments["isolatedContext"] = page.context_id
    remaining = remaining_reclaim_sec(reclaim_deadline)
    check_mux_reclaim_deadline(
        reclaim_deadline, "new_page", started=reclaim_started
    )
    with browser_operation_credit_slot():
        result = client.call_tool(
            "new_page",
            arguments,
            timeout_sec=min(
                125.0,
                client._request_timeout_sec,
                remaining,
            ),
        )
    page_id, target_id = parse_new_page(result)
    lease_id = page.lease_id
    reopened = McpPageCls(
        page_id=page_id,
        target_id=target_id,
        lease_id=lease_id,
        context_id=page.context_id,
        url=reopen_url,
    )
    client._heartbeat_lease(lease_id)
    try:
        check_mux_reclaim_deadline(
            reclaim_deadline, "bind_lease", started=reclaim_started
        )
        client._bind_page_lease(reopened)
    except RuntimeError as exc:
        if MUX_RECLAIM_STALL_TOKEN in str(exc):
            raise
        if "LEASE_NOT_ACTIVE" not in str(exc):
            raise
        client._page_lease_heartbeat.untrack(lease_id)
        lease_id = client._acquire_page_lease()
        reopened = McpPageCls(
            page_id=page_id,
            target_id=target_id,
            lease_id=lease_id,
            context_id=page.context_id,
            url=reopen_url,
        )
        client._heartbeat_lease(lease_id)
        check_mux_reclaim_deadline(
            reclaim_deadline, "bind_lease_retry", started=reclaim_started
        )
        client._bind_page_lease(reopened)
    client._pages[page_id] = reopened
    client._page_lease_heartbeat.track(lease_id)
    if runtime_binding is not None:
        remaining = remaining_reclaim_sec(reclaim_deadline)
        check_mux_reclaim_deadline(
            reclaim_deadline, "runtime_bind", started=reclaim_started
        )
        client._bind_and_navigate_runtime_page(
            reopened,
            reopen_url,
            runtime_binding,
            timeout_ms=min(
                120_000,
                int(max(5_000, remaining * 1000)),
            ),
        )
    return reopened


def recover_mux_transport_inner(
    client: ChromeMcpClient,
    *,
    start_generation: int | None = None,
) -> None:
    held_lock = client._acquire_request_lock()
    try:
        _LOGGER.warning(
            "RECOVER_MUX_TRANSPORT: gen=%s pages=%d disconnected=%d",
            start_generation,
            len(client._pages),
            len(client._disconnected_pages),
        )
        reclaim_deadline = reclaim_wall_deadline()
        saved_pages = client._collapse_pages_for_recovery(
            {**client._disconnected_pages, **client._pages}
        )
        from mux.transport_recovery_core import (
            TRSM_MODE_TOKEN,
            TransportRecoveryMode,
        )

        trsm_mode = client._resolve_trsm_mode()
        peer_count = parallel_mux_peer_count()
        _LOGGER.warning(
            "%s=%s parallel_mux_peers=%d pages=%d",
            TRSM_MODE_TOKEN,
            trsm_mode.value,
            peer_count,
            len(saved_pages),
        )
        if trsm_mode == TransportRecoveryMode.PARALLEL_PAGE_RECLAIM and saved_pages:
            client._reclaim_pages_parallel_safe(saved_pages, reclaim_deadline)
            return
        client._teardown_shim_process()
        last_error: RuntimeError | None = None
        for attempt in range(_TRANSPORT_RECOVER_ATTEMPTS):
            if (
                start_generation is not None
                and start_generation != client._request_generation
            ):
                raise RuntimeError(
                    f"{MUX_RECLAIM_STALL_TOKEN}: request abandoned during "
                    f"transport recovery (orphan recovery in progress)"
                )
            check_mux_reclaim_deadline(
                reclaim_deadline,
                "recover_mux_transport",
                started=reclaim_deadline
                - float(mux_page_reclaim_hard_timeout_sec()),
            )
            try:
                client._spawn_shim_process()
                client._initialize_shim_session()
                break
            except RuntimeError as exc:
                last_error = exc
                client._teardown_shim_process()
                if attempt + 1 < _TRANSPORT_RECOVER_ATTEMPTS:
                    time.sleep(
                        min(
                            0.75 * (attempt + 1),
                            remaining_reclaim_sec(reclaim_deadline),
                        )
                    )
        else:
            if last_error is not None:
                raise last_error
            check_mux_reclaim_deadline(
                reclaim_deadline,
                "recover_mux_transport",
                started=reclaim_deadline
                - float(mux_page_reclaim_hard_timeout_sec()),
            )
            return
        if not saved_pages:
            return
        rebuild_disconnected_pages(client, saved_pages, reclaim_deadline)
    finally:
        client._release_request_lock(held_lock)


def rebuild_disconnected_pages(
    client: ChromeMcpClient,
    saved_pages: dict[int, McpPage],
    reclaim_deadline: float,
) -> None:
    from chrome_mcp.client import McpPage as McpPageCls

    page_items = list(saved_pages.items())
    for idx, (old_page_id, old_page) in enumerate(page_items):
        remaining = remaining_reclaim_sec(reclaim_deadline)
        if remaining < 5.0:
            _LOGGER.warning(
                "page rebuild budget exhausted; %d pages remain disconnected",
                len(page_items) - idx,
            )
            break
        new_page_id: int | None = None
        for rebuild_attempt in range(2):
            remaining = remaining_reclaim_sec(reclaim_deadline)
            if remaining < 5.0:
                break
            try:
                old_target = old_page.target_id.strip()
                import chrome_mcp.client as _cmc

                if old_target and rebuild_attempt == 0:
                    _cmc._http_close_exact_target(old_target)
                reopen_url = (old_page.url or "http://127.0.0.1:3000").strip()
                runtime_binding = client._runtime_binding_source_for(reopen_url)
                initial_url = (
                    "about:blank" if runtime_binding is not None else reopen_url
                )
                arguments: dict[str, object] = {
                    "url": initial_url,
                    "timeout": 60_000,
                }
                if old_page.context_id is not None:
                    arguments["isolatedContext"] = old_page.context_id
                with browser_operation_credit_slot():
                    result = client._call_tool_direct(
                        "new_page", arguments, timeout_sec=min(65.0, remaining)
                    )
                page_id, target_id = parse_new_page(result)
                new_page_id = page_id
                client._call_tool_direct(
                    "evaluate_script",
                    {
                        "pageId": page_id,
                        "function": "async () => document.readyState",
                    },
                    timeout_sec=min(10.0, remaining),
                )
                rebuilt = McpPageCls(
                    page_id=page_id,
                    target_id=target_id,
                    lease_id=old_page.lease_id,
                    context_id=old_page.context_id,
                    url=reopen_url,
                )
                client._heartbeat_lease(old_page.lease_id)
                client._bind_page_lease(rebuilt)
                if runtime_binding is not None:
                    client._bind_and_navigate_runtime_page(
                        rebuilt,
                        reopen_url,
                        runtime_binding,
                        timeout_ms=min(60_000, int(remaining * 1000)),
                    )
                client._pages[page_id] = rebuilt
                client._disconnected_pages.pop(old_page_id, None)
                client._page_lease_heartbeat.track(old_page.lease_id)
                _LOGGER.info(
                    "rebuilt page %d→%d (url=%s) after transport recovery",
                    old_page_id,
                    page_id,
                    reopen_url,
                )
                break
            except Exception as exc:
                if new_page_id is not None:
                    client._pages.pop(new_page_id, None)
                    try:
                        client._call_tool_direct(
                            "close_page",
                            {"pageId": new_page_id},
                            timeout_sec=10.0,
                        )
                    except Exception:
                        pass
                    new_page_id = None
                if rebuild_attempt + 1 >= 2 or not _is_page_ownership_error(
                    str(exc)
                ):
                    _LOGGER.warning(
                        "failed to rebuild page %d after transport recovery: %s",
                        old_page_id,
                        exc,
                    )
                    client._disconnected_pages.pop(old_page_id, None)
                    break
                _LOGGER.warning(
                    "rebuild page %d ownership probe failed (attempt %d): %s",
                    old_page_id,
                    rebuild_attempt + 1,
                    exc,
                )
                time.sleep(min(1.0, remaining_reclaim_sec(reclaim_deadline)))
