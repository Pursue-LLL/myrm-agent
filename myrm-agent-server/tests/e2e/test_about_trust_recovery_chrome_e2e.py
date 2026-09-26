"""Lane-B: About tab hydrates with trust/recovery cards mounted (read-only).

Covers the SystemCenterSection about tab where TrustBadgeCard and
RecoveryGuideCard mount. No writes, no backend mutation: asserts shell
hydration, the About content itself, and zero error boundaries.
The two cards are Tauri-gated by design (null in browsers); their
Tauri-only behavior is covered by unit tests with a mocked runtime.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
)

_ABOUT_TAB_STATE = """(() => {
  const bodyText = document.body ? (document.body.innerText || '') : '';
  const headings = Array.from(document.querySelectorAll('h1, h2')).map((h) => h.textContent || '');
  const hasErrors = /Application error|Something went wrong/i.test(bodyText);
  return {
    ready:
      location.pathname.startsWith('/settings') &&
      bodyText.length > 20 &&
      !!document.querySelector('[data-testid="settings-layout"]'),
    headings: headings.slice(0, 60),
    hasErrors,
    url: window.location.href,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_about_tab_trust_recovery_chrome_e2e() -> None:
    """About tab hydrates cleanly with the trust/recovery mount point."""
    prepare_e2e_ui_session(get_e2e_api_url())

    with open_settings_subroute("/settings/system?sub=about") as (client, page):
        state = wait_for_state(
            client,
            page,
            _ABOUT_TAB_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert state.get("ready") is True, state
        assert state.get("hasErrors") is False, state
        headings = state.get("headings") or []
        assert any("MyrmAgent" in h for h in headings), state
