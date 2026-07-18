"""Real Chrome MCP E2E for Research Studio three-column workbench.

Prerequisites:
  ./myrm ready --chrome

Covers:
  T1 - /research page loads with correct three-column layout (PC mode)
  T2 - Resource pool displays empty state with correct UI elements
  T3 - Resource pool actions (Wiki, Upload) buttons present
  T4 - Desktop three-column layout has drag handles
  T5 - Metadata title correct
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, open_mcp_page, wait_for_state

RESEARCH_URL = f"{get_e2e_ui_url()}/research"

_DISMISS_MIGRATION_JS = """(() => {
  sessionStorage.setItem('migration_discovery_dismissed', 'true');
  sessionStorage.setItem('competitor_migration_dismissed', 'true');
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

  const isMobile = window.matchMedia('(max-width: 768px)').matches;
  const dragHandles = document.querySelectorAll('[class*="cursor-col-resize"]');
  const tabs = document.querySelectorAll('[role="tab"]');
  const tabTexts = Array.from(tabs).map(t => t.textContent || '');

  return {
    ready: (resourcePool || emptyState) && title.includes('Research'),
    title,
    resourcePool,
    emptyState,
    wikiBtn,
    uploadBtn,
    selectedCount,
    isMobile,
    dragHandleCount: dragHandles.length,
    tabCount: tabs.length,
    tabTexts,
    bodyLength: bodyText.length,
    url: location.href,
    viewportWidth: window.innerWidth,
  };
})()"""


@pytest.mark.chrome_e2e(lane="LIVE_AGENT")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_research_studio_full_chrome_e2e() -> None:
    """Research Studio: page load, three-column layout, resource pool UI."""
    with open_mcp_page(RESEARCH_URL) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=5.0)

        state = wait_for_state(client, page, _LAYOUT_PROBE_JS, timeout_sec=45.0)

        # T5: Metadata title
        assert "Research" in str(state.get("title", "")), (
            f"Page title should contain 'Research': {state.get('title')}"
        )
        assert state.get("url", "").endswith("/research"), (
            f"URL should end with /research: {state.get('url')}"
        )

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

        # T4: Responsive layout verification
        is_mobile = state.get("isMobile") is True
        viewport_w = state.get("viewportWidth", 0)
        if is_mobile:
            assert isinstance(state.get("tabCount"), int) and state["tabCount"] >= 3, (
                f"Mobile ({viewport_w}px) should show >=3 tabs, got {state.get('tabCount')}"
            )
        else:
            assert isinstance(state.get("dragHandleCount"), int) and state["dragHandleCount"] >= 2, (
                f"Desktop ({viewport_w}px) should have >=2 drag handles, got {state.get('dragHandleCount')}"
            )
