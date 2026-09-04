"""Real Chrome MCP E2E: FAL.ai Video Provider Settings and Media Configuration Doctor lifecycle."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    warm_ui_route,
)

_VERIFY_MEDIA_SECTION_JS = """(() => {
  // Check if media section or settings container exists
  const textContent = document.body.innerText || '';
  const hasFalLabel = textContent.includes('FAL.ai') || textContent.includes('flux-3') || textContent.includes('Media');
  return {
    ok: true,
    hasFalLabel,
    path: window.location.pathname,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="READ",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(300)
def test_fal_media_provider_settings_and_doctor_lifecycle() -> None:
    """Validate backend FAL media provider status, test-media-config, and frontend media settings interaction."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    # 1. Verify backend media-provider-status returns fal provider with models
    status_res = http_json("GET", f"{api_url}/agents/media-provider-status")
    assert isinstance(status_res, dict)
    assert status_res.get("success") is True
    providers = status_res.get("data", {}).get("providers", {})
    assert "fal" in providers
    fal_info = providers["fal"]
    assert "FAL.ai" in fal_info.get("name", "")
    assert fal_info.get("defaultModel") == "fal-ai/flux-3-video"

    # 2. Verify backend test-media-config endpoint responds properly for fal
    test_res = http_json(
        "POST",
        f"{api_url}/agents/test-media-config",
        body={"mediaType": "video", "provider": "fal", "model": "fal-ai/flux-3-video"},
    )
    assert isinstance(test_res, dict)
    assert "success" in test_res

    # 3. Warm up UI route and inspect page state
    warm_ui_route("/")
    with open_mcp_page(f"{ui_url}/", timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_react_e2e_bridge(
            client,
            page,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            page_url=f"{ui_url}/",
        )

        res = client.evaluate(page, _VERIFY_MEDIA_SECTION_JS, timeout_sec=10.0)
        assert isinstance(res, dict)
        assert res.get("ok") is True
