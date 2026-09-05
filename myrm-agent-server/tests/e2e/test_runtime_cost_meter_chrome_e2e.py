"""Chrome MCP E2E: Runtime Cost Meter & Search Quota Ledger Task Flow."""

from __future__ import annotations

import json
import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    wait_for_settings_layout,
    wait_for_state,
    warm_ui_route,
)

_VERIFY_COST_METER_STATE_JS = """(() => {
  try {
    const bodyText = document.body ? document.body.innerText : '';
    const hasSearchQuota = /搜索配额|Search Quota|配额水库|Quota Reservoirs|已消耗/i.test(bodyText);
    const hasBrowserCompute = /浏览器|Browser|自动化算力|Compute Runtime|计算时长/i.test(bodyText);
    const hasProviders = /Tavily|Brave|SearXNG/i.test(bodyText);
    
    // Find reset/recalibrate buttons if any
    const buttons = Array.from(document.querySelectorAll('button'));
    const hasResetBtn = buttons.some(b => /重置|校准|Recalibrate|Reset/i.test(b.textContent || ''));

    return {
      ready: hasSearchQuota || hasBrowserCompute || hasProviders,
      hasSearchQuota,
      hasBrowserCompute,
      hasProviders,
      hasResetBtn,
      bodySnippet: bodyText.slice(0, 400),
    };
  } catch (err) {
    return { ready: false, err: String(err) };
  }
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_runtime_cost_meter_settings_ui_and_ledger_chrome_e2e() -> None:
    """Validate Search Quota & Browser Compute Runtime Meter task flow in real Chrome."""
    api_url = get_e2e_api_url()

    # Step 1: Pre-populate search quota and browser telemetry via backend API
    seed_search = http_json(
        "POST",
        f"{api_url}/api/v1/statistics/search-quotas",
        {"provider": "tavily", "count": 120, "quota_exceeded": False},
    )
    assert seed_search.get("code") == 0
    assert seed_search.get("data", {}).get("provider") == "tavily"

    seed_browser = http_json(
        "POST",
        f"{api_url}/api/v1/statistics/browser-runtime",
        {
            "session_id": "e2e-chrome-test-sess",
            "duration_seconds": 60.0,
            "active_compute_seconds": 30.0,
            "bytes_transferred": 1048576,
            "request_count": 15,
            "failed_request_count": 0,
        },
    )
    assert seed_browser.get("code") == 0

    # Step 2: Open /settings/usage in real Chrome MCP
    subroute = "/settings/usage"
    warm_ui_route(subroute)
    with open_settings_subroute(subroute, timeout_ms=90_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_settings_layout(client, page)

        state = wait_for_state(client, page, _VERIFY_COST_METER_STATE_JS, timeout_sec=45.0)
        assert state.get("ready") is True, f"Runtime cost meter not visible on UI: {state}"

    # Step 3: Perform 429 recalibration self-healing check via REST API
    deplete_res = http_json(
        "POST",
        f"{api_url}/api/v1/statistics/search-quotas",
        {"provider": "tavily", "count": 1, "quota_exceeded": True},
    )
    assert deplete_res.get("code") == 0
    assert deplete_res.get("data", {}).get("is_depleted") is True

    # Step 4: Perform recalibrate reset action
    reset_res = http_json(
        "POST",
        f"{api_url}/api/v1/statistics/search-quotas/reset",
        {"provider": "tavily"},
    )
    assert reset_res.get("code") == 0
    assert reset_res.get("data", {}).get("is_depleted") is False
    assert reset_res.get("data", {}).get("used_count") == 0
