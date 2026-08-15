"""Chrome MCP E2E: Lean Co-Pilot full user flows (run chip, advisor Tier-0, quote ask, mobile view-full)."""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_CHAT_SHELL_READY_JS = """(() => {
  const state = window.__MYRM_E2E_CHAT__?.getChatShellState?.() ?? {};
  return {
    ready:
      state.isMessagesLoaded === true
      && state.notFound !== true
      && state.loadError !== true,
    state,
  };
})()"""

_COPILOT_CHIP_READY_JS = """(() => {
  const chip = document.querySelector('[data-testid="copilot-run-status-chip"]');
  const headline = document.querySelector('[data-testid="copilot-run-headline"]');
  const ask = document.querySelector('[data-testid="copilot-run-ask-button"]');
  const text = (headline?.textContent || '').trim();
  return {
    ready: !!chip && !!ask && text.includes('web_search'),
    headline: text,
  };
})()"""

_EXPAND_RUN_STEPS_JS = """(() => {
  const toggle = document.querySelector('[data-testid="copilot-run-headline-toggle"]');
  if (!toggle) return { ok: false, err: 'missing-toggle' };
  toggle.click();
  return { ok: true };
})()"""

_RUN_STEPS_READY_JS = """(() => {
  const steps = document.querySelector('[data-testid="copilot-run-steps"]');
  const text = steps?.textContent || '';
  return { ready: !!steps && text.includes('web_search'), text: text.slice(0, 120) };
})()"""

_OPEN_ADVISOR_JS = """(() => {
  const ask = document.querySelector('[data-testid="copilot-run-ask-button"]');
  if (!ask) return { ok: false, err: 'missing-ask' };
  ask.click();
  return { ok: true };
})()"""

_ADVISOR_PANEL_OPEN_JS = """(() => {
  const panel = document.querySelector('[data-testid="copilot-advisor-panel"]');
  const open = panel?.getAttribute('data-state') === 'open' || panel?.offsetParent !== null;
  return { ready: !!panel && open };
})()"""

_TIER0_ASK_JS = """(() => {
  const input = document.querySelector('[data-testid="copilot-advisor-input"]');
  const send = document.querySelector('[data-testid="copilot-advisor-send"]');
  if (!input || !send) return { ok: false, err: 'missing-advisor-controls' };
  const setter = Object.getOwnPropertyDescriptor(window.HTMLTextAreaElement.prototype, 'value')?.set;
  if (!setter) return { ok: false, err: 'setter-not-found' };
  setter.call(input, '现在在干嘛？');
  input.dispatchEvent(new Event('input', { bubbles: true }));
  send.click();
  return { ok: true };
})()"""

_TIER0_REPLY_READY_JS = """(() => {
  const box = document.querySelector('[data-testid="copilot-advisor-messages"]');
  const text = box?.textContent || '';
  return {
    ready: text.includes('步骤 1') || text.includes('Step 1'),
    sample: text.slice(0, 200),
  };
})()"""

