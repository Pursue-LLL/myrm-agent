"""Chrome READ E2E: Lifecycle Outbound Webhook settings management and ping probe."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    warm_ui_route,
)

_WEBHOOK_SETTINGS_CHECK_JS = """(async () => {
  const res = await fetch('/api/lifecycle-webhooks', { cache: 'no-store' });
  if (!res.ok) {
    return { ok: false, status: res.status };
  }
  const hooks = await res.json();
  return {
    ok: Array.isArray(hooks),
    count: hooks.length,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_lifecycle_webhook_settings_chrome_e2e() -> None:
    """Browser same-origin fetch verifies lifecycle webhook settings endpoint accessibility in WebUI."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/settings/integrationCatalog")
    with open_mcp_page(f"{ui_url}/settings/integrationCatalog", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_react_e2e_bridge(
            client,
            page,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            page_url=f"{ui_url}/settings/integrationCatalog",
        )
        browser_body = client.evaluate(page, _WEBHOOK_SETTINGS_CHECK_JS)
        assert browser_body.get("ok") is True, browser_body
