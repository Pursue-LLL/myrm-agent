"""Chrome READ E2E: context retention UI (CompactedSummaryView + pins MiniPanel)."""

from __future__ import annotations

import json
import os
import sys
import time
from collections.abc import Callable

import pytest

_LIB = os.path.join(os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib")
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_MAX_ATTEMPTS = 1
_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "open_mcp_page",
    "MUX",
    "CDP",
    "Chrome MCP",
    "Browser Orchestrator",
    "No target with given id",
    "connection reset",
    "wait_for_state",
    "Browser state did not become ready",
    "Page shell did not hydrate",
    "E2E_MUX_DAEMONS",
    "muxDaemons",
    "transport dead",
    "transport unavailable",
    "recover_mux_transport",
    "recover_mux",
    "chrome-error",
    "Runtime.evaluate",
    "CDP request timeout",
    "no-bridge",
    "PARENT_LEASE_NOT_ACTIVE",
    "E2E_LEASE_INVALID",
    "LEASE_NOT_ACTIVE",
    "E2E_RUNTIME_BINDING_FAILED",
    "private API not ready",
    "Connection refused",
    "ConnectionRefusedError",
)

_SUMMARY_NEEDLE = "E2E context retention summary fixture"
_PIN_NEEDLE = "src/context/retention.py"
_BOOKMARK_LABEL = "Before compaction E2E"


def _seed_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-context-retention-fixture",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2econtextret")
    branches_payload = http_json(
        "GET",
        f"{api_url}/api/v1/chats/{chat_id}/context/branches",
    )
    assert isinstance(branches_payload, dict)
    branches = branches_payload.get("data", branches_payload).get("branches", [])
    assert isinstance(branches, list) and len(branches) >= 1, branches_payload
    return seeded


_CHAT_HYDRATED_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgCount = store?.messages?.length ?? 0;
  const summary = store?.compactedSummary ?? '';
  return {
    ready: msgCount > 0 && typeof summary === 'string' && summary.length > 0,
    msgCount,
    summaryHead: String(summary).slice(0, 120),
    isMessagesLoaded: Boolean(store?.isMessagesLoaded),
    loadError: Boolean(store?.loadError),
    notFound: Boolean(store?.notFound),
    chatId: store?.chatId ?? null,
  };
})()"""


_CHAT_UI_READY_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const hasStore =
    Boolean(store?.isMessagesLoaded)
    && (store?.messages?.length ?? 0) > 0
    && typeof store?.compactedSummary === 'string'
    && store.compactedSummary.length > 0;
  const hasSummaryDom = Boolean(
    document.querySelector('[data-testid="compacted-summary-view"]'),
  );
  const hasChatInput = Boolean(document.querySelector('[data-chat-input]'));
  const hasMessageShell = Boolean(
    document.querySelector('[data-message-id="compacted-summary-view"]'),
  );
  const path = window.location.pathname.replace(/^\\//, '');
  return {
    ready: hasStore && (hasSummaryDom || hasMessageShell),
    hasStore,
    hasSummaryDom,
    hasMessageShell,
    hasChatInput,
    msgCount: store?.messages?.length ?? 0,
    summaryLen: (store?.compactedSummary ?? '').length,
    path,
    storeChatId: store?.chatId ?? null,
    notFound: Boolean(store?.notFound),
    loadError: Boolean(store?.loadError),
    hasMessageListSkeleton: Boolean(
      document.querySelector('[data-testid="message-list-skeleton"]'),
    ),
    hasChatRouteLoading: Boolean(
      document.querySelector('[data-testid="chat-route-loading"]'),
    ),
  };
})()"""


