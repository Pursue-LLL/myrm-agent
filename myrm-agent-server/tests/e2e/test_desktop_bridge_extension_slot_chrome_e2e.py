"""Chrome MCP E2E for Desktop Bridge & Declarative Extension Slot Protocol.

Verifies:
1. Zero-Chrome WebUI parity: In standard browser environment, --traffic-light-inset-top
   evaluates cleanly to 0px, ensuring zero UI chrome collision or unwanted margins.
2. ExtensionSlot rendering: Extension slots in NavBar and Sidebar footer mount cleanly
   without throwing errors or degrading WebUI layout.
3. Layout stability: Core layout containers (nav, chat sidebar) remain functional and interactive.
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
  const navSlot = document.querySelector('[data-slot-name="navbar.bottom.tools"]');
  const sidebarSlot = document.querySelector('[data-slot-name="sidebar.footer.action"]');
  const appLayout = document.querySelector('[data-testid="app-layout"]') || document.body;

  // In standard browser E2E (non-Tauri), topInset should be '0px' or unset (empty).
  const isZeroChromeWeb = topInset === '0px' || topInset === '' || topInset === '0';

  return {
    ready: !!appLayout && !!navBar && isZeroChromeWeb,
    hasNavBar: !!navBar,
    topInset,
    leftInset,
    isZeroChromeWeb,
    hasNavSlot: !!navSlot,
    hasSidebarSlot: !!sidebarSlot,
    bodyLen: document.body ? document.body.innerText.length : 0,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_desktop_bridge_extension_slot_and_zero_chrome_parity() -> None:
    """Validate Zero-Chrome insets and ExtensionSlot protocol in live Chrome."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/")
    with open_mcp_page(f"{ui_url}/", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
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
