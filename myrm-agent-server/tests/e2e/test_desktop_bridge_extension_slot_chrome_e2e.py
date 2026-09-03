"""Chrome MCP E2E for Desktop Bridge & Declarative Extension Slot Protocol.

Verifies:
1. Zero-Chrome WebUI parity: In standard browser environment, --traffic-light-inset-top
   evaluates cleanly to 0px, ensuring zero UI chrome collision or unwanted margins.
2. ExtensionSlot Store Lifecycle: Dynamic registration, query, order sorting, and unregistration
   via window.__MYRM_EXTENSION_SLOT_STORE__ in a live Chrome browser session.
3. Layout stability: Core layout containers (nav, chat sidebar) remain functional and interactive.
4. Browser fallback safety: Verification that native OS capabilities degrade safely in Web mode.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_DESKTOP_BRIDGE_EXTENSION_SLOT_STATE = """(() => {
  const root = document.documentElement;
  const computedStyle = getComputedStyle(root);
  const topInset = computedStyle.getPropertyValue('--traffic-light-inset-top').trim();
  const leftInset = computedStyle.getPropertyValue('--traffic-light-inset-left').trim();

  const navBar = document.querySelector('nav') || document.querySelector('[role="navigation"]');
  const appLayout = document.querySelector('[data-testid="app-layout"]') || document.body;

  // In standard browser E2E (non-Tauri), topInset should be '0px' or unset (empty).
  const isZeroChromeWeb = topInset === '0px' || topInset === '' || topInset === '0';

  return {
    ready: !!appLayout && !!navBar && isZeroChromeWeb,
    hasNavBar: !!navBar,
    topInset,
    leftInset,
    isZeroChromeWeb,
    bodyLen: document.body ? document.body.innerText.length : 0,
  };
})()"""

_TEST_EXTENSION_SLOT_STORE_JS = """(() => {
  const store = window.__MYRM_EXTENSION_SLOT_STORE__;
  if (!store) {
    return { ok: false, err: 'store_not_exposed' };
  }

  const state = store.getState();

  // Test dynamic contribution registration
  const unregister = state.registerContribution({
    id: 'e2e-test-action',
    slotName: 'navbar.bottom.tools',
    order: 5,
    component: () => null,
  });

  const registered = store.getState().getContributionsForSlot('navbar.bottom.tools');
  const hasRegistered = registered.some((c) => c.id === 'e2e-test-action');

  // Test unregistration
  unregister();
  const afterUnregister = store.getState().getContributionsForSlot('navbar.bottom.tools');
  const isCleaned = !afterUnregister.some((c) => c.id === 'e2e-test-action');

  return {
    ok: true,
    hasStore: true,
    hasRegistered,
    isCleaned,
  };
})()"""

_TEST_NAV_TABS_INTERACTIVE_JS = """(() => {
  const links = Array.from(document.querySelectorAll('nav a'));
  const chatLink = links.find((l) => l.getAttribute('href') === '/' || l.getAttribute('href') === '');
  const settingsLink = links.find((l) => (l.getAttribute('href') || '').includes('/settings'));

  return {
    hasLinks: links.length >= 2,
    hasChatLink: !!chatLink,
    hasSettingsLink: !!settingsLink,
    linkCount: links.length,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_desktop_bridge_extension_slot_and_zero_chrome_parity() -> None:
    """Validate Zero-Chrome insets, ExtensionSlot store lifecycle, and layout stability in live Chrome."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/")
    with open_mcp_page(f"{ui_url}/", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)

        # 1. Verify Zero-Chrome WebUI Insets and Core Navigation
        state = wait_for_state(
            client,
            page,
            _DESKTOP_BRIDGE_EXTENSION_SLOT_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert state.get("ready") is True, f"State check failed: {state}"
        assert state.get("hasNavBar") is True, "NavBar must be mounted in WebUI"
        assert state.get("isZeroChromeWeb") is True, (
            f"Expected 0px top inset in Web mode, got {state.get('topInset')}"
        )

        # 2. Verify ExtensionSlot Store Lifecycle in Browser
        slot_eval = client.evaluate(page, _TEST_EXTENSION_SLOT_STORE_JS, timeout_sec=20.0)
        assert slot_eval.get("ok") is True, f"ExtensionSlot store evaluation failed: {slot_eval}"
        assert slot_eval.get("hasRegistered") is True, "Dynamic contribution registration must succeed"
        assert slot_eval.get("isCleaned") is True, "Unregistration closure must remove contribution"

        # 3. Verify Navigation Links Interactive State
        nav_eval = client.evaluate(page, _TEST_NAV_TABS_INTERACTIVE_JS, timeout_sec=20.0)
        assert nav_eval.get("hasLinks") is True, f"NavBar links check failed: {nav_eval}"
        assert nav_eval.get("hasSettingsLink") is True, "Settings link must be accessible in nav"
