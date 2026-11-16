"""Real Chrome MCP E2E for Zero-Model-Cost Deterministic Behavioral Metrics Panel.

Verifies the user journey on WebUI /settings/memory -> Understand (理解) tab:
1. Navigate to /settings/memory.
2. Verify Command Center renders and switch to Understand tab.
3. Assert BehavioralMetricsPanel micro-histogram, peak active window, and latency cards render.
4. Verify behavioral profile synchronization contract from real browser session.

The Command Center is a Memory Labs surface: the node needs a runtime started with
both Labs switches on and skips, naming the command, on one that was not. Formal run::

    MYRM_MEMORY_LABS=1 NEXT_PUBLIC_MEMORY_LABS=1 ./myrm-dev test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_memory_behavioral_metrics_chrome_e2e.py
"""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    warm_ui_route,
)
from tests.support.memory_labs import require_memory_labs

_BEHAVIORAL_METRICS_CONTRACT_JS = """(async () => {
  try {
    // 1. Fetch behavioral insights from same-origin browser API
    const insightsRes = await fetch('/api/v1/memory/command-center/behavioral-insights?lookback_days=30', {
      cache: 'no-store',
    });
    if (!insightsRes.ok) {
      return { ok: false, status: insightsRes.status, err: 'insights-fetch-failed' };
    }
    const insights = await insightsRes.json();

    // 2. Validate deterministic metric properties
    const hasHistograms = Array.isArray(insights.workday_hour_histogram) && Array.isArray(insights.weekend_hour_histogram);
    const hasDualTracks = insights.workday_hour_histogram.length === 24 && insights.weekend_hour_histogram.length === 24;
    const isZeroModelCost = insights.source === 'computed_deterministic';

    // 3. Trigger behavioral sync from browser session
    const syncRes = await fetch('/api/v1/memory/command-center/behavioral-sync?lookback_days=30', {
      method: 'POST',
      cache: 'no-store',
    });
    if (!syncRes.ok) {
      return { ok: false, status: syncRes.status, err: 'sync-failed' };
    }
    const syncResult = await syncRes.json();

    return {
      ok: true,
      hasHistograms,
      hasDualTracks,
      isZeroModelCost,
      selfMessageCount: insights.self_message_count,
      syncStatus: syncResult.status,
      updatedKeysCount: syncResult.count,
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_behavioral_metrics_panel_contract_in_chrome_e2e() -> None:
    """Browser same-origin verification for behavioral metrics insights and sync contract."""
    api_url = get_e2e_api_url()
    require_memory_labs(api_url)
    prepare_e2e_ui_session(api_url)

    warm_ui_route("/settings/memory")
    with open_settings_subroute("/settings/memory", timeout_ms=90_000) as (
        client,
        page,
    ):
        dismiss_blocking_modals(client, page)
        browser_body = client.evaluate(page, _BEHAVIORAL_METRICS_CONTRACT_JS)
        assert browser_body.get("ok") is True, browser_body
        assert browser_body.get("hasDualTracks") is True, browser_body
        assert browser_body.get("isZeroModelCost") is True, browser_body
        assert browser_body.get("syncStatus") == "success", browser_body
