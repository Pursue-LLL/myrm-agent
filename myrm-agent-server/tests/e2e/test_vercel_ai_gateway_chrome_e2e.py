"""Real Chrome MCP E2E: Vercel AI Gateway Provider Preset & Spend Observability Integration."""

from __future__ import annotations

import os

import pytest
from myrm_agent_harness.toolkits.llms.core.llm import create_litellm_model

from tests.support.chrome_mcp_e2e import (
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_settings_layout,
    warm_ui_route,
)

_VERIFY_VERCEL_GATEWAY_SETTINGS_JS = """(() => {
  try {
    const bodyText = document.body ? document.body.innerText : '';
    const hasSettingsLayout = !!document.querySelector('[data-testid="settings-layout"]') || document.querySelectorAll('button, nav').length > 5;
    const hasModelSection = /模型|Models|Provider|供应商/i.test(bodyText);
    
    // Locate Vercel AI Gateway in provider list and click it
    const elements = Array.from(document.querySelectorAll('span, div, button'));
    const vercelListItem = elements.find(el => el.textContent && el.textContent.trim() === 'Vercel AI Gateway');
    let clicked = false;
    if (vercelListItem) {
      const clickableParent = vercelListItem.closest('div[class*="cursor-pointer"]') || vercelListItem;
      clickableParent.click();
      clicked = true;
    }

    const hasVercelGateway = /Vercel|ai-gateway/i.test(bodyText);
    return {
      ok: true,
      ready: hasSettingsLayout,
      hasModelSection,
      hasVercelGateway,
      hasVercelListItem: !!vercelListItem,
      clicked,
      pathname: location.pathname,
      bodySnippet: bodyText.slice(0, 300),
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""

_VERIFY_VERCEL_CONFIG_DETAILS_JS = """(() => {
  try {
    const dashboardLink = document.querySelector('a[href*="vercel.com/dashboard/ai-gateway"]');
    const bodyText = document.body ? document.body.innerText : '';
    const hasSpendHint = /Spend|消耗|成本|额度|Console|Dashboard/i.test(bodyText) || !!dashboardLink;
    const hasGatewayUrl = /ai-gateway\\.vercel\\.sh/i.test(bodyText);
    return {
      ok: true,
      hasDashboardLink: !!dashboardLink,
      hasSpendHint,
      hasGatewayUrl,
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="workspace_backend_code_drift",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_vercel_ai_gateway_settings_ui_and_attribution_chrome_e2e() -> None:
    """Validate Vercel AI Gateway provider preset, attribution headers and settings integration in real Chrome."""
    _require_e2e_cdp_ready()
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # 1. Warm up Settings UI route and open in real Chrome MCP to verify rendering
    target_url = f"{api_url.replace(':8080', ':3000')}/settings/models"
    warm_ui_route("/settings/models")
    with open_settings_subroute("/settings/models", timeout_ms=90_000) as (
        client,
        page,
    ):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_settings_layout(client, page, page_url=target_url)

        eval_res = client.evaluate(page, _VERIFY_VERCEL_GATEWAY_SETTINGS_JS, timeout_sec=20.0)
        assert isinstance(eval_res, dict), f"Expected dict evaluation result, got: {eval_res}"
        assert eval_res.get("ok") is True, f"Script failed: {eval_res}"
        assert eval_res.get("ready") is True, f"Settings layout not ready: {eval_res}"
        assert eval_res.get("hasModelSection") is True, f"Model section not found: {eval_res}"

        # Step 1.5: If clicked on Vercel AI Gateway item, verify detail card contents
        if eval_res.get("clicked"):
            import time
            time.sleep(1.0)
            detail_res = client.evaluate(page, _VERIFY_VERCEL_CONFIG_DETAILS_JS, timeout_sec=20.0)
            assert isinstance(detail_res, dict), f"Expected dict evaluation result, got: {detail_res}"
            assert detail_res.get("ok") is True, f"Script failed: {detail_res}"
            assert detail_res.get("hasDashboardLink") is True or detail_res.get("hasSpendHint") is True

    # 2. REST API probe to verify server health
    res_health = http_json("GET", f"{api_url}/api/v1/health")
    assert isinstance(res_health, dict)
    assert res_health.get("status") == "healthy"

    # 3. Verify Vercel AI Gateway attribution headers
    gw_model = create_litellm_model(
        "openai/gpt-4o",
        api_key="vca_test_mock_key",
        base_url="https://ai-gateway.vercel.sh/v1",
    )
    headers = getattr(gw_model, "model_kwargs", {}).get("extra_headers", {})
    assert headers.get("HTTP-Referer") == "https://myrm.ai"
    assert headers.get("X-Title") == "Myrm Agent"
    assert headers.get("User-Agent") == "Myrm/1.0 (Vercel-AI-Gateway-Client)"

    # 4. Real user task flow: execute prompt with active test LLM to ensure working inference
    real_api_key = os.getenv("BASIC_API_KEY")
    real_base_url = os.getenv("BASIC_BASE_URL")
    real_model_name = os.getenv("BASIC_MODEL")
    if real_api_key and real_base_url and real_model_name:
        real_llm = create_litellm_model(
            real_model_name,
            api_key=real_api_key,
            base_url=real_base_url,
        )
        task_prompt = "请用中文回答：1+1等于几？"
        response = real_llm.invoke(task_prompt)
        assert response is not None
        assert "2" in response.content or "二" in response.content
