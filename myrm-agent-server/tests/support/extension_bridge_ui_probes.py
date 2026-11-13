"""Scripts the Chrome e2e tests run inside the Settings → Browser Extension page, and the API calls that prepare it."""

from __future__ import annotations

import time

from tests.support.chrome_mcp_e2e import http_json

EXTENSION_BRIDGE_STATE = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  const bodyText = root?.innerText || '';
  const fetchErrorVisible = /无法连接服务器|Unable to connect to the server/i.test(bodyText);
  const matrixLabels = ['URL 导航', '标签页发现', 'Agent 标签页控制',
    'URL navigation', 'Tab discovery', 'Agent tab control'];
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
      matrixHits.length >= 3 &&
      unavailableHits >= 3 &&
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


CONNECTED_BRIDGE_STATE = """(() => {
  const root = document.querySelector('[data-section="extensionBridge"][data-active]');
  const bodyText = root?.innerText || '';
  const fetchErrorVisible = /无法连接服务器|Unable to connect to the server/i.test(bodyText);
  const matrixLabels = ['URL 导航', '标签页发现', 'Agent 标签页控制',
    'URL navigation', 'Tab discovery', 'Agent tab control'];
  const matrixHits = matrixLabels.filter((label) => bodyText.includes(label));
  const availableHits = (bodyText.match(/可用|Available/g) || []).length;
  const relayLine = (bodyText.match(/(私网中继能力|私網中繼能力|Private-network relay capability)[^\\n]*/i) || [])[0] || '';
  return {
    ready:
      !!root &&
      location.pathname.includes('/settings/extensionBridge') &&
      !fetchErrorVisible &&
      matrixHits.length >= 3 &&
      availableHits >= 3 &&
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


ACCESS_POLICY_INVALID_STATE = """(() => {
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


ADD_EXAMPLE_DOMAIN_JS = """(() => {
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


ACCESS_POLICY_VALID_AFTER_DOMAIN = """(() => {
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


TOGGLE_ALLOW_ALL_JS = """(() => {
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


ACCESS_POLICY_VALID_ALLOW_ALL = """(() => {
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


AVAILABLE_TABS_STATE = """(() => {
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


PAUSE_STUB_TAB_JS = """(() => {
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


TAB_PAUSED_STATE = """(() => {
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


REMOVE_EXAMPLE_DOMAIN_JS = """(() => {
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


def reset_access_policy(api_url: str) -> None:
    http_json(
        "PUT",
        f"{api_url}/api/v1/extension/access-policy",
        {
            "allow_all_eligible_tabs": False,
            "domains": [],
            "paused_tab_ids": [],
        },
    )


def wait_stub_tabs_visible(api_url: str, *, timeout_sec: float = 20.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        status = http_json("GET", f"{api_url}/api/v1/extension/status")
        if isinstance(status, dict):
            tabs = status.get("available_tabs")
            if isinstance(tabs, list) and len(tabs) > 0:
                return status
        time.sleep(0.3)
    raise TimeoutError("Extension stub tabs not visible in /extension/status")
