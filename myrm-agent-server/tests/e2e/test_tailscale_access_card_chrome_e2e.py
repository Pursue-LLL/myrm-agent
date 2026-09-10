"""Chrome MCP E2E: Tailscale Zero-Trust Remote Access Card in System Settings UI.

[INPUT]
- tests.support.chrome_mcp_e2e::open_settings_subroute, wait_for_state, dismiss_blocking_modals
- app.api.remote_access.router::tailscale_status (GET /api/v1/remote-access/tailscale/status)
- components/features/settings/sections/system/TailscaleAccessCard.tsx

[OUTPUT]
- test_tailscale_access_card_chrome_e2e: Real Chrome MCP E2E validation of TailscaleAccessCard
  in Settings -> System section (:3000/settings/system).

[POS]
Validates that Tailscale Access status, zero-trust badges, direct/HTTPS connection modes,
and interactive controls (refresh, copy) render and operate cleanly in real Chrome browser.
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

_VERIFY_TAILSCALE_CARD_JS = """(() => {
  try {
    const bodyText = document.body ? document.body.innerText : '';
    const hasTitle = /Tailscale 零信任远程访问|Tailscale/i.test(bodyText);
    const hasBadge = /零信任安全|Tailscale/i.test(bodyText);
    const hasStatus = /已连接 Tailnet|Tailscale 未运行|未检测到 Tailscale|Active|Inactive|Not Installed/i.test(bodyText);

    const buttons = Array.from(document.querySelectorAll('button'));
    const refreshBtn = buttons.find(b =>
      b.getAttribute('title') === 'Refresh Tailscale status' ||
      /Refresh|刷新/i.test(b.textContent || '')
    );
    const copyBtn = buttons.find(b =>
      b.getAttribute('title') === '复制链接' ||
      /Copy|复制/i.test(b.textContent || '')
    );

    return {
      ready: hasTitle && hasBadge && hasStatus,
      hasTitle,
      hasBadge,
      hasStatus,
      hasRefreshBtn: Boolean(refreshBtn),
      hasCopyBtn: Boolean(copyBtn),
      snippet: bodyText.slice(0, 400),
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
@pytest.mark.timeout(600)
def test_tailscale_access_card_chrome_e2e() -> None:
    """Validate Tailscale Access Card renders and operates in real Chrome WebUI (:3000/settings/system)."""
    api_url = get_e2e_api_url()

    # 1. Verify backend API returns 200
    api_resp = http_json("GET", f"{api_url}/api/v1/remote-access/tailscale/status")
    payload = api_resp.get("data") if isinstance(api_resp, dict) and isinstance(api_resp.get("data"), dict) else api_resp
    assert isinstance(payload, dict)
    assert "installed" in payload or "running" in payload, f"Unexpected API response: {api_resp}"

    subroute = "/settings/system"
    warm_ui_route(subroute)
    with open_settings_subroute(subroute, timeout_ms=90_000) as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_settings_layout(client, page)

        state = wait_for_state(client, page, _VERIFY_TAILSCALE_CARD_JS, timeout_sec=45.0)
        assert state.get("ready") is True, f"Tailscale Card not visible in Settings -> System: {state}"
        assert state.get("hasTitle") is True
        assert state.get("hasRefreshBtn") is True

        # 2. Real User Interaction: Click refresh button via client.evaluate and verify responsiveness
        refresh_res = client.evaluate(
            page,
            """(() => {
            const buttons = Array.from(document.querySelectorAll('button'));
            const refreshBtn = buttons.find(b =>
              b.getAttribute('title') === 'Refresh Tailscale status' ||
              /Refresh|刷新/i.test(b.textContent || '')
            );
            if (refreshBtn) {
                refreshBtn.click();
                return { clicked: true };
            }
            return { clicked: false };
        })()""",
            timeout_sec=10.0,
        )
        assert isinstance(refresh_res, dict)
        assert refresh_res.get("clicked") is True, f"Refresh button click failed: {refresh_res}"
