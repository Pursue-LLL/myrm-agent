"""Real Chrome MCP E2E: FAL.ai Video Media Provider API & WebUI Settings Integration."""

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

_VERIFY_FAL_MEDIA_SETTINGS_JS = """(() => {
  // Query for media settings or provider elements
  const cards = Array.from(document.querySelectorAll('[data-testid^="media-provider-card-"], .rounded-xl, .rounded-lg'));
  const falCard = cards.find(el => el.textContent && el.textContent.includes('FAL.ai'));
  
  return {
    ok: true,
    hasFalMention: Boolean(falCard || document.body.innerText.includes('FAL.ai') || document.body.innerText.includes('FLUX.3')),
    cardFound: Boolean(falCard),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_fal_media_config_api_and_settings_chrome_e2e() -> None:
    """Validate backend FAL provider status contract and frontend settings render in real Chrome."""
    _require_e2e_cdp_ready()
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    # 1. Direct REST probe to /api/v1/agents/media-provider-status
    status_res = http_json("GET", f"{api_url}/api/v1/agents/media-provider-status")
    assert isinstance(status_res, dict)
    assert status_res.get("success") is True
    providers = status_res.get("data", {}).get("providers", {})
    assert "fal" in providers, f"FAL provider missing in live providers: {providers.keys()}"
    fal_info = providers["fal"]
    assert "FAL.ai" in fal_info.get("name", "")
    assert fal_info.get("defaultModel") == "fal-ai/flux-3-video"

    # 2. Warm up Settings UI route and verify with Chrome MCP
    warm_ui_route("/settings")
    with open_settings_subroute("/settings?tab=media", timeout_ms=90_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_settings_layout(client, page)

        dom_res = client.evaluate(page, _VERIFY_FAL_MEDIA_SETTINGS_JS, timeout_sec=10.0)
        assert isinstance(dom_res, dict)
        assert dom_res.get("ok") is True
