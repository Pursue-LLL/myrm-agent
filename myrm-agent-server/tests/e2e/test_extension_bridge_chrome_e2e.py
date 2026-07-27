"""Real Chrome MCP E2E for Settings → Browser Extension Bridge relay contract UI."""

from __future__ import annotations

from urllib.parse import urlparse

import pytest

from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_EXTENSION_BRIDGE_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  const fetchErrorVisible = /无法连接服务器|Unable to connect to the server/i.test(bodyText);
  const matrixLabels = ['URL 导航', '标签页发现', '调试器附加', '调试器分离',
    'URL Navigation', 'Tab Discovery', 'Debugger Attach', 'Debugger Detach'];
  const matrixHits = matrixLabels.filter((label) => bodyText.includes(label));
  const unavailableHits = (bodyText.match(/不可用|Unavailable/g) || []).length;
  const relayLine = (bodyText.match(/私网中继能力[^\\n]*/i) || [])[0] || '';
  const wsMatch = bodyText.match(/ws:\\/\\/[^\\s]+\\/api\\/v1\\/ws\\/extension/i);
  return {
    ready:
      !fetchErrorVisible &&
      location.pathname.includes('/settings/extensionBridge') &&
      matrixHits.length >= 4 &&
      unavailableHits >= 4 &&
      /未连接|Not connected/i.test(bodyText) &&
      /chrome:\\/\\/inspect\\/#remote-debugging/i.test(bodyText) &&
      !!wsMatch,
    fetchErrorVisible,
    matrixHits: matrixHits.length,
    unavailableHits,
    relayLine,
    wsUrl: wsMatch ? wsMatch[0] : '',
    heading: document.querySelector('h2')?.textContent || '',
  };
})()"""


@pytest.mark.chrome_e2e(lane="READ")
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_extension_bridge_settings_relay_contract_in_real_ui() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    api_port = urlparse(api_url).port or 8080

    status = http_json("GET", f"{api_url}/api/v1/extension/status")
    assert isinstance(status, dict)
    assert status.get("connected") is False
    assert status.get("handshake_ready") is False
    assert status.get("capabilities") == []

    hints = http_json("GET", f"{api_url}/api/v1/extension/setup-hints")
    assert isinstance(hints, dict)
    assert "auth_token_configured" in hints
    assert "cdp_endpoint_discovered" in hints

    warm_ui_route("/settings/extensionBridge")

    with open_mcp_page(f"{ui_url}/settings/extensionBridge") as (client, page):
        dismiss_blocking_modals(client, page)
        state = wait_for_state(
            client,
            page,
            _EXTENSION_BRIDGE_STATE,
            timeout_sec=90.0,
        )
        assert state.get("fetchErrorVisible") is not True, state
        assert int(state.get("matrixHits") or 0) >= 4, state
        assert int(state.get("unavailableHits") or 0) >= 4, state
        ws_url = str(state.get("wsUrl") or "")
        assert f":{api_port}/api/v1/ws/extension" in ws_url, state
        heading = str(state.get("heading") or "")
        assert "浏览器扩展桥接" in heading or "Browser Extension" in heading, state