_SUMMARY_BOOKMARKS_JS = f"""(() => {{
  const card = document.querySelector('[data-testid="compacted-summary-view"]');
  if (!card) {{
    const store = window.__myrmChatStore?.getState?.();
    return {{
      ready: false,
      reason: 'no-summary-card',
      storeSummaryLen: (store?.compactedSummary ?? '').length,
      storeMsgCount: store?.messages?.length ?? 0,
      hasMessageShell: Boolean(
        document.querySelector('[data-message-id="compacted-summary-view"]'),
      ),
    }};
  }}
  const text = card.textContent || '';
  const summaryNeedle = {json.dumps(_SUMMARY_NEEDLE)};
  const bookmarkNeedle = {json.dumps(_BOOKMARK_LABEL)};
  const store = window.__myrmChatStore?.getState?.();
  const storeBranches = Array.isArray(store?.contextBranches) ? store.contextBranches : [];
  const storeLabels = storeBranches.map((item) => String(item?.label || '').trim());
  const hasStoreBookmark = storeLabels.some((label) => label.includes(bookmarkNeedle));
  const items = Array.from(
    document.querySelectorAll('[data-testid="compacted-summary-bookmark-item"]'),
  );
  const labels = items.map((el) => (el.textContent || '').trim());
  const hasDomBookmark = labels.some((label) => label.includes(bookmarkNeedle));
  const hasBookmark = hasDomBookmark;
  const bookmarksSection = document.querySelector('[data-testid="compacted-summary-bookmarks"]');
  const bookmarksState = bookmarksSection?.getAttribute('data-bookmarks-state') ?? 'missing';
  return {{
    ready: text.includes(summaryNeedle) && hasBookmark,
    hasCard: true,
    hasSummaryText: text.includes(summaryNeedle),
    bookmarkCount: items.length,
    bookmarkLabels: labels,
    storeBranchCount: storeBranches.length,
    storeBranchLabels: storeLabels,
    hasStoreBookmark,
    bookmarksState,
  }};
}})()"""


_ROUTE_SEGMENT_CLEARED_JS = """(() => ({
  ready: !document.querySelector('[data-testid="chat-route-loading"]'),
  hasChatRouteLoading: Boolean(
    document.querySelector('[data-testid="chat-route-loading"]'),
  ),
}))()"""


_OPEN_CONTEXT_USAGE_PANEL_JS = """(() => {
  const indicator = document.querySelector('[data-testid="context-usage-indicator"]');
  if (!indicator) {
    return { ok: false, reason: 'no-indicator' };
  }
  indicator.click();
  const panel = document.querySelector('[data-testid="context-usage-panel"]');
  return { ok: true, panelOpen: Boolean(panel) };
})()"""


_PINS_PANEL_JS = f"""(() => {{
  const indicator = document.querySelector('[data-testid="context-usage-indicator"]');
  let panel = document.querySelector('[data-testid="context-usage-panel"]');
  if (indicator && !panel) {{
    indicator.click();
    panel = document.querySelector('[data-testid="context-usage-panel"]');
  }}
  const pinNeedle = {json.dumps(_PIN_NEEDLE)};
  const store = window.__myrmChatStore?.getState?.();
  const storePins = Array.isArray(store?.contextPinnedFiles) ? store.contextPinnedFiles : [];
  const items = Array.from(document.querySelectorAll('[data-testid="context-pin-item"]'));
  const paths = items.map((el) => el.getAttribute('data-pin-path') || '');
  const hasStorePin = storePins.some((path) => String(path).includes(pinNeedle));
  const hasDomPin = paths.some((path) => path.includes(pinNeedle));
  const hasPin = hasDomPin;
  return {{
    ready: Boolean(panel) && hasPin,
    hasPanel: Boolean(panel),
    hasIndicator: Boolean(document.querySelector('[data-testid="context-usage-indicator"]')),
    pinPaths: paths,
    storePinPaths: storePins,
    hasStorePin,
  }};
}})()"""


_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""


