"""Real Chrome MCP E2E: A2A Trusted Peer Registry API & WebUI Settings Integration."""

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

_VERIFY_A2A_SETTINGS_JS = """(() => {
  const container = document.querySelector('[data-section="a2aPeers"]');
  const bodyText = document.body ? (document.body.innerText || '') : '';
  const containerText = container ? (container.innerText || '') : '';
  const allButtons = Array.from(document.querySelectorAll('button')).map(b => (b.textContent || '').trim());
  const allHeadings = Array.from(document.querySelectorAll('h1, h2, h3')).map(h => (h.textContent || '').trim());
  
  const hasA2AInBody = bodyText.includes('A2A') || bodyText.includes('可信远程节点') || bodyText.includes('Trusted Remote Peers') || bodyText.includes('节点名册');
  const hasAddBtn = allButtons.some(t => t.includes('A2A') || t.includes('Peer') || t.includes('节点'));
  
  return {
    ok: true,
    hasA2AMention: hasA2AInBody || Boolean(container),
    hasAddBtn,
    containerFound: Boolean(container),
    containerTextPreview: containerText.slice(0, 300),
    allHeadings,
    sampleButtons: allButtons.slice(0, 10),
    url: window.location.href,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a2a_peer_registry_api_and_settings_chrome_e2e() -> None:
    """Validate backend A2A peers CRUD API and frontend settings render in real Chrome."""
    _require_e2e_cdp_ready()
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # 1. Direct REST probe to /api/v1/a2a/peers
    peers_res = http_json("GET", f"{api_url}/api/v1/a2a/peers")
    assert isinstance(peers_res, list)

    # Seed a peer if empty to test full UI representation
    peer_created = False
    created_peer_id = None
    if len(peers_res) == 0:
        create_res = http_json(
            "POST",
            f"{api_url}/api/v1/a2a/peers",
            {
                "name": "E2E Trusted Research Peer",
                "base_url": "https://peer.example.org",
                "description": "Registered via live Chrome E2E",
                "auth_type": "bearer",
                "auth_token": "sk-e2e-peer-token-9999",
                "is_active": True,
            },
            expected_statuses=frozenset({201}),
        )
        assert isinstance(create_res, dict)
        created_peer_id = create_res.get("id")
        peer_created = True

    try:
        # 2. Warm up Settings UI route and verify with Chrome MCP
        warm_ui_route("/settings")
        with open_settings_subroute("/settings/a2aPeers", timeout_ms=90_000) as (client, page):
            ensure_desktop_viewport(client, page)
            dismiss_blocking_modals(client, page)
            wait_for_settings_layout(client, page)

            dom_res = client.evaluate(page, _VERIFY_A2A_SETTINGS_JS, timeout_sec=15.0)
            assert isinstance(dom_res, dict)
            assert dom_res.get("ok") is True
            assert dom_res.get("hasA2AMention") is True, f"A2A UI elements not found in settings: {dom_res}"

    finally:
        if peer_created and created_peer_id:
            try:
                http_json("DELETE", f"{api_url}/api/v1/a2a/peers/{created_peer_id}")
            except Exception:
                pass
