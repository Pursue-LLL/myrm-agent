"""Chrome MCP E2E: Browser Doctor card in Settings > System.

Verifies the Browser Doctor diagnostics card renders and executes a real
diagnosis round trip against the backend:
1. Settings/System page loads and the Browser Doctor card is visible
2. Running diagnostics renders the check report (Patchright check present)
3. The report renders the healthy/unhealthy status badge
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

_BROWSER_DOCTOR_CARD_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTitle = /Browser Diagnostics|浏览器诊断/.test(text);
  const hasRunButton = /Run diagnostics|运行诊断/.test(text);
  const hasLaunchSwitch = /Include launch test|包含启动测试/.test(text);
  return {
    ready: hasTitle && hasRunButton && hasLaunchSwitch,
    hasTitle,
    hasRunButton,
    hasLaunchSwitch,
    snippet: text.slice(0, 800),
  };
})()"""

_BROWSER_DOCTOR_REPORT_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasPatchright = /Patchright Engine|Patchright 引擎/.test(text);
  const hasBadge = /Browser stack healthy|浏览器栈正常|Issues detected|发现问题/.test(text);
  return {
    ready: hasPatchright && hasBadge,
    hasPatchright,
    hasBadge,
    snippet: text.slice(0, 1200),
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_chrome_ui_browser_doctor_card_renders_report() -> None:
    """Browser Doctor card must render and surface a real diagnosis report."""
    api_url = get_e2e_api_url()
    prepare_e2e_ui_session(api_url)

    # System tab pulls a heavy bundle — warm parent routes first (settings E2E pattern).
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
            _BROWSER_DOCTOR_CARD_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(90.0),
        )
        assert card.get("ready") is True, json.dumps(card, indent=2, ensure_ascii=False)
        assert card.get("hasTitle") is True
        assert card.get("hasRunButton") is True
        assert card.get("hasLaunchSwitch") is True

        report = wait_for_state(
            client,
            page,
            _BROWSER_DOCTOR_REPORT_JS,
            timeout_sec=_warm_ui_parallel_wait_sec(180.0),
        )
        assert report.get("ready") is True, json.dumps(report, indent=2, ensure_ascii=False)
        assert report.get("hasPatchright") is True
        assert report.get("hasBadge") is True
