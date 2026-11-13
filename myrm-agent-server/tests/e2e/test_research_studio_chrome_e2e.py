"""Real Chrome MCP E2E for Research Studio three-column workbench.

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
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, open_mcp_page, wait_for_state

RESEARCH_URL = f"{get_e2e_ui_url()}/research"

_DISMISS_MIGRATION_JS = """(() => {
  localStorage.setItem('myrm.proactive.dismissed.migration-discovery', 'forever');
  return true;
})()"""

_LAYOUT_PROBE_JS = """(() => {
  const bodyText = document.body.innerText || '';
  const title = document.title;

  const resourcePool = bodyText.includes('资料池') || bodyText.includes('Resources');
  const emptyState = bodyText.includes('暂无研究资料')
    || bodyText.includes('No resources added yet');
  const wikiBtn = bodyText.includes('从知识库') || bodyText.includes('From Wiki');
  const uploadBtn = bodyText.includes('上传') || bodyText.includes('Upload');
  const selectedCount = bodyText.includes('已选') || bodyText.includes('selected');

  const paneIds = ['resources', 'chat', 'output'];
  const isShown = (el) => el.getClientRects().length > 0;
  const visiblePanes = paneIds.filter((id) => {
    const pane = document.getElementById('research-pane-' + id);
    return pane !== null && isShown(pane);
  });
  const chatPane = document.getElementById('research-pane-chat');
  const rowWidth = chatPane ? chatPane.parentElement.clientWidth : 0;
  // Mirrors the layout's `@6xl` container query: three panes from 72rem of research-area width.
  const wide = rowWidth >= 72 * parseFloat(getComputedStyle(document.documentElement).fontSize);
  const dragHandles = Array.from(document.querySelectorAll('[class*="cursor-col-resize"]')).filter(isShown);
  const tabs = Array.from(document.querySelectorAll('[role="tab"]')).filter(isShown);
  const tabTexts = tabs.map((t) => t.textContent || '');
  const composer = chatPane ? chatPane.querySelector('textarea') : null;
  let composerInChatPane = false;
  if (composer !== null && chatPane !== null && isShown(chatPane)) {
    const paneRect = chatPane.getBoundingClientRect();
    const composerRect = composer.getBoundingClientRect();
    composerInChatPane = composerRect.left >= paneRect.left && composerRect.right <= paneRect.right;
  }

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
    composerInChatPane,
    dragHandleCount: dragHandles.length,
    tabCount: tabs.length,
    tabTexts,
    bodyLength: bodyText.length,
    url: location.href,
    viewportWidth: window.innerWidth,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_research_studio_full_chrome_e2e() -> None:
    """Research Studio: page load, three-column layout, resource pool UI."""
    with open_mcp_page(RESEARCH_URL) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=5.0)

        state = wait_for_state(client, page, _LAYOUT_PROBE_JS, timeout_sec=45.0)

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
