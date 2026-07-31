"""Phase C inventory: minimal SHARED+READ+STANDARD chrome_e2e smoke (home shell)."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_HOME_SHELL_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  const composer = document.querySelector('textarea, [contenteditable="true"]');
  return {
    ready:
      location.pathname === '/' &&
      bodyText.length > 40 &&
      !!composer &&
      composer.offsetParent !== null,
    pathname: location.pathname,
    bodyLength: bodyText.length,
    hasComposer: !!composer,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_phase_c_shared_read_home_shell_smoke() -> None:
    """Shared hot UI attach opens home and exposes the composer shell."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/")
    with open_mcp_page(f"{ui_url}/", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        state = wait_for_state(
            client,
            page,
            _HOME_SHELL_STATE,
            timeout_sec=120.0,
            poll_sec=2.0,
        )
        assert state.get("ready") is True, state
        assert state.get("hasComposer") is True, state
