"""Chrome MCP E2E: /pricing renders billing catalog shell (READ-only, no checkout)."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    get_e2e_ui_url,
    navigate_mcp_page,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_PRICING_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const ready = /定价|Pricing/i.test(text);
  return { ready, sample: text.slice(0, 200) };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.timeout(240)
def test_billing_pricing_page_renders() -> None:
    warm_ui_route("/pricing")
    pricing_url = f"{get_e2e_ui_url()}/pricing"
    with open_mcp_page(pricing_url, skip_settings_layout_wait=True) as (client, page):
        navigate_mcp_page(client, page, pricing_url, timeout_ms=90_000)
        state = wait_for_state(client, page, _PRICING_READY_JS, timeout_sec=90.0)
        assert state.get("ready") is True, state
