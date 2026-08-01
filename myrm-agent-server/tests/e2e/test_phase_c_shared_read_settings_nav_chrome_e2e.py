"""Phase C inventory: SHARED+READ settings nav smoke (no config mutation)."""

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


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_phase_c_shared_read_settings_nav_smoke() -> None:
    """Shared hot UI attach opens settings/search without mutating global config."""
    ui_url = get_e2e_ui_url().rstrip("/")
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/settings/search")
    settings_url = f"{ui_url}/settings/search"
    with open_mcp_page(settings_url, timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        client.navigate(page, settings_url, timeout_ms=90_000)
        dismiss_blocking_modals(client, page)
        state = wait_for_state(
            client,
            page,
            _SETTINGS_NAV_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert state.get("ready") is True, state
        assert state.get("fetchErrorVisible") is not True, state
