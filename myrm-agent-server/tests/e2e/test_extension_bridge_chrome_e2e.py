"""Real Chrome MCP E2E for Settings → Browser Extension Bridge relay contract UI."""

from __future__ import annotations

import time
from urllib.parse import urlparse

import pytest

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
from tests.support.extension_bridge_ws_stub import hold_extension_bridge_session

_EXTENSION_BRIDGE_STATE = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  const bodyText = root?.innerText || '';
  const fetchErrorVisible = /无法连接服务器|Unable to connect to the server/i.test(bodyText);
  const matrixLabels = ['URL 导航', '标签页发现', '调试器附加', '调试器分离',
    'URL navigation', 'Tab discovery', 'Debugger attach', 'Debugger detach'];
  const matrixHits = matrixLabels.filter((label) => bodyText.includes(label));
  const unavailableHits = (bodyText.match(/不可用|Unavailable/g) || []).length;
  const relayLine = (bodyText.match(/(私网中继能力|私網中繼能力|Private-network relay capability)[^\\n]*/i) || [])[0] || '';
  const wsMatch = bodyText.match(/ws:\\/\\/[^\\s]+\\/api\\/v1\\/ws\\/extension/i);
  const pairingGuideVisible =
    /加载已解压|Load unpacked|pairing bundle|配对包|Generate pairing|Quick Setup|快速设置/i.test(bodyText);
  return {
    ready:
      !!root &&
      location.pathname.includes('/settings/extensionBridge') &&
      !fetchErrorVisible &&
      matrixHits.length >= 4 &&
      unavailableHits >= 4 &&
      /未连接|Not connected/i.test(bodyText) &&
      pairingGuideVisible &&
      !!wsMatch,
    hasActiveSection: !!root,
    fetchErrorVisible,
    matrixHits: matrixHits.length,
    unavailableHits,
    relayLine,
    pairingGuideVisible,
    wsUrl: wsMatch ? wsMatch[0] : '',
    heading: root?.querySelector('h2')?.textContent || '',
    pathname: location.pathname,
  };
})()"""


_CONNECTED_BRIDGE_STATE = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  const bodyText = root?.innerText || '';
  const fetchErrorVisible = /无法连接服务器|Unable to connect to the server/i.test(bodyText);
  const matrixLabels = ['URL 导航', '标签页发现', '调试器附加', '调试器分离',
    'URL navigation', 'Tab discovery', 'Debugger attach', 'Debugger detach'];
  const matrixHits = matrixLabels.filter((label) => bodyText.includes(label));
  const availableHits = (bodyText.match(/可用|Available/g) || []).length;
  const relayLine = (bodyText.match(/(私网中继能力|私網中繼能力|Private-network relay capability)[^\\n]*/i) || [])[0] || '';
  return {
    ready:
      !!root &&
      location.pathname.includes('/settings/extensionBridge') &&
      !fetchErrorVisible &&
      matrixHits.length >= 4 &&
      availableHits >= 4 &&
      (/已连接|Connected/i.test(bodyText)) &&
      (/已就绪|Ready \\(all required actions available\\)/i.test(relayLine) ||
        /全部必需动作可用|全部必要動作可用/i.test(relayLine)),
    hasActiveSection: !!root,
    fetchErrorVisible,
    matrixHits: matrixHits.length,
    availableHits,
    relayLine,
    pathname: location.pathname,
  };
})()"""


_ACCESS_POLICY_INVALID_STATE = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  const bodyText = root?.innerText || '';
  const invalidHelp =
    /Add at least one authorized domain|请至少添加一个授权域名|請至少新增一個授權域名/i.test(bodyText);
  return {
    ready:
      !!root &&
      location.pathname.includes('/settings/extensionBridge') &&
      (/已连接|Connected/i.test(bodyText)) &&
      invalidHelp,
    invalidHelp,
    hasDomainBadge: /\\*\\.example\\.com/.test(bodyText),
    pathname: location.pathname,
  };
})()"""


_ADD_EXAMPLE_DOMAIN_JS = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  if (!root) return { ok: false, reason: 'no-root' };
  const inputs = root.querySelectorAll('input');
  let domainInput = null;
  for (const inp of inputs) {
    const ph = inp.getAttribute('placeholder') || '';
    if (/github|example|域名|domain/i.test(ph)) {
      domainInput = inp;
      break;
    }
  }
  if (!domainInput) {
    return { ok: false, reason: 'no-input', inputCount: inputs.length };
  }
  const nativeSetter = Object.getOwnPropertyDescriptor(
    window.HTMLInputElement.prototype,
    'value',
  )?.set;
  nativeSetter?.call(domainInput, '*.example.com');
  domainInput.dispatchEvent(new Event('input', { bubbles: true }));
  domainInput.dispatchEvent(new Event('change', { bubbles: true }));
  const buttons = [...root.querySelectorAll('button')];
  const addBtn = buttons.find((b) => /^(Add|添加|新增)$/i.test((b.textContent || '').trim()));
  if (!addBtn) {
    return {
      ok: false,
      reason: 'no-add-btn',
      buttons: buttons.map((b) => (b.textContent || '').trim()).slice(0, 12),
    };
  }
  addBtn.click();
  return { ok: true };
})()"""


