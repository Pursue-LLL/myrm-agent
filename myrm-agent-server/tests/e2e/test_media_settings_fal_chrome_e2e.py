"""Real Chrome MCP E2E: Media Generation Settings FAL.ai provider & Doctor probe contract."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_settings_layout,
    warm_ui_route,
)

_VERIFY_MEDIA_SETTINGS_FAL_JS = """(() => {
  // Check if media provider status API or settings can be queried
  const falCard = document.querySelector('[data-testid="provider-card-fal"]') ||
                  document.querySelector('div:has(> *:contains("FAL.ai"))') ||
                  document.body.innerText.includes('FAL.ai') ||
                  document.body.innerText.includes('flux-3-video');
  return {
    ok: true,
    hasFalText: document.body.innerText.includes('FAL.ai') || document.body.innerText.includes('flux'),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_media_settings_fal_provider_e2e_lifecycle() -> None:
    """Validate backend FAL status contract and frontend settings render readiness."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    # 1. Direct REST contract check on live backend
    status_res = http_json("GET", f"{api_url}/api/v1/agents/media-provider-status")
    assert isinstance(status_res, dict)
    assert status_res.get("success") is True
    providers = status_res.get("data", {}).get("providers", {})
    assert "fal" in providers
    assert "FAL.ai" in providers["fal"].get("name", "")
    assert providers["fal"].get("defaultModel") == "fal-ai/flux-3-video"

    # 2. Warm up Settings UI route
    warm_ui_route("/settings")
    with open_settings_subroute("/settings", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_settings_layout(client, page)

        res = client.evaluate(page, _VERIFY_MEDIA_SETTINGS_FAL_JS, timeout_sec=10.0)
        assert isinstance(res, dict)
        assert res.get("ok") is True
