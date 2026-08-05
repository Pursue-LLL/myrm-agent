"""Phase C inventory: SETTINGS route SHARED+READ smoke (lighter than slash_skill)."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_react_e2e_bridge,
    wait_for_state,
    warm_ui_route,
)

_SETTINGS_SHELL_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    ready:
      location.pathname.startsWith('/settings') &&
      bodyText.length > 20 &&
      !!document.querySelector('[data-testid="settings-layout"]'),
    pathname: location.pathname,
    bodyLength: bodyText.length,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED", access_scope="READ", workload="STANDARD"
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_phase_c_settings_route_shell_smoke() -> None:
    """Shared attach opens settings route without slash palette interactions."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/settings")
    settings_url = f"{ui_url}/settings"
    with open_mcp_page(settings_url, timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page, recover_url=settings_url)
        state: dict[str, object] = {}
        for attempt in range(3):
            try:
                state = wait_for_state(
                    client,
                    page,
                    _SETTINGS_SHELL_STATE,
                    timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                )
                if state.get("ready") is True:
                    break
            except AssertionError:
                if attempt >= 2:
                    raise
            if attempt < 2:
                reload_mcp_page(client, page, target_url=settings_url, timeout_ms=90_000)
                dismiss_blocking_modals(client, page)
        assert state.get("ready") is True, state
