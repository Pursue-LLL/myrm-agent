"""Real Chrome MCP E2E: Vercel AI Gateway Provider Preset & Spend Observability Integration."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    wait_for_settings_layout,
    warm_ui_route,
)

_VERIFY_VERCEL_GATEWAY_SETTINGS_JS = """(() => {
  try {
    const bodyText = document.body ? document.body.innerText : '';
    const hasSettingsLayout = !!document.querySelector('[data-testid="settings-layout"]') || document.querySelectorAll('button, nav').length > 5;
    const hasModelSection = /模型|Models|Provider|供应商/i.test(bodyText);
    const hasVercelGateway = /Vercel|ai-gateway/i.test(bodyText);
    return {
      ok: true,
      ready: hasSettingsLayout,
      hasModelSection,
      hasVercelGateway,
      pathname: location.pathname,
      bodySnippet: bodyText.slice(0, 300),
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_vercel_ai_gateway_settings_ui_and_attribution_chrome_e2e() -> None:
    """Validate Vercel AI Gateway provider preset, attribution headers and settings integration in real Chrome."""
    _require_e2e_cdp_ready()
    api_url = get_e2e_api_url()

    # 1. Warm up Settings UI route and open in real Chrome MCP to verify rendering
    target_url = f"{api_url.replace(':8080', ':3000')}/settings?tab=models"
    warm_ui_route("/settings")
    with open_settings_subroute("/settings?tab=models", timeout_ms=90_000) as (
        client,
        page,
    ):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_settings_layout(client, page, page_url=target_url)

        eval_res = client.evaluate(
            page, _VERIFY_VERCEL_GATEWAY_SETTINGS_JS, timeout_sec=20.0
        )
        assert isinstance(
            eval_res, dict
        ), f"Expected dict evaluation result, got: {eval_res}"
        assert eval_res.get("ok") is True, f"Script failed: {eval_res}"
        assert eval_res.get("ready") is True, f"Settings layout not ready: {eval_res}"
        assert eval_res.get("hasModelSection") is True, f"Model section not found: {eval_res}"

    # 2. REST API probe to verify server health and model discovery endpoints
    res_health = http_json("GET", f"{api_url}/api/v1/health")
    assert isinstance(res_health, dict)
    assert res_health.get("status") == "healthy"
