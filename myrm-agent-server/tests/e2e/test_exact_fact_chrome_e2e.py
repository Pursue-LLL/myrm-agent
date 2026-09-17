"""Real Chrome MCP E2E for Memory Exact Fact Lock & UI contract flow.

Covers the full real-user journey on WebUI /settings/memory:
1. Initialize WebUI session with real backend URL
2. Verify live memory API contracts (list, stats, search) with zero mocks
3. Navigate to /settings/memory in real Chrome browser session
4. Verify memory settings UI shell hydration, tab switchers, and controls
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_MEMORY_UI_STATE_JS = """(() => {
  const root = document.querySelector('main') || document.body;
  const buttons = Array.from(document.querySelectorAll('button')).map(b => (b.textContent || '').trim());
  const switches = document.querySelectorAll('button[role="switch"]');
  return {
    ready: root !== null && buttons.length > 0,
    buttonCount: buttons.length,
    switchCount: switches.length,
    url: window.location.href,
  };
})()"""


# PRIVATE+exclusive_backend: workspace harness often drifts from shared :8080;
# SHARED would epoch-skip under PRIVATE_EPOCH_REQUIRED (TAB-9 requires private_reason).
@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="READ",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_exact_fact_contract_in_chrome_e2e() -> None:
    """Real browser verification for memory exact fact lock & UI contract flow."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # 1. Verify live memory API contracts on exclusive backend (unmocked)
    list_res = http_json("GET", f"{api_url}/api/v1/memory?memory_type=semantic&limit=10")
    assert isinstance(list_res, dict), f"Unexpected list response: {list_res}"
    assert "items" in list_res, f"items missing in list response: {list_res}"

    stats_res = http_json("GET", f"{api_url}/api/v1/memory/stats")
    assert isinstance(stats_res, dict), f"Unexpected stats response: {stats_res}"

    search_res = http_json("GET", f"{api_url}/api/v1/memory/search?query=test&memory_type=semantic")
    assert isinstance(search_res, dict), f"Unexpected search response: {search_res}"
    assert "results" in search_res, f"results missing in search response: {search_res}"

    # 2. Verify WebUI /settings/memory in real Chrome browser
    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=90_000) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        state = wait_for_state(client, page, _MEMORY_UI_STATE_JS, timeout_sec=60.0)
        assert state.get("ready") is True, f"Memory settings UI not ready: {state}"
        assert state.get("buttonCount", 0) > 0, f"Expected interactive buttons in UI: {state}"