_ACCESS_POLICY_VALID_AFTER_DOMAIN = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  const bodyText = root?.innerText || '';
  const invalidHelp =
    /Add at least one authorized domain|请至少添加一个授权域名|請至少新增一個授權域名/i.test(bodyText);
  const hasDomain = /\\*\\.example\\.com/.test(bodyText);
  return {
    ready:
      !!root &&
      (/已连接|Connected/i.test(bodyText)) &&
      hasDomain &&
      !invalidHelp,
    invalidHelp,
    hasDomain,
  };
})()"""


_TOGGLE_ALLOW_ALL_JS = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  if (!root) return { ok: false, reason: 'no-root' };
  const switchEl = root.querySelector('[role="switch"]');
  if (!switchEl) return { ok: false, reason: 'no-switch' };
  if (switchEl.getAttribute('data-state') === 'checked') {
    return { ok: true, skipped: 'already-checked' };
  }
  switchEl.click();
  return { ok: true, skipped: false };
})()"""


_ACCESS_POLICY_VALID_ALLOW_ALL = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  const bodyText = root?.innerText || '';
  const invalidHelp =
    /Add at least one authorized domain|请至少添加一个授权域名|請至少新增一個授權域名/i.test(bodyText);
  const switchEl = root?.querySelector('[role="switch"]');
  return {
    ready:
      !!root &&
      (/已连接|Connected/i.test(bodyText)) &&
      !invalidHelp &&
      switchEl?.getAttribute('data-state') === 'checked',
    invalidHelp,
    switchState: switchEl?.getAttribute('data-state') || '',
  };
})()"""


_AVAILABLE_TABS_STATE = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  const bodyText = root?.innerText || '';
  const hasExampleTab = /example\\.com/i.test(bodyText) &&
    (/Example E2E Stub Tab|e2e-stub/i.test(bodyText) || /Pause|暂停/.test(bodyText));
  return {
    ready: !!root && hasExampleTab,
    hasExampleTab,
    bodySnippet: bodyText.slice(0, 600),
  };
})()"""


_PAUSE_STUB_TAB_JS = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  if (!root) return { ok: false, reason: 'no-root' };
  const buttons = [...root.querySelectorAll('button')];
  const pauseBtn = buttons.find((b) => /^(Pause|暂停)$/i.test((b.textContent || '').trim()));
  if (!pauseBtn) {
    return {
      ok: false,
      reason: 'no-pause-btn',
      buttons: buttons.map((b) => (b.textContent || '').trim()).slice(0, 16),
    };
  }
  pauseBtn.click();
  return { ok: true };
})()"""


_TAB_PAUSED_STATE = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  const bodyText = root?.innerText || '';
  const pausedBadge = /Paused|已暂停|已暫停/i.test(bodyText);
  const resumeBtn = /Resume|恢复|恢復/i.test(bodyText);
  return {
    ready: !!root && pausedBadge && resumeBtn,
    pausedBadge,
    resumeBtn,
  };
})()"""


