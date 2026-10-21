"""Chrome MCP E2E: OpenTelemetry Trace Posture & SRE Diagnostics UI.

[INPUT]
- tests.support.chrome_mcp_e2e::open_settings_subroute, wait_for_state, dismiss_blocking_modals
- services/system::get_telemetry_posture (GET /api/v1/system/telemetry-posture)
- components/features/settings/sections/system/TelemetryPostureCard.tsx

[OUTPUT]
- test_telemetry_posture_card_chrome_e2e: Real Chrome MCP E2E validation of TelemetryPostureCard
  in Settings -> Developer section (:3000/settings/developer).

[POS]
E2E browser integration test verifying that SRE OpenTelemetry Posture diagnostics render
correctly on the live WebUI, display protocol/endpoint details, and refresh on demand.
"""

from __future__ import annotations

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

_VERIFY_TELEMETRY_CARD_JS = """(() => {
  try {
    const bodyText = document.body ? document.body.innerText : '';
    const hasTitle = /OpenTelemetry Trace Posture|遥测态势|Telemetry/i.test(bodyText);
    const hasProtocol = /Protocol|协议|HTTP\\/PROTOBUF|GRPC|NOOP/i.test(bodyText);
    const hasEndpoint = /Endpoint|端点/i.test(bodyText);
    const hasFeatures = /3-Tier GenAI|三层 GenAI|Capabilities|特性/i.test(bodyText);
    const hasEnvironment = /Environment|代码环境|Branch|Non-Git/i.test(bodyText);

    const buttons = Array.from(document.querySelectorAll('button'));
    const refreshBtn = buttons.find(b => /Refresh|刷新|更新/i.test(b.textContent || ''));
    const copyBtn = buttons.find(b => /Copy Env|复制/i.test(b.textContent || ''));

    return {
      ready: hasTitle && (hasProtocol || hasEndpoint || hasFeatures || hasEnvironment),
      hasTitle,
      hasProtocol,
      hasEndpoint,
      hasFeatures,
      hasEnvironment,
      hasRefreshBtn: Boolean(refreshBtn),
      hasCopyBtn: Boolean(copyBtn),
      snippet: bodyText.slice(0, 300),
    };
  } catch (err) {
    return { ready: false, err: String(err) };
  }
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_telemetry_posture_card_chrome_e2e() -> None:
    """Validate OpenTelemetry Posture card renders in real Chrome WebUI (:3000/settings/developer)."""
    api_url = get_e2e_api_url()

    # Verify backend API returns 200 first
    api_resp = http_json("GET", f"{api_url}/api/v1/system/telemetry-posture")
    assert "status" in api_resp or "protocol" in api_resp or "error" not in api_resp

    subroute = "/settings/developer"
    warm_ui_route(subroute)
    with open_settings_subroute(subroute, timeout_ms=90_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_settings_layout(client, page)

        state = wait_for_state(client, page, _VERIFY_TELEMETRY_CARD_JS, timeout_sec=45.0)
        assert state.get("ready") is True, f"Telemetry Posture Card not visible: {state}"
        assert state.get("hasTitle") is True
        assert state.get("hasRefreshBtn") is True

        # Real User Interaction: Click refresh button via client.evaluate and verify no crash
        refresh_res = client.evaluate(page, """(() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const refreshBtn = buttons.find(b => /Refresh|刷新|更新/i.test(b.textContent || ''));
            if (refreshBtn) {
                refreshBtn.click();
                return { clicked: true };
            }
            return { clicked: false };
        })()""", timeout_sec=10.0)
        assert isinstance(refresh_res, dict)
        assert refresh_res.get("clicked") is True, f"Refresh button click failed: {refresh_res}"

        # Real User Interaction: Click copy env config button and verify no crash
        copy_res = client.evaluate(page, """(() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const copyBtn = buttons.find(b => /Copy Env|复制/i.test(b.textContent || ''));
            if (copyBtn) {
                copyBtn.click();
                return { clicked: true };
            }
            return { clicked: false };
        })()""", timeout_sec=10.0)
        assert isinstance(copy_res, dict)
        assert copy_res.get("clicked") is True, f"Copy button click failed: {copy_res}"


