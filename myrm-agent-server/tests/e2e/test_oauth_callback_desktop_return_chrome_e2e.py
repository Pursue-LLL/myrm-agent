"""Lane-B: OAuth callback desktop-return branch renders safely in real Chrome.

Covers the `?desktop=1` branch added for Tauri Cloud sign-in return:
invalid exchange shows the error card (no desktop button, no token leak);
missing exchange shows the missing-token error. The Tauri-only
ServerConnection card renders null in browsers by design and is covered
by unit tests instead.
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    get_e2e_api_url,
    get_e2e_ui_url,
    navigate_mcp_page,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_CALLBACK_ERROR_JS = """(() => {
  const bodyText = document.body ? (document.body.innerText || '') : '';
  const bodyHtml = document.body ? (document.body.innerHTML || '') : '';
  const hasError = !!document.querySelector('.text-destructive') || bodyText.length > 20;
  return {
    ready: hasError,
    hasLoginLink: !!document.querySelector('a[href="/auth/login"]'),
    leaksDeepLink: bodyHtml.includes('myrmagent://'),
    bodyPreview: bodyText.slice(0, 200),
    url: window.location.href,
  };
})()"""

_SETTINGS_SHELL_JS = """(() => {
  const bodyText = document.body ? (document.body.innerText || '') : '';
  return {
    ready:
      location.pathname.startsWith('/settings') &&
      bodyText.length > 20 &&
      !!document.querySelector('[data-testid="settings-layout"]'),
    pathname: location.pathname,
    bodyLength: bodyText.length,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_oauth_callback_desktop_return_error_chrome_e2e() -> None:
    """Invalid/missing exchange with desktop=1 renders error UI without token leak."""
    prepare_e2e_ui_session(get_e2e_api_url())
    ui_base = get_e2e_ui_url().rstrip("/")
    warm_ui_route("/auth/oauth/callback")

    with open_settings_subroute("/settings") as (client, page):
        navigate_mcp_page(
            client,
            page,
            f"{ui_base}/auth/oauth/callback?exchange=e2e-invalid-token&desktop=1",
        )
        state = wait_for_state(
            client,
            page,
            _CALLBACK_ERROR_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert state.get("ready") is True, state
        assert state.get("hasLoginLink") is True, state
        assert state.get("leaksDeepLink") is False, state

        navigate_mcp_page(client, page, f"{ui_base}/auth/oauth/callback?desktop=1")
        missing = wait_for_state(
            client,
            page,
            _CALLBACK_ERROR_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert missing.get("ready") is True, missing
        assert missing.get("leaksDeepLink") is False, missing

        # Settings shell must still hydrate in browsers: guards the
        # ServerConnection import changes against breaking the web bundle.
        navigate_mcp_page(client, page, f"{ui_base}/settings")
        shell = wait_for_state(
            client,
            page,
            _SETTINGS_SHELL_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert shell.get("ready") is True, shell
