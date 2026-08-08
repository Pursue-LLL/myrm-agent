"""Chrome E2E: Second Brain pitfall guardrails panel on wiki settings."""

from __future__ import annotations

import os
import sys

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_wiki_settings_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
)

_WIKI_SHELL_JS = """(() => ({
  ready:
    location.pathname.endsWith('/settings/wiki') &&
    !!document.querySelector('[data-testid="wiki-settings-shell"]'),
}))()"""

_PITFALL_PANEL_JS = """(() => {
  const overviewTab = document.querySelector('[role="tab"][data-state="inactive"]');
  const tabs = document.querySelectorAll('[role="tab"]');
  if (tabs.length && !document.querySelector('[data-testid="second-brain-pitfall-panel"]')) {
    tabs[0].click();
  }
  return {
    ready:
      location.pathname.endsWith('/settings/wiki') &&
      !!document.querySelector('[data-testid="second-brain-pitfall-panel"]'),
    hasLadder: !!document.querySelector('[data-testid="second-brain-troubleshooting-ladder"]'),
    hasTeamKb: !!document.querySelector('[data-testid="second-brain-team-kb-scenarios"]'),
    tabCount: tabs.length,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_second_brain_pitfall_guardrails_panel() -> None:
    """Wiki settings shows Second Brain pitfall panel + ladder + team KB chips."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    wiki_page_url = f"{ui_url.rstrip('/')}/settings/wiki"
    with open_wiki_settings_mcp_page(
        wiki_page_url,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    ) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=wiki_page_url)
        shell_state = wait_for_state(
            client,
            page,
            _WIKI_SHELL_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(45.0),
            page_url=wiki_page_url,
        )
        assert shell_state.get("ready") is True, shell_state
        state = wait_for_state(
            client,
            page,
            _PITFALL_PANEL_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            page_url=wiki_page_url,
        )
        assert state.get("ready") is True, state
        assert state.get("hasLadder") is True, state
        assert state.get("hasTeamKb") is True, state