_REMOVE_EXAMPLE_DOMAIN_JS = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  if (!root) return { ok: false, reason: 'no-root' };
  const removeBtn = [...root.querySelectorAll('button')].find((b) => {
    const host = b.closest('div');
    return (
      (b.className || '').includes('hover:text-destructive') &&
      (host?.textContent || '').includes('*.example.com')
    );
  });
  if (!removeBtn) {
    return {
      ok: false,
      reason: 'no-remove-btn',
      sample: (root.innerText || '').slice(0, 400),
    };
  }
  removeBtn.click();
  return { ok: true };
})()"""


def _reset_access_policy(api_url: str) -> None:
    http_json(
        "PUT",
        f"{api_url}/api/v1/extension/access-policy",
        {
            "allow_all_eligible_tabs": False,
            "domains": [],
            "paused_tab_ids": [],
        },
    )


def _wait_stub_tabs_visible(api_url: str, *, timeout_sec: float = 20.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        status = http_json("GET", f"{api_url}/api/v1/extension/status")
        if isinstance(status, dict):
            tabs = status.get("available_tabs")
            if isinstance(tabs, list) and len(tabs) > 0:
                return status
        time.sleep(0.3)
    raise TimeoutError("Extension stub tabs not visible in /extension/status")


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
    api_port = urlparse(api_url).port or 8080

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
            _EXTENSION_BRIDGE_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
            page_url=bridge_url,
        )
        assert state.get("fetchErrorVisible") is not True, state
        assert state.get("hasActiveSection") is True, state
        assert int(state.get("matrixHits") or 0) >= 4, state
        assert int(state.get("unavailableHits") or 0) >= 4, state
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
            "attach_debugger",
            "detach_debugger",
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
                _CONNECTED_BRIDGE_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert state.get("fetchErrorVisible") is not True, state
            assert state.get("hasActiveSection") is True, state
            assert int(state.get("matrixHits") or 0) >= 4, state
            assert int(state.get("availableHits") or 0) >= 4, state
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
    _reset_access_policy(api_url)

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
                _ACCESS_POLICY_INVALID_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert invalid_state.get("invalidHelp") is True, invalid_state

            add_result = client.evaluate(page, _ADD_EXAMPLE_DOMAIN_JS, timeout_sec=30.0)
            assert isinstance(add_result, dict) and add_result.get("ok") is True, add_result

            valid_state = wait_for_state(
                client,
                page,
                _ACCESS_POLICY_VALID_AFTER_DOMAIN,
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

    _reset_access_policy(api_url)


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
    _reset_access_policy(api_url)

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
                _ACCESS_POLICY_INVALID_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )

            toggle = client.evaluate(page, _TOGGLE_ALLOW_ALL_JS, timeout_sec=30.0)
            assert isinstance(toggle, dict) and toggle.get("ok") is True, toggle

            valid_state = wait_for_state(
                client,
                page,
                _ACCESS_POLICY_VALID_ALLOW_ALL,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert valid_state.get("switchState") == "checked", valid_state
            assert valid_state.get("invalidHelp") is not True, valid_state

        refreshed = http_json("GET", f"{api_url}/api/v1/extension/status")
        assert isinstance(refreshed, dict)
        assert refreshed.get("access_policy_valid") is True
        assert refreshed.get("allow_all_eligible_tabs") is True

    _reset_access_policy(api_url)


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
                _ACCESS_POLICY_VALID_AFTER_DOMAIN,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )

            remove = client.evaluate(page, _REMOVE_EXAMPLE_DOMAIN_JS, timeout_sec=30.0)
            assert isinstance(remove, dict) and remove.get("ok") is True, remove

            invalid_state = wait_for_state(
                client,
                page,
                _ACCESS_POLICY_INVALID_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert invalid_state.get("invalidHelp") is True, invalid_state

        refreshed = http_json("GET", f"{api_url}/api/v1/extension/status")
        assert isinstance(refreshed, dict)
        assert refreshed.get("access_policy_valid") is False
        assert refreshed.get("authorized_domains") == []

    _reset_access_policy(api_url)


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
        _wait_stub_tabs_visible(api_url)

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
                _AVAILABLE_TABS_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert tabs_state.get("hasExampleTab") is True, tabs_state

            pause = client.evaluate(page, _PAUSE_STUB_TAB_JS, timeout_sec=30.0)
            assert isinstance(pause, dict) and pause.get("ok") is True, pause

            paused_state = wait_for_state(
                client,
                page,
                _TAB_PAUSED_STATE,
                timeout_sec=_warm_ui_parallel_wait_sec(90.0),
                page_url=bridge_url,
            )
            assert paused_state.get("pausedBadge") is True, paused_state

        refreshed = http_json("GET", f"{api_url}/api/v1/extension/status")
        assert isinstance(refreshed, dict)
        assert 1001 in (refreshed.get("paused_tab_ids") or [])

    _reset_access_policy(api_url)