def _await_attach_chat(
    client: object,
    page: object,
    chat_id: str,
    *,
    timeout_sec: float = 180.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        remaining = max(5.0, deadline - time.monotonic())
        try:
            raw = client.evaluate(  # type: ignore[attr-defined]
                page,
                _attach_chat_probe(chat_id),
                timeout_sec=min(45.0, _attach_eval_timeout_sec(), remaining),
            )
        except RuntimeError as exc:
            if "CDP request timeout" not in str(exc) and "Runtime.evaluate" not in str(exc):
                raise
            last = {"err": str(exc)}
            time.sleep(2.0)
            continue
        if isinstance(raw, dict) and raw.get("ok") is True:
            return raw
        last = raw if isinstance(raw, dict) else {"value": raw}
        time.sleep(2.0)
    raise AssertionError(f"attachToChat did not become ready: {last}")


def _attach_eval_timeout_sec() -> float:
    try:
        from e2e_core.shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            return 150.0
    except ImportError:
        pass
    return 120.0


def _attach_chat_probe(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) {{
    return {{ ok: false, err: 'no-bridge' }};
  }}
  await bridge.attachToChat({chat_id_json});
  const snap = bridge.turnSnapshot?.() ?? {{}};
  const store = window.__myrmChatStore?.getState?.();
  const summary = store?.compactedSummary ?? '';
  const hasSummaryDom = Boolean(
    document.querySelector('[data-testid="compacted-summary-view"]')
    || document.querySelector('[data-message-id="compacted-summary-view"]'),
  );
  return {{
    ok:
      snap.chatId === {chat_id_json}
      && (snap.userCount ?? 0) >= 1
      && typeof summary === 'string'
      && summary.length > 0
      && Boolean(store?.isMessagesLoaded)
      && !Boolean(store?.notFound)
      && !Boolean(store?.loadError),
    snap,
    summaryHead: String(summary).slice(0, 120),
    hasSummaryDom,
    isMessagesLoaded: Boolean(store?.isMessagesLoaded),
    loadError: Boolean(store?.loadError),
    notFound: Boolean(store?.notFound),
  }};
}})()"""


def _bridge_ready_timeout_sec() -> float:
    try:
        from e2e_core.shared_ui_hydrate import parallel_shared_ui_hydrate_queue_enabled

        if parallel_shared_ui_hydrate_queue_enabled():
            return 180.0
    except ImportError:
        pass
    return 90.0


def _force_mux_heal_before_retry() -> None:
    _require_e2e_cdp_ready(budget_sec=45.0)
    from mux.attach_force_restart import force_mux_attach_restart_scoped

    force_mux_attach_restart_scoped(reason="context retention chrome outer retry")
    time.sleep(3.0)


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    if "E2E_USER_CLOSED_TAB" in text:
        return False
    if "E2E_ORCHESTRATOR_LEASE_DENIED" in text or "LEASE_DENIED" in text:
        return False
    non_retryable = (
        "React E2E bridge did not become ready",
        "attachToChat did not become ready",
        "E2E_RUNTIME_BINDING_FAILED",
        "attach-dom-not-ready",
        "hasSummaryDom",
        "hasMessageListSkeleton",
    )
    if any(marker in text for marker in non_retryable):
        return False
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


_CLOSE_CONTEXT_USAGE_PANEL_JS = """(() => {
  const panel = document.querySelector('[data-testid="context-usage-panel"]');
  if (!panel) {
    return { ok: true, closed: false, reason: 'no-panel' };
  }
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  const stillOpen = document.querySelector('[data-testid="context-usage-panel"]');
  return { ok: true, closed: !stillOpen };
})()"""


_BREAKDOWN_PANEL_JS = """(() => {
  const indicator = document.querySelector('[data-testid="context-usage-indicator"]');
  if (indicator) {
    indicator.click();
  }
  const breakdown = document.querySelector('[data-testid="context-budget-breakdown"]');
  const store = window.__myrmChatStore?.getState?.();
  let budget = null;
  const msgs = Array.isArray(store?.messages) ? store.messages : [];
  for (let i = msgs.length - 1; i >= 0; i -= 1) {
    const msg = msgs[i];
    if (msg?.role === 'assistant' && msg?.contextBudget) {
      budget = msg.contextBudget;
      break;
    }
  }
  const tools = Number(budget?.bound_tools_overhead_tokens ?? 0);
  const messagesEst = Number(budget?.messages_estimated_tokens ?? 0);
  return {
    ready: Boolean(breakdown) && tools > 0 && messagesEst > 0,
    hasBreakdown: Boolean(breakdown),
    toolsOverhead: tools,
    messagesEst,
  };
})()"""


_FORK_BOOKMARK_CLICK_JS = """(async () => {
  let clickedBtn = null;
  for (let attempt = 0; attempt < 48; attempt += 1) {
    const store = window.__myrmChatStore?.getState?.();
    if (store?.loading) {
      await new Promise((resolve) => setTimeout(resolve, 250));
      continue;
    }
    const btn = document.querySelector('[data-testid="compacted-summary-bookmark-fork"]');
    if (!btn || btn.disabled) {
      await new Promise((resolve) => setTimeout(resolve, 250));
      continue;
    }
    if (!clickedBtn) {
      btn.scrollIntoView({ block: 'center', inline: 'nearest' });
      btn.focus();
      btn.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true }));
      btn.dispatchEvent(new PointerEvent('pointerup', { bubbles: true }));
      btn.dispatchEvent(new MouseEvent('click', { bubbles: true, cancelable: true }));
      clickedBtn = btn;
    }
    const diag = window.__MYRM_CONTEXT_BRANCH_FORK_DIAG__;
    if (diag?.phase === 'start' || diag?.phase === 'api-ok' || diag?.phase === 'navigate') {
      return { ok: true, diag, label: (clickedBtn.textContent || '').trim(), attempts: attempt + 1 };
    }
    if (diag?.phase === 'api-error' || diag?.phase === 'blocked-loading') {
      return { ok: false, reason: diag.phase, diag, attempts: attempt + 1 };
    }
    await new Promise((resolve) => setTimeout(resolve, 250));
  }
  return {
    ok: false,
    reason: clickedBtn ? 'fork-click-not-acknowledged' : 'no-fork-button',
    diag: window.__MYRM_CONTEXT_BRANCH_FORK_DIAG__ ?? null,
    label: clickedBtn ? (clickedBtn.textContent || '').trim() : '',
  };
})()"""


_FORK_BOOKMARK_READY_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const loading = Boolean(store?.loading);
  const btn = document.querySelector('[data-testid="compacted-summary-bookmark-fork"]');
  return {
    ready: !loading && Boolean(btn) && !btn.disabled,
    loading,
    hasButton: Boolean(btn),
    disabled: Boolean(btn?.disabled),
  };
})()"""