_SET_CHAT_LOADING_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setLoading) return { ok: false, err: 'missing-setLoading' };
  bridge.setLoading(true);
  return { ok: true, loading: bridge.getChatShellState?.().loading === true };
})()"""

_SELECTION_SNIPPET_READY_JS = """(() => {
  const needle = 'connection refused';
  const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
  let node = walker.nextNode();
  while (node) {
    const value = node.textContent || '';
    if (value.includes(needle) && node.parentElement?.closest?.('[data-message-id]')) {
      return { ready: true };
    }
    node = walker.nextNode();
  }
  return { ready: false };
})()"""

_SELECT_AND_CLICK_QUOTE_JS = """(async () => {
  window.__MYRM_E2E_CHAT__?.setLoading?.(true);
  const needle = 'connection refused';
  const waitFrame = () =>
    new Promise((r) => {
      const t = setTimeout(() => r(), 16);
      requestAnimationFrame(() => { clearTimeout(t); r(); });
    });
  const findTarget = () => {
    const walker = document.createTreeWalker(document.body, NodeFilter.SHOW_TEXT);
    let node = walker.nextNode();
    while (node) {
      const value = node.textContent || '';
      const msgContainer = node.parentElement?.closest?.('[data-message-id]');
      if (value.includes(needle) && msgContainer) {
        return { node, msgContainer };
      }
      node = walker.nextNode();
    }
    return null;
  };
  const selectAndNotify = (target) => {
    const range = document.createRange();
    range.selectNodeContents(target.node);
    const selection = window.getSelection();
    selection?.removeAllRanges();
    selection?.addRange(range);
    target.msgContainer.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
  };
  let target = findTarget();
  if (!target) {
    return {
      ok: false,
      err: 'snippet-not-found',
      portal: !!document.getElementById('quote-toolbar-portal'),
      msgIdCount: document.querySelectorAll('[data-message-id]').length,
    };
  }
  selectAndNotify(target);
  const diag = [];
  for (let i = 0; i < 180; i++) {
    await waitFrame();
    const btn = document.querySelector('[data-testid="quote-toolbar-advisor-ask"]');
    if (btn) {
      btn.click();
      const sel = window.getSelection();
      return { ok: true, clicked: true, waitedFrames: i, selText: sel?.toString?.().slice(0, 40) || '' };
    }
    const sel = window.getSelection();
    if (!target || sel?.isCollapsed || !target.msgContainer.isConnected) {
      if (i % 5 === 0) {
        diag.push({
          i,
          collapsed: sel?.isCollapsed ?? null,
          disconnected: !target?.msgContainer?.isConnected,
          portal: !!document.getElementById('quote-toolbar-portal'),
        });
      }
      const next = findTarget();
      if (next) {
        target = next;
        selectAndNotify(target);
      }
    }
  }
  const sel = window.getSelection();
  const anchorEl = sel?.anchorNode?.nodeType === 3 ? sel.anchorNode.parentElement : sel?.anchorNode;
  return {
    ok: false,
    err: 'toolbar-timeout',
    diag,
    selText: sel?.toString?.().slice(0, 40) || '',
    selCollapsed: sel?.isCollapsed,
    anchorNodeType: sel?.anchorNode?.nodeType ?? -1,
    anchorTag: anchorEl?.tagName ?? '',
    anchorInMsg: !!anchorEl?.closest?.('[data-message-id]'),
    portal: !!document.getElementById('quote-toolbar-portal'),
    quoteBtn: !!document.querySelector('[data-testid="quote-toolbar-advisor-ask"]'),
    loading: window.__MYRM_E2E_CHAT__?.getChatShellState?.().loading,
    msgIdCount: document.querySelectorAll('[data-message-id]').length,
  };
})()"""

_SELECTION_ADVISOR_USER_MSG_JS = """(() => {
  const box = document.querySelector('[data-testid="copilot-advisor-messages"]');
  const text = box?.textContent || '';
  return {
    ready: text.includes('解释选中内容') || text.includes('Explain selection'),
    sample: text.slice(0, 240),
  };
})()"""

_MOBILE_VIEWPORT_JS = """(() => {
  try { window.resizeTo(390, 844); } catch { /* ignore */ }
  return { width: window.innerWidth, height: window.innerHeight };
})()"""

_SET_MOBILE_LOADING_JS = """(() => ({
  ready: !!(window.__MYRM_E2E_MOBILE_CC__?.setLoading),
  ok: false,
  err: window.__MYRM_E2E_MOBILE_CC__?.setLoading ? undefined : 'missing-mobile-bridge',
}))()"""

_MOBILE_LOADING_APPLY_JS = """(() => {
  const bridge = window.__MYRM_E2E_MOBILE_CC__;
  if (!bridge?.setLoading) return { ok: false, err: 'missing-mobile-bridge' };
  bridge.setLoading(true);
  return { ok: true };
})()"""

_MOBILE_VIEW_FULL_READY_JS = """(() => ({
  ready: !!document.querySelector('[data-testid="mobile-command-view-full-conversation"]'),
  pathname: location.pathname,
}))()"""

_CLICK_MOBILE_VIEW_FULL_JS = """(() => {
  const link = document.querySelector('[data-testid="mobile-command-view-full-conversation"]');
  if (!link) return { ok: false, err: 'missing-link' };
  link.click();
  return { ok: true };
})()"""


def _seed_copilot_fixture(api_url: str) -> dict[str, str]:
    seeded = http_json("POST", f"{api_url}/api/v1/chats/test/seed-copilot-fixture")
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2ecopilot")
    return {
        "chat_id": chat_id,
        "ui_path": str(seeded.get("ui_path") or ""),
        "mobile_path": str(seeded.get("mobile_path") or ""),
    }


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_copilot_desktop_and_mobile_full_flows() -> None:
    """Single SHPOIB bootstrap: desktop chip/advisor/quote + mobile view-full."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)
    seeded = _seed_copilot_fixture(api_url)
    chat_id = seeded["chat_id"]
    mobile_path = seeded["mobile_path"]

    warm_ui_route(f"/{chat_id}")
    warm_ui_route(mobile_path)
    with open_mcp_page(f"{ui_url}/{chat_id}") as (client, page):
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=10.0)
        ensure_desktop_viewport(client, page)
        shell = wait_for_state(client, page, _CHAT_SHELL_READY_JS, timeout_sec=120.0)
        assert shell.get("ready") is True, shell

        chip = wait_for_state(client, page, _COPILOT_CHIP_READY_JS, timeout_sec=60.0)
        assert chip.get("ready") is True, chip

        expanded = client.evaluate(page, _EXPAND_RUN_STEPS_JS, timeout_sec=10.0)
        assert isinstance(expanded, dict) and expanded.get("ok") is True, expanded
        steps = wait_for_state(client, page, _RUN_STEPS_READY_JS, timeout_sec=30.0)
        assert steps.get("ready") is True, steps

        opened = client.evaluate(page, _OPEN_ADVISOR_JS, timeout_sec=10.0)
        assert isinstance(opened, dict) and opened.get("ok") is True, opened
        panel = wait_for_state(client, page, _ADVISOR_PANEL_OPEN_JS, timeout_sec=30.0)
        assert panel.get("ready") is True, panel

        asked = client.evaluate(page, _TIER0_ASK_JS, timeout_sec=10.0)
        assert isinstance(asked, dict) and asked.get("ok") is True, asked
        tier0 = wait_for_state(client, page, _TIER0_REPLY_READY_JS, timeout_sec=60.0)
        assert tier0.get("ready") is True, tier0

        set_loading = client.evaluate(page, _SET_CHAT_LOADING_JS, timeout_sec=10.0)
        assert isinstance(set_loading, dict) and set_loading.get("ok") is True, set_loading
        snippet_ready = wait_for_state(client, page, _SELECTION_SNIPPET_READY_JS, timeout_sec=30.0)
        assert snippet_ready.get("ready") is True, snippet_ready
        quote_clicked = client.evaluate(page, _SELECT_AND_CLICK_QUOTE_JS, timeout_sec=30.0)
        assert isinstance(quote_clicked, dict) and quote_clicked.get("ok") is True, quote_clicked
        selection_msg = wait_for_state(
            client,
            page,
            _SELECTION_ADVISOR_USER_MSG_JS,
            timeout_sec=60.0,
        )
        assert selection_msg.get("ready") is True, selection_msg

        client.navigate(page, f"{ui_url}{mobile_path}", timeout_ms=90_000)
        dismiss_blocking_modals(client, page)
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=10.0)
        client.evaluate(page, _MOBILE_VIEWPORT_JS, timeout_sec=5.0)
        mobile_bridge = wait_for_state(client, page, _SET_MOBILE_LOADING_JS, timeout_sec=30.0)
        assert mobile_bridge.get("ready") is True, mobile_bridge
        set_mobile = client.evaluate(page, _MOBILE_LOADING_APPLY_JS, timeout_sec=10.0)
        assert isinstance(set_mobile, dict) and set_mobile.get("ok") is True, set_mobile
        ready = wait_for_state(client, page, _MOBILE_VIEW_FULL_READY_JS, timeout_sec=60.0)
        assert ready.get("ready") is True, ready
        clicked = client.evaluate(page, _CLICK_MOBILE_VIEW_FULL_JS, timeout_sec=10.0)
        assert isinstance(clicked, dict) and clicked.get("ok") is True, clicked
        navigated = wait_for_state(
            client,
            page,
            f"""(() => ({{
              ready: location.pathname === {json.dumps(f"/{chat_id}")},
              pathname: location.pathname,
            }}))()""",
            timeout_sec=60.0,
        )
        assert navigated.get("ready") is True, navigated
