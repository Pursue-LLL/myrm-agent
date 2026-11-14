"""Real Chrome MCP E2E for the Research Studio workbench.

Prerequisites:
  ./myrm-dev ready --chrome

Covers:
  T1 - /research page loads with substantial content
  T2 - Resource pool displays empty state with correct UI elements
  T3 - Resource pool actions (Wiki, Upload) buttons present
  T4 - Layout follows the research area's own width: three panes with drag handles when wide, one pane under tabs
       when narrow
  T5 - Metadata title correct
  T6 - The chat composer sits inside the chat pane instead of spanning the side panes
  T7 - In a phone-width frame the pane tabs switch which single pane is shown, without horizontal overflow
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_ui_url,
    open_mcp_page,
    wait_for_state,
)

RESEARCH_URL = f"{get_e2e_ui_url()}/research"

_DISMISS_MIGRATION_JS = """(() => {
  localStorage.setItem('myrm.proactive.dismissed.migration-discovery', 'forever');
  return true;
})()"""

# One probe for any document: the page itself, or the phone-sized frame that hosts a second copy of the app.
_LAYOUT_PROBE_FN = """(doc, win) => {
  const bodyText = doc.body.innerText || '';
  const title = doc.title;

  const resourcePool = bodyText.includes('资料池') || bodyText.includes('Resources');
  const emptyState = bodyText.includes('暂无研究资料')
    || bodyText.includes('No resources added yet');
  const wikiBtn = bodyText.includes('从知识库') || bodyText.includes('From Wiki');
  const uploadBtn = bodyText.includes('上传') || bodyText.includes('Upload');
  const selectedCount = bodyText.includes('已选') || bodyText.includes('selected');

  const paneIds = ['resources', 'chat', 'output'];
  const isShown = (el) => el.getClientRects().length > 0;
  const visiblePanes = paneIds.filter((id) => {
    const pane = doc.getElementById('research-pane-' + id);
    return pane !== null && isShown(pane);
  });
  const chatPane = doc.getElementById('research-pane-chat');
  const rowWidth = chatPane ? chatPane.parentElement.clientWidth : 0;
  // Mirrors the layout's `@6xl` container query: three panes from 72rem of research-area width.
  const wide = rowWidth >= 72 * parseFloat(win.getComputedStyle(doc.documentElement).fontSize);
  const dragHandles = Array.from(doc.querySelectorAll('[class*="cursor-col-resize"]')).filter(isShown);
  const tabs = Array.from(doc.querySelectorAll('[role="tab"]')).filter(isShown);
  const tabTexts = tabs.map((t) => t.textContent || '');
  const selectedPane = tabs
    .filter((t) => t.getAttribute('aria-selected') === 'true')
    .map((t) => (t.getAttribute('aria-controls') || '').replace('research-pane-', ''));
  const composer = chatPane ? chatPane.querySelector('textarea') : null;
  let composerInChatPane = false;
  if (composer !== null && chatPane !== null && isShown(chatPane)) {
    const paneRect = chatPane.getBoundingClientRect();
    const composerRect = composer.getBoundingClientRect();
    composerInChatPane = composerRect.left >= paneRect.left && composerRect.right <= paneRect.right;
  }
  const root = doc.documentElement;

  return {
    ready: (resourcePool || emptyState) && title.includes('Research') && composer !== null,
    title,
    resourcePool,
    emptyState,
    wikiBtn,
    uploadBtn,
    selectedCount,
    wide,
    rowWidth,
    visiblePanes,
    selectedPane,
    composerInChatPane,
    dragHandleCount: dragHandles.length,
    tabCount: tabs.length,
    tabTexts,
    pageOverflowsX: root.scrollWidth > root.clientWidth,
    bodyLength: bodyText.length,
    url: win.location.href,
    viewportWidth: win.innerWidth,
  };
}"""

_LAYOUT_PROBE_JS = f"({_LAYOUT_PROBE_FN})(document, window)"

# A phone-sized same-origin frame gives the app a real 390px viewport (window.resizeTo is a no-op in this Chrome), so
# the research area is genuinely narrow. The frame is a second full app load: on a cold dev server it can take a minute.
_PHONE_FRAME_WIDTH = 390
_PHONE_FRAME_PROBE_JS = (
    """(() => {
  let frame = document.getElementById('e2e-phone-frame');
  if (!frame) {
    frame = document.createElement('iframe');
    frame.id = 'e2e-phone-frame';
    frame.style.cssText = 'position:fixed;left:0;top:0;width:390px;height:844px;border:0;z-index:2147483647;background:#fff';
    frame.src = location.origin + '/research';
    document.body.appendChild(frame);
    return { ready: false, stage: 'loading' };
  }
  let win;
  let doc;
  try {
    win = frame.contentWindow;
    doc = win.document;
  } catch (err) {
    return { ready: false, stage: 'unreachable' };
  }
  if (!doc.body || win.location.pathname !== '/research') {
    return { ready: false, stage: 'navigating', path: win.location.pathname };
  }
  return (__PROBE__)(doc, win);
})()"""
).replace("__PROBE__", _LAYOUT_PROBE_FN)

# Radix tabs activate on pointerdown, so a bare click() would not switch them; the events are built from the frame's
# own window so the app sees same-realm events.
_PHONE_FRAME_SELECT_PANE_JS = """(() => {
  const frame = document.getElementById('e2e-phone-frame');
  const win = frame.contentWindow;
  const trigger = win.document.querySelector('[role="tab"][aria-controls="research-pane-__PANE__"]');
  if (!trigger) {
    return { ready: false, reason: 'no-tab' };
  }
  if (trigger.getAttribute('aria-selected') !== 'true') {
    const opts = { bubbles: true, cancelable: true, composed: true, button: 0, detail: 1, view: win };
    trigger.dispatchEvent(new win.PointerEvent('pointerdown', { ...opts, pointerId: 1, isPrimary: true }));
    trigger.dispatchEvent(new win.MouseEvent('mousedown', opts));
    trigger.dispatchEvent(new win.PointerEvent('pointerup', { ...opts, pointerId: 1, isPrimary: true }));
    trigger.dispatchEvent(new win.MouseEvent('mouseup', opts));
    trigger.dispatchEvent(new win.MouseEvent('click', opts));
  }
  return { ready: true };
})()"""

_REMOVE_PHONE_FRAME_JS = """(() => {
  document.getElementById('e2e-phone-frame')?.remove();
  return { ready: true };
})()"""


def _pane_shown_js(pane: str) -> str:
    """Probe that is ready once the phone frame shows exactly ``pane`` and its tab is the selected one."""
    return f"""(() => {{
  const state = {_PHONE_FRAME_PROBE_JS};
  if (state.stage) {{
    return state;
  }}
  return {{
    ...state,
    ready: state.visiblePanes.length === 1 && state.visiblePanes[0] === {json.dumps(pane)}
      && state.selectedPane.length === 1 && state.selectedPane[0] === {json.dumps(pane)},
  }};
}})()"""


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_research_studio_full_chrome_e2e() -> None:
    """Research Studio: page load, three-column layout, resource pool UI."""
    with open_mcp_page(RESEARCH_URL) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=5.0)

        state = wait_for_state(client, page, _LAYOUT_PROBE_JS, timeout_sec=45.0)
        layout = {key: state.get(key) for key in ("viewportWidth", "rowWidth", "wide", "visiblePanes", "tabCount")}
        print(f"E2E_RESEARCH_LAYOUT: {json.dumps(layout)}", flush=True)

        # T5: Metadata title
        assert "Research" in str(state.get("title", "")), f"Page title should contain 'Research': {state.get('title')}"
        assert state.get("url", "").endswith("/research"), f"URL should end with /research: {state.get('url')}"

        # T1: Three-column layout renders
        assert isinstance(state.get("bodyLength"), int) and state["bodyLength"] > 50, (
            f"Page body should have substantial content: {state.get('bodyLength')}"
        )

        # T2: Empty state or resource pool header visible
        assert state.get("resourcePool") is True or state.get("emptyState") is True, (
            "Resource pool header or empty state should be visible"
        )

        # T3: Action buttons present
        assert state.get("wikiBtn") is True, "Wiki add button should be present"
        assert state.get("uploadBtn") is True, "Upload button should be present"
        assert state.get("selectedCount") is True, "Selected count should be visible"

        # T4: Layout follows the research area's own width, not the viewport
        viewport_w = state.get("viewportWidth", 0)
        if state.get("wide") is True:
            assert state.get("visiblePanes") == ["resources", "chat", "output"], (
                f"Wide area ({state.get('rowWidth')}px of {viewport_w}px viewport) should show all three panes: "
                f"{state.get('visiblePanes')}"
            )
            assert state.get("dragHandleCount") == 2, f"Wide area should show 2 drag handles: {state.get('dragHandleCount')}"
            assert state.get("tabCount") == 0, f"Wide area should hide the pane tabs: {state.get('tabTexts')}"
        else:
            assert len(state.get("visiblePanes", [])) == 1, (
                f"Narrow area ({state.get('rowWidth')}px of {viewport_w}px viewport) should show one pane: "
                f"{state.get('visiblePanes')}"
            )
            assert state.get("tabCount") == 3, f"Narrow area should show three pane tabs: {state.get('tabTexts')}"
            assert state.get("dragHandleCount") == 0, f"Narrow area should hide the drag handles: {state.get('dragHandleCount')}"

        # T6: The composer belongs to the chat pane (only measurable while that pane is on screen)
        if "chat" in state.get("visiblePanes", []):
            assert state.get("composerInChatPane") is True, "Chat composer should sit inside the chat pane"


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_research_studio_phone_frame_tabs_switch_panes_chrome_e2e() -> None:
    """At phone width one pane shows under three tabs, each tab shows its own pane, and the page never scrolls sideways."""
    with open_mcp_page(RESEARCH_URL) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=5.0)
        dismiss_blocking_modals(client, page)

        phone = wait_for_state(client, page, _PHONE_FRAME_PROBE_JS, timeout_sec=_warm_ui_parallel_wait_sec(240.0))
        layout = {
            key: phone.get(key) for key in ("viewportWidth", "rowWidth", "wide", "visiblePanes", "selectedPane", "tabCount")
        }
        print(f"E2E_RESEARCH_PHONE_LAYOUT: {json.dumps(layout)}", flush=True)

        assert phone.get("viewportWidth") == _PHONE_FRAME_WIDTH, phone
        assert phone.get("wide") is False, f"A phone-width research area must use the single-pane layout: {phone}"
        assert len(phone.get("visiblePanes", [])) == 1, f"Phone width should show one pane: {phone.get('visiblePanes')}"
        assert phone.get("tabCount") == 3, f"Phone width should show three pane tabs: {phone.get('tabTexts')}"
        assert phone.get("selectedPane") == phone.get("visiblePanes"), f"The shown pane must be the selected tab's: {phone}"
        assert phone.get("dragHandleCount") == 0, f"Phone width should hide the drag handles: {phone.get('dragHandleCount')}"
        assert phone.get("pageOverflowsX") is False, f"The research page must not scroll sideways on a phone: {phone}"

        # Each tab brings its own pane to the screen; the chat composer stays inside the chat pane.
        for pane in ("resources", "output", "chat"):
            selected = client.evaluate(page, _PHONE_FRAME_SELECT_PANE_JS.replace("__PANE__", pane), timeout_sec=15.0)
            assert isinstance(selected, dict) and selected.get("ready") is True, selected
            shown = wait_for_state(client, page, _pane_shown_js(pane), timeout_sec=_warm_ui_parallel_wait_sec(60.0))
            assert shown.get("pageOverflowsX") is False, f"Showing the {pane} pane must not overflow the phone width: {shown}"
            if pane == "chat":
                assert shown.get("composerInChatPane") is True, f"The composer must sit inside the chat pane: {shown}"

        client.evaluate(page, _REMOVE_PHONE_FRAME_JS, timeout_sec=10.0)
