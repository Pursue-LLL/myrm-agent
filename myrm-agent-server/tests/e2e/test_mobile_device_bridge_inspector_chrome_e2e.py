"""Real Chrome MCP E2E: Mobile Device Bridge Inspector panel lifecycle & touch relay contract."""

from __future__ import annotations

import pytest

from tests.support.chrome_mcp_e2e import (
    _require_e2e_cdp_ready,
    dismiss_blocking_modals,
    ensure_desktop_viewport,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_react_e2e_bridge,
    warm_ui_route,
)

_VERIFY_DEVICE_STORE_AND_PANEL_JS = """(() => {
  const store = window.__MYRM_DEVICE_INSPECTOR_STORE__;
  if (!store) {
    // If not on window, check if toggle button or state can be engaged
    return { ok: false, err: 'no-device-store-exposed' };
  }
  const state = store.getState();
  const initialOpen = state.isOpen;

  // Open panel
  state.openPanel();
  const afterOpen = store.getState().isOpen;

  // Set mode to inspect
  state.setMode('inspect');
  const inspectMode = store.getState().mode === 'inspect';

  // Toggle notification redaction
  const initialRedaction = store.getState().notificationRedaction;
  state.setNotificationRedaction(!initialRedaction);
  const toggledRedaction = store.getState().notificationRedaction !== initialRedaction;
  state.setNotificationRedaction(initialRedaction); // restore

  // Close panel
  state.closePanel();
  const afterClose = !store.getState().isOpen;

  return {
    ok: true,
    initialOpen,
    afterOpen,
    inspectMode,
    toggledRedaction,
    afterClose,
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="SHARED",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_mobile_device_inspector_api_and_ui_lifecycle() -> None:
    """Validate backend device bridge REST contracts (/doctor, /snapshot, /relay) and frontend inspector store."""
    _require_e2e_cdp_ready()
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    # 1. Verify backend REST endpoints directly on live server
    doctor_res = http_json("GET", f"{api_url}/webui/device/doctor")
    assert isinstance(doctor_res, dict)
    assert "adb_available" in doctor_res
    assert "devices" in doctor_res

    snapshot_res = http_json("GET", f"{api_url}/webui/device/snapshot")
    assert isinstance(snapshot_res, dict)
    assert "screenshot_base64" in snapshot_res
    assert "viewport_width" in snapshot_res
    assert "connected" in snapshot_res

    relay_res = http_json(
        "POST",
        f"{api_url}/webui/device/relay",
        body={"action": "tap", "x": 500, "y": 1000},
    )
    assert isinstance(relay_res, dict)
    assert relay_res.get("action") == "tap"

    # 2. Warm up UI route and inspect page state
    warm_ui_route("/")
    session = "mobile_inspector_e2e"
    with open_mcp_page(f"{ui_url}/?chat={session}") as (client, page):
        ensure_desktop_viewport(client, page)
        dismiss_blocking_modals(client, page)
        wait_for_react_e2e_bridge(client, page)

        # 3. Verify window.__MYRM_DEVICE_INSPECTOR_STORE__ interaction in real browser
        store_res = client.evaluate(page, _VERIFY_DEVICE_STORE_AND_PANEL_JS, timeout_sec=10.0)
        assert isinstance(store_res, dict)
        assert store_res.get("ok")
        assert store_res.get("afterOpen") is True
        assert store_res.get("inspectMode") is True
        assert store_res.get("toggledRedaction") is True
        assert store_res.get("afterClose") is True
