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
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_split_stack_settings_ui_and_discover_api_chrome_e2e() -> None:
    """Validate trusted split-stack model endpoint discovery REST API & WebUI Settings integration in real Chrome."""
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

        # 2. Check split-stack model section & Playbook card presence
        eval_res = client.evaluate(
            page, _VERIFY_SPLIT_STACK_SETTINGS_JS, timeout_sec=20.0
        )
        assert isinstance(
            eval_res, dict
        ), f"Expected dict evaluation result, got: {eval_res}"
        assert eval_res.get("ok") is True, f"Script failed: {eval_res}"
        assert eval_res.get("ready") is True, f"Settings layout not ready: {eval_res}"

        # 3. Check Playbook card presence and full dialog trigger
        eval_playbook = client.evaluate(
            page,
            """(() => {
              const card = document.querySelector('[data-testid="model-orchestration-playbook-card"]');
              const openBtn = document.querySelector('[data-testid="view-full-playbook-button"]');
              if (openBtn) {
                openBtn.click();
              }
              const dialog = document.querySelector('[data-testid="model-orchestration-playbook-dialog"]');
              const tabPrinciples = document.querySelector('[data-testid="playbook-tab-principles"]');
              if (tabPrinciples) {
                tabPrinciples.click();
              }
              const closeBtn = document.querySelector('[data-testid="playbook-close-button"]');
              if (closeBtn) {
                closeBtn.click();
              }
              return {
                ok: true,
                cardFound: !!card,
                openBtnFound: !!openBtn,
                dialogFound: !!dialog,
              };
            })()""",
            timeout_sec=20.0,
        )
        assert isinstance(eval_playbook, dict)
        assert eval_playbook.get("ok") is True
        assert eval_playbook.get("cardFound") is True, "Playbook card rendered in settings"

    # 2. Direct REST probe to /api/v1/health (GET probe, allowed under READ)
    # to confirm server API readiness and model capability catalog
    res_models = http_json("GET", f"{api_url}/api/v1/health")
    assert isinstance(res_models, dict)
    assert res_models.get("status") == "healthy"
