"""Chrome MCP E2E: Desktop Automation Readiness on Settings > System.

Verifies the real WebUI path for topic_05 #1 (permissions + capture readiness):
1. Settings/System loads and Desktop Automation Readiness card is visible
2. First paint settles into a user-facing readiness tone (verified / unverified / missing)
3. Recheck triggers probe_capture and the card remains coherent with the live API
"""

from __future__ import annotations

import json

import pytest
import urllib.request

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
  const hasTitle = /Desktop Automation Readiness|桌面自动化就绪/.test(text);
  const hasVerified = /All capabilities ready|全部能力就绪/.test(text);
  const hasUnverified = /capture not verified|捕获尚未验证|擷取尚未驗證/.test(text);
  const hasMissing = /Setup required for desktop automation|需要完成桌面自动化设置|需完成桌面自動化設定/.test(
    text,
  );
  const hasChecking = /Checking environment|正在检查环境|正在檢查環境/.test(text);
  const tone = hasVerified
    ? 'verified'
    : hasUnverified
      ? 'unverified'
      : hasMissing
        ? 'missing'
        : hasChecking
          ? 'checking'
          : 'unknown';
  return {
    ready: hasTitle && tone !== 'unknown' && tone !== 'checking',
    hasTitle,
    tone,
    snippet: text.slice(0, 1200),
  };
})()"""

_CLICK_RECHECK_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const recheck = buttons.find((btn) => {
    const title = (btn.getAttribute('title') || '').toLowerCase();
    const label = (btn.getAttribute('aria-label') || '').toLowerCase();
    return (
      title.includes('recheck') ||
      title.includes('重新检查') ||
      title.includes('重新檢查') ||
      label.includes('recheck')
    );
  });
  if (!recheck) {
    return { ok: false, reason: 'recheck_button_not_found' };
  }
  recheck.click();
  return { ok: true };
})()"""


def _fetch_permissions(*, probe_capture: bool) -> dict[str, object]:
    api = get_e2e_api_url().rstrip("/")
    suffix = "?probe_capture=true" if probe_capture else ""
    url = f"{api}/webui/desktop/permissions{suffix}"
    with urllib.request.urlopen(url, timeout=30) as resp:
        payload = json.loads(resp.read().decode("utf-8"))
    assert isinstance(payload, dict), payload
    return payload


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_desktop_permissions_card_three_state_and_recheck() -> None:
    """Desktop permissions card must show honest readiness and survive recheck."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    baseline = _fetch_permissions(probe_capture=False)
    assert "capture_ready" in baseline
    assert "screen_recording_capturable" in baseline
    assert baseline.get("capture_ready") is False or baseline.get(
        "screen_recording_capturable"
    ) is True
    if baseline.get("screen_recording_capturable") is None:
        assert baseline.get("capture_ready") is False

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
        assert card.get("hasTitle") is True
        assert card.get("tone") in {"verified", "unverified", "missing"}

        click = client.evaluate(page, _CLICK_RECHECK_JS, timeout_sec=15.0)
        assert isinstance(click, dict) and click.get("ok") is True, click

        after = wait_for_state(
            client,
            page,
            _DESKTOP_PERMISSIONS_CARD_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert after.get("ready") is True, json.dumps(after, indent=2, ensure_ascii=False)
        assert after.get("tone") in {"verified", "unverified", "missing"}

        probed = _fetch_permissions(probe_capture=True)
        capturable = probed.get("screen_recording_capturable")
        capture_ready = probed.get("capture_ready")
        assert capturable is True or capturable is False
        assert capture_ready is (probed.get("all_granted") is True and capturable is True)

        if capture_ready is True:
            assert after.get("tone") == "verified"
        elif probed.get("all_granted") is True and capturable is False:
            assert after.get("tone") == "missing"
        elif probed.get("all_granted") is not True:
            assert after.get("tone") == "missing"
