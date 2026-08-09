"""Real Chrome MCP E2E for browser takeover in-chat banner (extension / CDP path)."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    deny_stale_browser_takeover_approvals,
    ensure_e2e_memory_disabled,
    ensure_e2e_yolo_mode,
    wait_e2e_backend_ready,
    wait_e2e_cdp_ready,
    wait_e2e_provider_ready,
)
from e2e_live_flows.browser_takeover_live_flow import (  # noqa: E402
    run_browser_takeover_live_flow,
)
from e2e_live_flows.browser_takeover_live_runner import (  # noqa: E402
    run_browser_takeover_live_session,
)

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, open_mcp_page, wait_for_state
from tests.support.e2e_runtime_guard import E2EResourceLedger

_BRIDGE_READY_JS = """(() => ({
  ready:
    typeof window.__MYRM_E2E_CHAT__?.triggerBrowserTakeover === 'function' &&
    typeof window.__MYRM_E2E_CHAT__?.getBrowserTakeoverSnapshot === 'function',
}))()"""

_TRIGGER_EXTENSION_TAKEOVER_JS = """(() => {
  window.__MYRM_E2E_CHAT__?.triggerBrowserTakeover?.({
    reason: 'E2E: complete login in your Chrome window',
    ui_mode: 'extension',
    auto_detect_completion: false,
    messageId: 'e2e-takeover-extension',
    url: 'https://example.com/login',
  });
  return window.__MYRM_E2E_CHAT__?.getBrowserTakeoverSnapshot?.() ?? null;
})()"""

_TRIGGER_CAPTCHA_AUTO_JS = """(() => {
  window.__MYRM_E2E_CHAT__?.triggerBrowserTakeover?.({
    reason: 'E2E: captcha auto-detect running',
    ui_mode: 'extension',
    auto_detect_completion: true,
    messageId: 'e2e-takeover-captcha',
  });
  return window.__MYRM_E2E_CHAT__?.getBrowserTakeoverSnapshot?.() ?? null;
})()"""

_BANNER_ASSERT_JS = """(() => {
  const alert = document.querySelector('[role="alert"]');
  const text = alert?.innerText || '';
  const backendUnreachable = /后端未响应|Backend not reachable|API_PORT=8080/i.test(text);
  if (backendUnreachable) {
    return {
      ready: false,
      backendUnreachable: true,
      hasAlert: true,
      sample: text.slice(0, 240),
    };
  }
  const buttons = alert ? Array.from(alert.querySelectorAll('button')) : [];
  const labels = buttons.map((btn) => (btn.textContent || '').trim());
  const hasAlert = !!alert;
  const hasExtensionTitle = /Your turn in Chrome|请在 Chrome 中完成操作/i.test(text);
  const hasReason = /请在 Chrome 完成操作|Please click Done|E2E:/i.test(text);
  const hasUrl = /example\\.com/i.test(text);
  const hasDone = labels.some((label) => /Done|完成/i.test(label));
  const hasSkip = labels.some((label) => /Can't do this|无法完成/i.test(label));
  const snap = window.__MYRM_E2E_CHAT__?.getBrowserTakeoverSnapshot?.();
  const storePending = snap?.pending === true && snap?.uiMode === 'extension';
  const ready = (hasAlert && hasExtensionTitle && hasDone && hasSkip) || storePending;
  return {
    ready,
    backendUnreachable: false,
    hasAlert,
    hasExtensionTitle,
    hasReason,
    hasUrl,
    hasDone,
    hasSkip,
    storePending,
    storeUiMode: snap?.pending ? snap?.uiMode ?? null : null,
    storeReason: snap?.reason ?? null,
    buttonCount: buttons.length,
    sample: text.slice(0, 240),
  };
})()"""

_CAPTCHA_AUTO_ASSERT_JS = """(() => {
  const alert = document.querySelector('[role="alert"]');
  const text = alert?.innerText || '';
  const buttons = alert ? Array.from(alert.querySelectorAll('button')) : [];
  const hasAlert = !!alert;
  const hasCaptchaText = /auto|自动|Captcha|captcha/i.test(text);
  const buttonCount = buttons.length;
  return {
    ready: hasAlert && hasCaptchaText && buttonCount === 0,
    hasAlert,
    hasCaptchaText,
    buttonCount,
  };
})()"""

_CLICK_DONE_JS = """(() => {
  const alert = document.querySelector('[role="alert"]');
  if (!alert) {
    return { clicked: false, reason: 'no-alert' };
  }
  const doneBtn = Array.from(alert.querySelectorAll('button')).find((btn) =>
    /Done|完成/i.test(btn.textContent || ''),
  );
  if (!doneBtn) {
    return { clicked: false, reason: 'no-done-button' };
  }
  doneBtn.click();
  return { clicked: true };
})()"""

_CLICK_SKIP_JS = """(() => {
  const alert = document.querySelector('[role="alert"]');
  if (!alert) {
    return { clicked: false, reason: 'no-alert' };
  }
  const skipBtn = Array.from(alert.querySelectorAll('button')).find((btn) =>
    /Can't do this|无法完成/i.test(btn.textContent || ''),
  );
  if (!skipBtn) {
    return { clicked: false, reason: 'no-skip-button' };
  }
  skipBtn.click();
  return { clicked: true };
})()"""

_SNAPSHOT_IDLE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.getBrowserTakeoverSnapshot?.();
  return {
    pending: snap?.pending ?? null,
    uiMode: snap?.uiMode ?? null,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
def test_extension_takeover_banner_shows_actions_and_dismisses_on_done() -> None:
    ui_url = get_e2e_ui_url()

    with open_mcp_page(ui_url) as (client, page):
        wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=60.0)

        triggered = client.evaluate(
            page, _TRIGGER_EXTENSION_TAKEOVER_JS, timeout_sec=10.0
        )
        assert isinstance(triggered, dict)
        assert triggered.get("pending") is True
        assert triggered.get("uiMode") == "extension"

        banner = wait_for_state(client, page, _BANNER_ASSERT_JS, timeout_sec=30.0)
        assert banner.get("hasAlert") is True, f"Missing takeover alert: {banner}"
        assert (
            banner.get("hasExtensionTitle") is True
        ), f"Missing extension title: {banner}"
        assert banner.get("hasReason") is True, f"Missing reason text: {banner}"
        assert banner.get("hasUrl") is True, f"Missing URL line: {banner}"
        assert banner.get("hasDone") is True, f"Missing Done button: {banner}"
        assert banner.get("hasSkip") is True, f"Missing Skip button: {banner}"

        clicked = client.evaluate(page, _CLICK_DONE_JS, timeout_sec=10.0)
        assert isinstance(clicked, dict)
        assert clicked.get("clicked") is True, f"Failed to click Done: {clicked}"

        idle = wait_for_state(
            client,
            page,
            """(() => ({
              ready: window.__MYRM_E2E_CHAT__?.getBrowserTakeoverSnapshot?.()?.pending === false,
            }))()""",
            timeout_sec=15.0,
        )
        assert idle.get("ready") is True

        snapshot = client.evaluate(page, _SNAPSHOT_IDLE_JS, timeout_sec=5.0)
        assert isinstance(snapshot, dict)
        assert snapshot.get("pending") is False


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
def test_extension_takeover_skip_dismisses_banner() -> None:
    ui_url = get_e2e_ui_url()

    with open_mcp_page(ui_url) as (client, page):
        wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=60.0)

        triggered = client.evaluate(
            page, _TRIGGER_EXTENSION_TAKEOVER_JS, timeout_sec=10.0
        )
        assert isinstance(triggered, dict)
        assert triggered.get("pending") is True
        assert triggered.get("uiMode") == "extension"

        banner = wait_for_state(client, page, _BANNER_ASSERT_JS, timeout_sec=30.0)
        assert banner.get("hasSkip") is True, f"Missing Skip button: {banner}"

        clicked = client.evaluate(page, _CLICK_SKIP_JS, timeout_sec=10.0)
        assert isinstance(clicked, dict)
        assert clicked.get("clicked") is True, f"Failed to click Skip: {clicked}"

        idle = wait_for_state(
            client,
            page,
            """(() => ({
              ready: window.__MYRM_E2E_CHAT__?.getBrowserTakeoverSnapshot?.()?.pending === false,
            }))()""",
            timeout_sec=15.0,
        )
        assert idle.get("ready") is True

        snapshot = client.evaluate(page, _SNAPSHOT_IDLE_JS, timeout_sec=5.0)
        assert isinstance(snapshot, dict)
        assert snapshot.get("pending") is False


@pytest.mark.chrome_e2e(execution_mode="SHARED", access_scope="READ", workload="STANDARD")
@pytest.mark.integration
def test_extension_takeover_captcha_auto_hides_done_skip() -> None:
    ui_url = get_e2e_ui_url()

    with open_mcp_page(ui_url) as (client, page):
        wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=60.0)

        triggered = client.evaluate(page, _TRIGGER_CAPTCHA_AUTO_JS, timeout_sec=10.0)
        assert isinstance(triggered, dict)
        assert triggered.get("pending") is True
        assert triggered.get("autoDetectCompletion") is True

        banner = wait_for_state(client, page, _CAPTCHA_AUTO_ASSERT_JS, timeout_sec=15.0)
        assert banner.get("hasAlert") is True, f"Missing takeover alert: {banner}"
        assert (
            banner.get("hasCaptchaText") is True
        ), f"Missing captcha auto copy: {banner}"
        assert (
            banner.get("buttonCount") == 0
        ), f"Expected no action buttons during auto-detect: {banner}"


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.chrome_e2e_browser_takeover_live
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_agent_browser_ask_human_shows_extension_banner_and_completes(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real model + WebUI send → browser_ask_human SSE → in-chat banner → Done → DONE.

    Uses private_backend=True (SHPOIB): shared :3000 UI + isolated :180xx API — no shared
    :8080 agent-stream lock contention with parallel LIVE pytest.
    """
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live browser takeover Chrome E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome (API /api/v1/config/readiness provider.is_ready must be true)",
        )

    if not wait_e2e_cdp_ready(timeout_sec=45.0):
        pytest.fail(
            "E2E Chrome CDP not ready for browser takeover LIVE test — run ./myrm ready --chrome "
            "(MYRM Chrome on :9333 must respond to /json/version)",
        )

    ensure_e2e_yolo_mode()
    deny_stale_browser_takeover_approvals()
    ensure_e2e_memory_disabled()
    if not wait_e2e_backend_ready(timeout_sec=90.0):
        pytest.fail("Backend not healthy before browser takeover LIVE Chrome E2E")

    chat_id = await run_browser_takeover_live_session(
        ledger=e2e_resource_ledger,
        run_flow=run_browser_takeover_live_flow,
    )
    assert chat_id