def _fork_navigated_js(parent_chat_id: str) -> str:
    return f"""(() => {{
  const parentChatId = {json.dumps(parent_chat_id)};
  const path = window.location.pathname.replace(/^\\//, '');
  const store = window.__myrmChatStore?.getState?.();
  const activeChatId = String(store?.chatId || '');
  const msgCount = Array.isArray(store?.messages) ? store.messages.length : 0;
  const ws = window.__myrmWorkspaceStore?.getState?.();
  const panes = Array.isArray(ws?.panes) ? ws.panes : [];
  const paneChatIds = panes.map((pane) => String(pane?.chatId || ''));
  const forkDiag = window.__MYRM_CONTEXT_BRANCH_FORK_DIAG__ ?? null;
  return {{
    ready:
      path !== parentChatId
      && path.length > 0
      && activeChatId === path
      && msgCount > 0,
    path,
    parentChatId,
    activeChatId,
    paneChatIds,
    msgCount,
    forkDiag,
  }};
}})()"""


def _ensure_react_bridge_on_home(
    client: object,
    page: object,
    *,
    ui_url: str,
) -> dict[str, object]:
    """Compile + hydrate Turbopack client on `/` before deep-linking seeded chat routes."""
    home_url = f"{ui_url.rstrip('/')}/"
    dismiss_blocking_modals(client, page)  # type: ignore[arg-type]
    client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)  # type: ignore[attr-defined]
    bridge_ready = wait_for_react_e2e_bridge(
        client,  # type: ignore[arg-type]
        page,  # type: ignore[arg-type]
        timeout_sec=min(90.0, _bridge_ready_timeout_sec()),
        page_url=home_url,
    )
    assert bridge_ready.get("ready") is True, json.dumps(bridge_ready, ensure_ascii=False)
    return bridge_ready


