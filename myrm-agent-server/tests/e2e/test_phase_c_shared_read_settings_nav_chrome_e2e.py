"""Phase C inventory: SHARED+READ settings nav smoke (no config mutation)."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
)

_SETTINGS_NAV_STATE = """(() => {
  const bodyText = document.body?.innerText ?? '';
  const fetchErrorVisible = /无法连接服务器|Unable to connect to the server/i.test(bodyText);
  return {
    ready:
      location.pathname.includes('/settings/search') &&
      !fetchErrorVisible &&
      bodyText.length > 20,
    fetchErrorVisible,
    pathname: location.pathname,
    bodyLength: bodyText.length,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_phase_c_shared_read_settings_nav_smoke() -> None:
    """Shared hot UI attach opens settings/search without mutating global config."""
    prepare_e2e_ui_session(get_e2e_api_url())

    with open_settings_subroute("/settings/search") as (client, page):
        state = wait_for_state(
            client,
            page,
            _SETTINGS_NAV_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert state.get("ready") is True, state
        assert state.get("fetchErrorVisible") is not True, state
