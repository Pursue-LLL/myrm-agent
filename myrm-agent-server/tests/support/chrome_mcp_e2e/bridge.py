"""Wait for the React E2E bridge to appear on a page, healing a stuck load without reloading a slow one."""

from __future__ import annotations

import sys
import time

from cdp_chat.support import get_e2e_ui_url
from chrome_mcp.client import ChromeMcpClient, McpPage
from e2e_core.orchestrator import touch_wall_progress

from .bridge_diagnostics import (
    _BRIDGE_DIAG_HOOK_JS,
    _REACT_E2E_BRIDGE_PROBE_JS,
    _bridge_failure_diagnostics,
    _log_bridge_wait_state,
    _wait_for_page_load_to_settle,
)
from .page_guard import dismiss_blocking_modals
from .probe_result import _coerce_evaluate_result
from .reload import reload_mcp_page
from .warm_ui import _trigger_attach_client_warmup_once, _trigger_attach_frontend_heal_once, warm_ui_route


def _ensure_react_e2e_bridge_timeout_sec(requested: float) -> float:
    """Hot-path reused shells need extra bridge budget under parallel SHPOIB mux pressure."""
    from e2e_core.shared_ui_session import (
        _bootstrap_hot_path_reused,
        _parallel_bridge_ready_cap_sec,
        _resolve_bridge_ready_timeout_sec,
    )

    if _bootstrap_hot_path_reused():
        try:
            from e2e_core.shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

            if parallel_shared_ui_hydrate_queue_enabled():
                return _resolve_bridge_ready_timeout_sec(_parallel_bridge_ready_cap_sec())
        except ImportError:
            pass
        return 120.0
    return requested


def _orchestrator_shared_ui_contract_timeout_sec() -> float:
    """Orchestrator open_page contract: parallel lanes get full bridge cap (180s)."""
    from e2e_core.shared_ui_session import (
        _parallel_bridge_ready_cap_sec,
        _resolve_bridge_ready_timeout_sec,
    )

    request = 120.0
    try:
        from e2e_core.shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            request = _parallel_bridge_ready_cap_sec()
    except ImportError:
        pass
    return _resolve_bridge_ready_timeout_sec(request)


def _load_scaled_bridge_wait_ceiling_sec() -> float:
    """Ceiling for one page's bridge wait on a busy host.

    A cold client bundle has to be compiled by the dev server before the page can boot, and a busy host
    makes that take minutes (a single chunk was measured at 190s). The ceiling therefore comes from the
    dev-gate contract — the single source every other E2E budget uses — instead of a fixed 120s that cut
    the wait short exactly when the page needed the most time.
    """
    try:
        from dev_gate.contract import load_scaled_budget_sec

        return load_scaled_budget_sec(120.0, 300.0)
    except (ImportError, OSError, AttributeError, RuntimeError, ValueError):
        return 120.0


def _react_bridge_wait_timeout_sec(requested: float) -> float:
    """Ceiling for one page's bridge wait; must not undercut the cap the caller already chose."""
    try:
        from e2e_core.shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            from e2e_core.shared_ui_session import _parallel_bridge_ready_cap_sec

            return min(max(requested, 90.0), _parallel_bridge_ready_cap_sec())
    except ImportError:
        pass
    return min(max(requested, 60.0), _load_scaled_bridge_wait_ceiling_sec())