def _run_retention_assertions(api_url: str, ui_url: str, *, warm_route: bool = True) -> None:
    seeded = _seed_fixture(api_url)
    chat_id = str(seeded["chat_id"])
    chat_url = f"{ui_url.rstrip('/')}/{chat_id}"
    home_url = f"{ui_url.rstrip('/')}/"
    if warm_route:
        warm_ui_route("/")
        warm_ui_route(f"/{chat_id}")

    with open_mcp_page(home_url, timeout_ms=120_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        _ensure_react_bridge_on_home(client, page, ui_url=ui_url)

        client.navigate(page, chat_url)  # type: ignore[attr-defined]
        time.sleep(1.5)
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        attached = _await_attach_chat(client, page, chat_id, timeout_sec=90.0)
        assert attached.get("ok") is True, attached

        dismiss_blocking_modals(client, page)

        chat_ui_probe = wait_for_state(
            client,
            page,
            _CHAT_UI_READY_JS,
            timeout_sec=30.0,
        )
        if chat_ui_probe.get("ready") is not True and chat_ui_probe.get("hasMessageListSkeleton") is True:
            reload_mcp_page(client, page, target_url=chat_url, timeout_ms=60_000)
            dismiss_blocking_modals(client, page)
            client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
            attached = _await_attach_chat(client, page, chat_id, timeout_sec=60.0)
            assert attached.get("ok") is True, attached

        route_ready = wait_for_state(
            client,
            page,
            _ROUTE_SEGMENT_CLEARED_JS,
            timeout_sec=45.0,
        )
        assert route_ready.get("ready") is True, route_ready

        hydrated = wait_for_state(client, page, _CHAT_HYDRATED_JS, timeout_sec=45.0)
        assert hydrated.get("ready") is True, hydrated

        chat_ui = wait_for_state(
            client,
            page,
            _CHAT_UI_READY_JS,
            timeout_sec=90.0,
        )
        assert chat_ui.get("ready") is True, chat_ui

        summary_state = wait_for_state(
            client,
            page,
            _SUMMARY_BOOKMARKS_JS,
            timeout_sec=60.0,
        )
        assert summary_state.get("ready") is True, summary_state

        opened = client.evaluate(page, _OPEN_CONTEXT_USAGE_PANEL_JS, timeout_sec=15.0)
        assert isinstance(opened, dict) and opened.get("ok") is True, opened

        pin_state = wait_for_state(client, page, _PINS_PANEL_JS, timeout_sec=45.0)
        assert pin_state.get("ready") is True, pin_state

        breakdown_state = wait_for_state(
            client,
            page,
            _BREAKDOWN_PANEL_JS,
            timeout_sec=45.0,
        )
        assert breakdown_state.get("ready") is True, breakdown_state

        client.evaluate(page, _CLOSE_CONTEXT_USAGE_PANEL_JS, timeout_sec=15.0)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        fork_clicked = client.evaluate(page, _FORK_BOOKMARK_CLICK_JS, timeout_sec=45.0)
        assert isinstance(fork_clicked, dict) and fork_clicked.get("ok") is True, fork_clicked

        fork_state = wait_for_state(
            client,
            page,
            _fork_navigated_js(chat_id),
            timeout_sec=60.0,
        )
        assert fork_state.get("ready") is True, fork_state


def _run_with_transport_retry(
    runner: Callable[..., None],
    api_url: str,
    ui_url: str,
) -> None:
    last_error: BaseException | None = None
    resolved_api = api_url
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            resolved_api = get_e2e_api_url()
            runner(resolved_api, ui_url, warm_route=(attempt == 1))
            return
        except Exception as exc:
            last_error = exc
            if attempt >= _MAX_ATTEMPTS or not _is_transport_retryable(exc):
                raise
            _force_mux_heal_before_retry()
    if last_error is not None:
        raise last_error


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_context_retention_summary_bookmarks_and_pins_render() -> None:
    """Seeded compacted summary, snapshot bookmarks, and pinned files render in real Chrome."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    _run_with_transport_retry(_run_retention_assertions, api_url, ui_url)
