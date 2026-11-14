"""Chrome E2E: the rail's More menu lists Research Studio and opens it.

Prerequisites:
  ./myrm-dev ready --attach --chrome

Covers:
  T1 - The More trigger opens a menu that lists a Research entry pointing at /research
  T2 - Choosing the entry lands on the Research Studio with its chat pane and composer rendered
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

# Radix opens a dropdown on pointerdown, so a bare click() on the trigger would not open it.
_OPEN_MORE_MENU_JS = """(() => {
  const trigger = document.querySelector('[data-testid="nav-more-trigger"]');
  const menu = document.querySelector('[data-testid="nav-more-menu"]');
  const link = menu ? menu.querySelector('a[href="/research"]') : null;
  if (link) {
    return {
      ready: true,
      label: (link.textContent || '').trim(),
      role: link.getAttribute('role'),
      menuItemCount: menu.querySelectorAll('[role="menuitem"], [role="menuitemcheckbox"]').length,
    };
  }
  if (trigger && trigger.getClientRects().length > 0 && trigger.getAttribute('aria-expanded') !== 'true') {
    trigger.dispatchEvent(new PointerEvent('pointerdown', { bubbles: true, button: 0, pointerType: 'mouse', isPrimary: true }));
  }
  return {
    ready: false,
    hasTrigger: !!trigger,
    triggerShown: !!trigger && trigger.getClientRects().length > 0,
    expanded: trigger ? trigger.getAttribute('aria-expanded') : null,
    hasMenu: !!menu,
    viewportWidth: window.innerWidth,
  };
})()"""

_CLICK_RESEARCH_ENTRY_JS = """(() => {
  const link = document.querySelector('[data-testid="nav-more-menu"] a[href="/research"]');
  if (!link) {
    return { ready: false, reason: 'no-research-entry' };
  }
  link.click();
  return { ready: true };
})()"""

_RESEARCH_LANDED_JS = """(() => {
  const chatPane = document.getElementById('research-pane-chat');
  const composer = chatPane ? chatPane.querySelector('textarea') : null;
  return {
    ready: location.pathname === '/research' && composer !== null,
    pathname: location.pathname,
    hasChatPane: chatPane !== null,
    hasComposer: composer !== null,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_more_menu_opens_research_studio() -> None:
    """Research Studio is reachable from the rail's More menu, not only by typing its URL."""
    prepare_e2e_ui_session(get_e2e_api_url())
    ui_url = get_e2e_ui_url().rstrip("/")

    warm_ui_route("/")
    with open_mcp_page(f"{ui_url}/", timeout_ms=120_000) as (client, page):
        dismiss_blocking_modals(client, page)
        ensure_desktop_viewport(client, page)

        menu = wait_for_state(client, page, _OPEN_MORE_MENU_JS, timeout_sec=_warm_ui_parallel_wait_sec(120.0))
        assert menu.get("ready") is True, menu
        assert menu.get("label"), f"the Research entry must carry a visible label: {menu}"
        assert menu.get("role") == "menuitem", f"the Research entry must be a menu item: {menu}"
        print(f"E2E_MORE_MENU: {menu}", flush=True)

        clicked = client.evaluate(page, _CLICK_RESEARCH_ENTRY_JS, timeout_sec=15.0)
        assert isinstance(clicked, dict) and clicked.get("ready") is True, clicked

        landed = wait_for_state(client, page, _RESEARCH_LANDED_JS, timeout_sec=_warm_ui_parallel_wait_sec(120.0))
        assert landed.get("pathname") == "/research", landed
        assert landed.get("hasChatPane") is True and landed.get("hasComposer") is True, landed