def wait_for_react_e2e_bridge(
    client: ChromeMcpClient,
    page: McpPage,
    *,
    timeout_sec: float = 90.0,
    page_url: str | None = None,
    require_attach: bool = False,
) -> dict[str, object]:
    """Wait for full React E2E bridge (attachToChat); reload-heal when clientHot was skipped at ADMIT.

    ``require_attach=True`` (shared-UI contract path) disables the softReady
    shortcut: SEARCH_POLICY/HYDRATE_PRIVATE_SEARCH_JS needs
    ``window.__MYRM_E2E_CHAT__`` methods, so reporting ready on app-layout alone
    strands the contract with a transient ``no-bridge``.

    A page that is still loading scripts is left alone until it settles or stalls: every heal reload below
    restarts all chunk downloads, which a slow dev server cannot finish before the next reload.
    """
    target_url = page_url or getattr(page, "url", None)
    deadline = time.monotonic() + _react_bridge_wait_timeout_sec(timeout_sec)
    last: dict[str, object] = {}
    polls = 0
    reload_passes = 0
    hooked_reload_passes = -1
    settled_reload_passes = -1
    max_reload_passes = 3
    ui_home = f"{get_e2e_ui_url().rstrip('/')}/"

    while time.monotonic() < deadline:
        polls += 1
        touch_wall_progress(current_node="wait_for_react_e2e_bridge")
        if polls == 1 or reload_passes != hooked_reload_passes:
            hooked_reload_passes = reload_passes
            try:
                client.evaluate(page, _BRIDGE_DIAG_HOOK_JS, timeout_sec=5.0)
            except Exception:  # noqa: BLE001 - hook is diagnostics only
                pass
        raw = client.evaluate(
            page,
            _REACT_E2E_BRIDGE_PROBE_JS,
            timeout_sec=max(5.0, min(30.0, deadline - time.monotonic())),
        )
        last = _coerce_evaluate_result(raw)
        if last.get("ready") is True:
            return last
        if polls in {1, 4, 8}:
            _log_bridge_wait_state(client, page, polls=polls, reload_passes=reload_passes, last=last)
        if reload_passes != settled_reload_passes:
            settled_reload_passes = reload_passes
            settle_outcome = _wait_for_page_load_to_settle(client, page, last, deadline=deadline)
            if settle_outcome == "stalled" and time.monotonic() < deadline:
                _trigger_attach_frontend_heal_once()
                _trigger_attach_client_warmup_once(page_url=target_url if isinstance(target_url, str) else None)
                if isinstance(target_url, str) and reload_passes < max_reload_passes:
                    reload_passes += 1
                    reload_mcp_page(
                        client,
                        page,
                        target_url=target_url,
                        timeout_ms=120_000,
                        ignore_cache=True,
                    )
                    try:
                        dismiss_blocking_modals(client, page)
                    except AssertionError:
                        pass
                    time.sleep(2.0)
            continue
        body_length = last.get("bodyLength")
        href = str(last.get("href", ""))
        if (
            isinstance(body_length, int)
            and body_length < 20
            and polls in {1, 4, 8}
            and ("127.0.0.1" in href or "localhost" in href)
        ):
            from urllib.parse import urlparse

            warm_path = urlparse(href).path or "/"
            try:
                warm_ui_route(warm_path, timeout_sec=60.0)
            except RuntimeError:
                pass
            _trigger_attach_frontend_heal_once()
        if (
            isinstance(body_length, int)
            and body_length < 20
            and polls >= 3
            and isinstance(target_url, str)
            and reload_passes < max_reload_passes
        ):
            _log_bridge_wait_state(client, page, polls=polls, reload_passes=reload_passes, last=last)
            reload_passes += 1
            reload_mcp_page(client, page, target_url=target_url, timeout_ms=120_000)
            try:
                dismiss_blocking_modals(client, page)
            except AssertionError:
                pass
            time.sleep(2.0)
            continue
        if (
            last.get("hasAppLayout") is True
            and last.get("hasInput") is True
            and last.get("fallback") is not True
            and not require_attach
            and polls >= 8
        ):
            # A soft-ready page has the shell but no bridge. Callers that later need
            # ``window.__MYRM_E2E_CHAT__`` then fail far from the cause, so leave a
            # greppable marker here: the absence of this line means the bridge really
            # attached, and its presence names the page that only looked ready.
            print(
                f"E2E_SOFT_READY_NO_BRIDGE: url={target_url} polls={polls} "
                f"hasAttach={last.get('hasAttach')} hasInput={last.get('hasInput')}",
                file=sys.stderr,
                flush=True,
            )
            return {**last, "ready": True, "softReady": True}
        if (
            last.get("hasSkeleton") is True or (last.get("hasAppLayout") is True and last.get("hasAttach") is not True)
        ) and polls in {6, 18, 36, 54}:
            _trigger_attach_frontend_heal_once()
            _trigger_attach_client_warmup_once(page_url=target_url if isinstance(target_url, str) else None)
            try:
                dismiss_blocking_modals(client, page)
            except AssertionError:
                pass
            # A page that never booted is not stale: reloading it restarts the boot. Only a booted page
            # with an old bridge object needs the cache-bypassing reload.
            if isinstance(target_url, str) and reload_passes < max_reload_passes:
                reload_passes += 1
                # Stale-Turbopack warm shells can render the app shell with an old
                # bridge object missing attachToChat — cache-bypassing reload pulls
                # the latest bundle so the contract's SEARCH_POLICY can bind.
                reload_mcp_page(
                    client,
                    page,
                    target_url=target_url,
                    timeout_ms=120_000,
                    ignore_cache=True,
                )
                time.sleep(2.0)
                continue
        should_home_heal = last.get("hasInput") is not True and polls in {8, 24, 48, 72} and isinstance(target_url, str)
        if should_home_heal and reload_passes < max_reload_passes:
            reload_passes += 1
            client.navigate(page, ui_home)
            time.sleep(3.0)
            dismiss_blocking_modals(client, page)
            client.navigate(page, target_url)
            time.sleep(2.0)
            dismiss_blocking_modals(client, page)
            continue
        should_reload = last.get("fallback") is True or (polls in {20, 40, 60, 80} and last.get("hasAttach") is not True)
        if should_reload and reload_passes < max_reload_passes and isinstance(target_url, str):
            reload_passes += 1
            reload_mcp_page(
                client,
                page,
                target_url=target_url,
                timeout_ms=120_000,
                ignore_cache=True,
            )
            dismiss_blocking_modals(client, page)
            time.sleep(2.0)
            continue
        time.sleep(0.5)

    raise AssertionError(f"React E2E bridge did not become ready: {last} diagnostics={_bridge_failure_diagnostics(client, page)}")
