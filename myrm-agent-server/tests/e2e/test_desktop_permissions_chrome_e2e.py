"""Chrome READ E2E: Desktop Automation Readiness card (permissions + capture probe).

Verifies Settings > System renders the local-mode DesktopPermissionsCard and that
Recheck hits ``GET /webui/desktop/permissions?probe_capture=true`` so
``screen_recording_capturable`` leaves the unverified (null) state.
"""

from __future__ import annotations

import json

import pytest

from tests.support.chrome_mcp_e2e import (
    _warm_ui_parallel_wait_sec,
    dismiss_blocking_modals,
    get_e2e_api_url,
    open_settings_subroute,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  return { ok: true };
})()"""

_SETTINGS_SHELL_STATE = """(() => {
  const bodyText = document.body.innerText || '';
  return {
    ready:
      location.pathname.startsWith('/settings') &&
      bodyText.length > 20 &&
      !!document.querySelector('[data-testid="settings-layout"]'),
    pathname: location.pathname,
    bodyLength: bodyText.length,
  };
})()"""

_DESKTOP_PERMISSIONS_CARD_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTitle = /Desktop Automation Readiness|桌面自动化就绪|桌面自動化就緒/.test(text);
  const hasInput = /Input Control|输入控制|輸入控制|入力制御|Eingabesteuerung|입력 제어|辅助功能|輔助功能/.test(text);
  const hasCapture = /Screen Capture|屏幕录制|螢幕錄製|画面収録|Bildschirmaufnahme|화면 기록|Capture usable|捕获可用|擷取可用|屏幕捕获|螢幕擷取/.test(text);
  const headerReady = /All capabilities ready|所有能力就绪|所有能力就緒|全部就绪|全部就緒|Permissions granted|权限已授予|許可權已授予|Screen capture unavailable|屏幕捕获不可用|螢幕擷取不可用|Setup required|桌面自动化需要配置|桌面自動化需要配置|需要设置|需要設定|Checking environment|正在检测环境|正在檢測環境|正在检查|正在檢查/.test(text);
  return {
    ready: hasTitle && hasInput && hasCapture && headerReady,
    hasTitle,
    hasInput,
    hasCapture,
    headerReady,
    snippet: text.slice(0, 1200),
  };
})()"""

_INSTALL_PERMISSIONS_FETCH_HOOK_JS = """(() => {
  if (window.__MYRM_E2E_PERM_HOOK__) {
    return { ok: true, already: true };
  }
  const hits = [];
  const originalFetch = window.fetch.bind(window);
  window.fetch = async (...args) => {
    const input = args[0];
    const url = typeof input === 'string' ? input : (input && input.url) || '';
    if (typeof url === 'string' && url.includes('/webui/desktop/permissions')) {
      hits.push(url);
    }
    return originalFetch(...args);
  };
  window.__MYRM_E2E_PERM_HOOK__ = { hits };
  return { ok: true, already: false };
})()"""

_CLICK_RECHECK_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const match = buttons.find((btn) => {
    const title = (btn.getAttribute('title') || '') + ' ' + (btn.getAttribute('aria-label') || '');
    return /Recheck|重新检查|重新檢查|再検査|Erneut prüfen|다시 확인|capture|捕获|擷取|Bildschirm|캡처/.test(title);
  });
  if (!match) {
    return { ok: false, reason: 'recheck_button_not_found' };
  }
  match.click();
  return { ok: true };
})()"""

_AFTER_RECHECK_STATE_JS = """(() => {
  const hook = window.__MYRM_E2E_PERM_HOOK__;
  const hits = Array.isArray(hook?.hits) ? hook.hits : [];
  const probed = hits.some((u) => String(u).includes('probe_capture=true'));
  const text = document.body?.innerText || '';
  const stillChecking = /Checking environment|正在检测环境|正在檢測環境|正在检查|正在檢查/.test(text) &&
    !/All capabilities ready|所有能力就绪|所有能力就緒|全部就绪|全部就緒|Permissions granted|权限已授予|許可權已授予|Screen capture unavailable|屏幕捕获不可用|螢幕擷取不可用|Setup required|桌面自动化需要配置|桌面自動化需要配置|需要设置|需要設定/.test(text);
  const captureRowSettled = /Capture usable|捕获可用|擷取可用|Capture functional|OK|Missing|缺失|未验证|未驗證|Not verified|不可用/.test(text);
  return {
    ready: probed && !stillChecking && captureRowSettled,
    probed,
    stillChecking,
    captureRowSettled,
    hitCount: hits.length,
    lastHit: hits.length ? hits[hits.length - 1] : null,
    snippet: text.slice(0, 1200),
  };
})()"""


# SHARED+READ: settings card only; do not PRIVATE (profile SSOT: no exclusive write).
# When workspace harness drifts, heal shared :8080 with zero leases — do not epoch-skip forever.
@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_desktop_permissions_card_recheck_probes_capture() -> None:
    """Desktop permissions card must render and Recheck must probe capture."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    warm_ui_route("/settings")
    warm_ui_route(
        "/settings/system",
        timeout_sec=_warm_ui_parallel_wait_sec(180.0),
    )
    with open_settings_subroute(
        "/settings/system",
        timeout_ms=120_000,
    ) as (client, page):
        client.evaluate(page, _DISMISS_MIGRATION_JS, timeout_sec=15.0)
        dismiss_blocking_modals(client, page)

        shell = wait_for_state(
            client,
            page,
            _SETTINGS_SHELL_STATE,
            timeout_sec=_warm_ui_parallel_wait_sec(120.0),
        )
        assert shell.get("ready") is True, json.dumps(shell, indent=2, ensure_ascii=False)

        card = wait_for_state(
            client,
            page,
            _DESKTOP_PERMISSIONS_CARD_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert card.get("ready") is True, json.dumps(card, indent=2, ensure_ascii=False)

        hook = client.evaluate(page, _INSTALL_PERMISSIONS_FETCH_HOOK_JS, timeout_sec=15.0)
        assert isinstance(hook, dict) and hook.get("ok") is True, hook

        click = client.evaluate(page, _CLICK_RECHECK_JS, timeout_sec=15.0)
        assert isinstance(click, dict) and click.get("ok") is True, click

        after = wait_for_state(
            client,
            page,
            _AFTER_RECHECK_STATE_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert after.get("ready") is True, json.dumps(after, indent=2, ensure_ascii=False)
        assert after.get("probed") is True
