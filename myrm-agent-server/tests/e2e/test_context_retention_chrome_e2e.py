"""Chrome READ E2E: context retention UI (CompactedSummaryView + pins MiniPanel)."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
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
  };
})()"""


_SUMMARY_BOOKMARKS_JS = f"""(() => {{
  const card = document.querySelector('[data-testid="compacted-summary-view"]');
  if (!card) {{
    return {{ ready: false, reason: 'no-summary-card' }};
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


_CLOSE_CONTEXT_USAGE_PANEL_JS = """(() => {
  const panel = document.querySelector('[data-testid="context-usage-panel"]');
  if (!panel) {
    return { ok: true, closed: false, reason: 'no-panel' };
  }
  document.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
  const stillOpen = document.querySelector('[data-testid="context-usage-panel"]');
  return { ok: true, closed: !stillOpen };
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


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_context_retention_summary_bookmarks_and_pins_render() -> None:
    """Seeded compacted summary, snapshot bookmarks, and pinned files render in real Chrome."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_fixture(api_url)
    chat_id = str(seeded["chat_id"])

    warm_ui_route(f"/{chat_id}")

    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        ensure_desktop_viewport(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        hydrated = wait_for_state(client, page, _CHAT_HYDRATED_JS, timeout_sec=90.0)
        assert hydrated.get("ready") is True, hydrated

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

        client.evaluate(page, _CLOSE_CONTEXT_USAGE_PANEL_JS, timeout_sec=15.0)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)

        fork_clicked = client.evaluate(page, _FORK_BOOKMARK_CLICK_JS, timeout_sec=45.0)
        assert isinstance(fork_clicked, dict) and fork_clicked.get("ok") is True, fork_clicked

        fork_state = wait_for_state(
            client,
            page,
            _fork_navigated_js(chat_id),
            timeout_sec=120.0,
        )
        assert fork_state.get("ready") is True, fork_state
