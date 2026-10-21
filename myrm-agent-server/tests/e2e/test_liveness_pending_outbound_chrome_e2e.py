"""Chrome READ E2E: liveness API exposes pendingOutboundCount for ops observability."""

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

_LIVENESS_FETCH_JS = """(async () => {
  const res = await fetch('/api/v1/health/liveness', { cache: 'no-store' });
  if (!res.ok) {
    return { ok: false, status: res.status };
  }
  const body = await res.json();
  const count = body.pendingOutboundCount;
  return {
    ok: typeof count === 'number' && Number.isFinite(count) && count >= 0,
    pendingOutboundCount: count,
    state: body.state,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_liveness_pending_outbound_count_chrome_e2e() -> None:
    """Browser same-origin fetch returns pendingOutboundCount (durable outbound ops field)."""
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(get_e2e_api_url())

    warm_ui_route("/")
    with open_mcp_page(f"{ui_url}/", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_react_e2e_bridge(
            client,
            page,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            page_url=f"{ui_url}/",
        )
        client.navigate(page, f"{ui_url}/", timeout_ms=90_000)
        dismiss_blocking_modals(client, page)
        browser_body = client.evaluate(page, _LIVENESS_FETCH_JS)
        assert browser_body.get("ok") is True, browser_body
        assert isinstance(browser_body.get("state"), str)
