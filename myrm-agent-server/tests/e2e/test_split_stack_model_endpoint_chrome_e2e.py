"""Real Chrome MCP E2E: Trusted LAN / Tailscale Split-Stack Model Endpoint & WebUI Settings Integration."""

from __future__ import annotations

import pytest

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

_VERIFY_SPLIT_STACK_SETTINGS_JS = """(() => {
  try {
    const bodyText = document.body ? document.body.innerText : '';
    const hasSettingsLayout = !!document.querySelector('[data-testid="settings-layout"]') || document.querySelectorAll('button, nav').length > 5;
    const hasModelSection = /模型|Models|Provider|供应商/i.test(bodyText);
    return {
      ok: true,
      ready: hasSettingsLayout,
      hasModelSection,
      pathname: location.pathname,
      bodySnippet: bodyText.slice(0, 300),
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_split_stack_settings_ui_and_discover_api_chrome_e2e() -> None:
    """Validate trusted split-stack model endpoint discovery REST API & WebUI Settings integration in real Chrome."""
    _require_e2e_cdp_ready()
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # 1. Direct REST probe to /api/v1/integrations/llm/discover-models for untrusted public endpoint without key -> rejected
    res_public = http_json(
        "POST",
        f"{api_url}/api/v1/integrations/llm/discover-models",
        body={"api_url": "https://api.openai.com/v1"},
    )
    assert isinstance(res_public, dict)
    assert res_public.get("success") is True  # standard ApiResponse envelope
    data_public = res_public.get("data", {})
    assert data_public.get("success") is False
    assert "API key is required" in (data_public.get("error") or "")

    # 2. Direct REST probe for cloud link-local metadata (169.254.169.254) -> strictly rejected
    res_link_local = http_json(
        "POST",
        f"{api_url}/api/v1/integrations/llm/discover-models",
        body={"api_url": "http://169.254.169.254/latest/meta-data"},
    )
    assert isinstance(res_link_local, dict)
    data_link_local = res_link_local.get("data", {})
    assert data_link_local.get("success") is False
    assert "API key is required" in (data_link_local.get("error") or "")

    # 3. Direct REST probe for trusted LAN / Tailscale host without key
    # In local development mode, server recognizes 192.168.1.253 as trusted split-stack host
    # and attempts probe with allowed_internal_hosts without requiring a user key.
    # We test with a dummy LAN endpoint: connection failure is handled gracefully with structured error,
    # proving the request passed the auth check and attempted network connect.
    res_lan = http_json(
        "POST",
        f"{api_url}/api/v1/integrations/llm/discover-models",
        body={"api_url": "http://192.168.1.253:11434/v1"},
    )
    assert isinstance(res_lan, dict)
    data_lan = res_lan.get("data", {})
    assert data_lan.get("error") != "API key is required for non-local endpoints", (
        f"Expected trusted LAN host to bypass key check, but got: {data_lan}"
    )

    # 4. Open Settings in real Chrome MCP and verify the UI renders
    warm_ui_route("/settings")
    with open_settings_subroute("/settings?tab=models", timeout_ms=90_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_settings_layout(client, page)

        eval_res = client.evaluate(page, _VERIFY_SPLIT_STACK_SETTINGS_JS, timeout_sec=20.0)
        assert isinstance(eval_res, dict), f"Expected dict evaluation result, got: {eval_res}"
        assert eval_res.get("ok") is True, f"Script failed: {eval_res}"
        assert eval_res.get("ready") is True, f"Settings layout not ready: {eval_res}"
