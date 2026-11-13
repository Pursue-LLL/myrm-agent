"""Real Chrome MCP E2E for Settings → Browser Extension Bridge relay contract UI."""

from __future__ import annotations

from urllib.parse import urlparse

import pytest
from e2e_core.dev_ports import shared_backend_port

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_settings_layout,
    wait_for_state,
    warm_ui_route,
)
from tests.support.extension_bridge_ui_probes import (
    ACCESS_POLICY_INVALID_STATE,
    ACCESS_POLICY_VALID_AFTER_DOMAIN,
    ACCESS_POLICY_VALID_ALLOW_ALL,
    ADD_EXAMPLE_DOMAIN_JS,
    AVAILABLE_TABS_STATE,
    CONNECTED_BRIDGE_STATE,
    EXTENSION_BRIDGE_STATE,
    PAUSE_STUB_TAB_JS,
    REMOVE_EXAMPLE_DOMAIN_JS,
    TAB_PAUSED_STATE,
    TOGGLE_ALLOW_ALL_JS,
    reset_access_policy,
    wait_stub_tabs_visible,
)
from tests.support.extension_bridge_ws_stub import hold_extension_bridge_session


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_extension_bridge_settings_relay_contract_in_real_ui() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    api_port = urlparse(api_url).port or shared_backend_port()

    status = http_json("GET", f"{api_url}/api/v1/extension/status")
    assert isinstance(status, dict)
    assert status.get("connected") is False
    assert status.get("handshake_ready") is False
    assert status.get("capabilities") == []

    http_json("POST", f"{api_url}/api/v1/extension/disconnect")

    hints = http_json("GET", f"{api_url}/api/v1/extension/setup-hints")
    assert isinstance(hints, dict)
    assert "auth_token_configured" in hints
    assert "cdp_endpoint_discovered" in hints
    assert "relay_cdp_ready" in hints
    assert "access_policy_valid" in hints

    warm_ui_route("/settings/extensionBridge")
    bridge_url = f"{ui_url.rstrip('/')}/settings/extensionBridge"

    prepare_e2e_ui_session(api_url)

    with open_settings_subroute(bridge_url, timeout_ms=90_000) as (client, page):
        dismiss_blocking_modals(client, page)
        wait_for_settings_layout(
            client,
            page,
            page_url=bridge_url,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        client.navigate(page, bridge_url, timeout_ms=90_000)
        dismiss_blocking_modals(client, page)
        state = wait_for_state(
            client,
            page,
            EXTENSION_BRIDGE_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            page_url=bridge_url,
        )
        assert state.get("fetchErrorVisible") is not True, state
        assert state.get("hasActiveSection") is True, state
        assert int(state.get("matrixHits") or 0) >= 3, state
        assert int(state.get("unavailableHits") or 0) >= 3, state
        ws_url = str(state.get("wsUrl") or "")
        assert f":{api_port}/api/v1/ws/extension" in ws_url, state
        heading = str(state.get("heading") or "")
        assert "浏览器扩展桥接" in heading or "Browser Extension" in heading, state


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_extension_bridge_settings_relay_contract_connected_in_real_ui() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    http_json("POST", f"{api_url}/api/v1/extension/disconnect")

    with hold_extension_bridge_session(api_url):
        status = http_json("GET", f"{api_url}/api/v1/extension/status")
        assert isinstance(status, dict)
        assert status.get("connected") is True
        assert status.get("handshake_ready") is True
        assert set(status.get("capabilities") or []) >= {
            "navigate_url",
            "list_tabs",
            "agent_tab_control",
        }

        with open_settings_subroute(f"{ui_url.rstrip('/')}/settings/extensionBridge", timeout_ms=90_000) as (client, page):
            bridge_url = f"{ui_url.rstrip('/')}/settings/extensionBridge"
            dismiss_blocking_modals(client, page)
            wait_for_settings_layout(
                client,
                page,
                page_url=bridge_url,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            )
            client.navigate(page, bridge_url, timeout_ms=90_000)
            dismiss_blocking_modals(client, page)
            state = wait_for_state(
                client,
                page,
                CONNECTED_BRIDGE_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert state.get("fetchErrorVisible") is not True, state
            assert state.get("hasActiveSection") is True, state
            assert int(state.get("matrixHits") or 0) >= 3, state
            assert int(state.get("availableHits") or 0) >= 3, state
            relay_line = str(state.get("relayLine") or "")
            assert "已就绪" in relay_line or "Ready" in relay_line, state


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_extension_bridge_access_policy_add_domain_in_real_ui() -> None:
    """Settings UI: empty policy shows invalid help; adding a domain clears it."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    http_json("POST", f"{api_url}/api/v1/extension/disconnect")
    reset_access_policy(api_url)

    with hold_extension_bridge_session(api_url):
        with open_settings_subroute(f"{ui_url.rstrip('/')}/settings/extensionBridge", timeout_ms=90_000) as (client, page):
            bridge_url = f"{ui_url.rstrip('/')}/settings/extensionBridge"
            dismiss_blocking_modals(client, page)
            wait_for_settings_layout(
                client,
                page,
                page_url=bridge_url,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            )
            client.navigate(page, bridge_url, timeout_ms=90_000)
            dismiss_blocking_modals(client, page)

            invalid_state = wait_for_state(
                client,
                page,
                ACCESS_POLICY_INVALID_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert invalid_state.get("invalidHelp") is True, invalid_state

            add_result = client.evaluate(page, ADD_EXAMPLE_DOMAIN_JS, timeout_sec=30.0)
            assert isinstance(add_result, dict) and add_result.get("ok") is True, add_result

            valid_state = wait_for_state(
                client,
                page,
                ACCESS_POLICY_VALID_AFTER_DOMAIN,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert valid_state.get("hasDomain") is True, valid_state
            assert valid_state.get("invalidHelp") is not True, valid_state

        hints = http_json("GET", f"{api_url}/api/v1/extension/setup-hints")
        assert isinstance(hints, dict)
        assert hints.get("access_policy_valid") is True

        refreshed = http_json("GET", f"{api_url}/api/v1/extension/status")
        assert isinstance(refreshed, dict)
        assert refreshed.get("access_policy_valid") is True
        assert "*.example.com" in (refreshed.get("authorized_domains") or [])

    reset_access_policy(api_url)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_extension_bridge_access_policy_allow_all_toggle_in_real_ui() -> None:
    """Settings UI: allow-all switch satisfies access policy without domains."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    http_json("POST", f"{api_url}/api/v1/extension/disconnect")
    reset_access_policy(api_url)

    with hold_extension_bridge_session(api_url):
        with open_settings_subroute(f"{ui_url.rstrip('/')}/settings/extensionBridge", timeout_ms=90_000) as (client, page):
            bridge_url = f"{ui_url.rstrip('/')}/settings/extensionBridge"
            dismiss_blocking_modals(client, page)
            wait_for_settings_layout(
                client,
                page,
                page_url=bridge_url,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            )
            client.navigate(page, bridge_url, timeout_ms=90_000)
            dismiss_blocking_modals(client, page)

            wait_for_state(
                client,
                page,
                ACCESS_POLICY_INVALID_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )

            toggle = client.evaluate(page, TOGGLE_ALLOW_ALL_JS, timeout_sec=30.0)
            assert isinstance(toggle, dict) and toggle.get("ok") is True, toggle

            valid_state = wait_for_state(
                client,
                page,
                ACCESS_POLICY_VALID_ALLOW_ALL,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert valid_state.get("switchState") == "checked", valid_state
            assert valid_state.get("invalidHelp") is not True, valid_state

        refreshed = http_json("GET", f"{api_url}/api/v1/extension/status")
        assert isinstance(refreshed, dict)
        assert refreshed.get("access_policy_valid") is True
        assert refreshed.get("allow_all_eligible_tabs") is True

    reset_access_policy(api_url)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_extension_bridge_access_policy_remove_domain_in_real_ui() -> None:
    """Settings UI: removing last domain restores invalid-policy help."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    http_json("POST", f"{api_url}/api/v1/extension/disconnect")
    http_json(
        "PUT",
        f"{api_url}/api/v1/extension/access-policy",
        {
            "allow_all_eligible_tabs": False,
            "domains": ["*.example.com"],
            "paused_tab_ids": [],
        },
    )

    with hold_extension_bridge_session(api_url):
        with open_settings_subroute(f"{ui_url.rstrip('/')}/settings/extensionBridge", timeout_ms=90_000) as (client, page):
            bridge_url = f"{ui_url.rstrip('/')}/settings/extensionBridge"
            dismiss_blocking_modals(client, page)
            wait_for_settings_layout(
                client,
                page,
                page_url=bridge_url,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            )
            client.navigate(page, bridge_url, timeout_ms=90_000)
            dismiss_blocking_modals(client, page)

            wait_for_state(
                client,
                page,
                ACCESS_POLICY_VALID_AFTER_DOMAIN,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )

            remove = client.evaluate(page, REMOVE_EXAMPLE_DOMAIN_JS, timeout_sec=30.0)
            assert isinstance(remove, dict) and remove.get("ok") is True, remove

            invalid_state = wait_for_state(
                client,
                page,
                ACCESS_POLICY_INVALID_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert invalid_state.get("invalidHelp") is True, invalid_state

        refreshed = http_json("GET", f"{api_url}/api/v1/extension/status")
        assert isinstance(refreshed, dict)
        assert refreshed.get("access_policy_valid") is False
        assert refreshed.get("authorized_domains") == []

    reset_access_policy(api_url)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="STANDARD",
    private_reason="global_write_non_namespace",
)
@pytest.mark.integration
@pytest.mark.timeout(180)
def test_extension_bridge_pause_tab_in_real_ui() -> None:
    """Settings UI: pause control marks stub tab paused in server policy."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()

    http_json("POST", f"{api_url}/api/v1/extension/disconnect")
    http_json(
        "PUT",
        f"{api_url}/api/v1/extension/access-policy",
        {
            "allow_all_eligible_tabs": True,
            "domains": [],
            "paused_tab_ids": [],
        },
    )

    with hold_extension_bridge_session(api_url):
        wait_stub_tabs_visible(api_url)

        with open_settings_subroute(f"{ui_url.rstrip('/')}/settings/extensionBridge", timeout_ms=90_000) as (client, page):
            bridge_url = f"{ui_url.rstrip('/')}/settings/extensionBridge"
            dismiss_blocking_modals(client, page)
            wait_for_settings_layout(
                client,
                page,
                page_url=bridge_url,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            )
            client.navigate(page, bridge_url, timeout_ms=90_000)
            dismiss_blocking_modals(client, page)

            tabs_state = wait_for_state(
                client,
                page,
                AVAILABLE_TABS_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert tabs_state.get("hasExampleTab") is True, tabs_state

            pause = client.evaluate(page, PAUSE_STUB_TAB_JS, timeout_sec=30.0)
            assert isinstance(pause, dict) and pause.get("ok") is True, pause

            paused_state = wait_for_state(
                client,
                page,
                TAB_PAUSED_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert paused_state.get("pausedBadge") is True, paused_state

        refreshed = http_json("GET", f"{api_url}/api/v1/extension/status")
        assert isinstance(refreshed, dict)
        assert 1001 in (refreshed.get("paused_tab_ids") or [])

    reset_access_policy(api_url)
