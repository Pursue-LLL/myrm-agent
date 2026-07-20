"""Real Chrome MCP E2E for browser takeover in-chat banner (extension / CDP path)."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    chat_messages_have_done,
    deny_stale_browser_takeover_approvals,
    ensure_e2e_memory_disabled,
    ensure_e2e_yolo_mode,
    get_e2e_api_url,
    wait_e2e_backend_ready,
    wait_e2e_cdp_ready,
    wait_e2e_provider_ready,
)
from cdp_chat_ui import chat_id_from_path, chat_user_message_count  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, open_mcp_page, wait_for_state
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

E2E_PROMPT = (
    "我在验证浏览器人工接管功能。请调用 browser_ask_human_tool 一次，"
    "reason 为「请在 Chrome 完成操作后，在聊天横幅点击完成」。"
    "完成后只回复 DONE。不要使用 browser_navigate_tool 或其他工具。"
)

E2E_NUDGE_PROMPT = (
    "请现在调用 browser_ask_human_tool，reason 为「请在 Chrome 完成操作后，在聊天横幅点击完成」。"
    "我完成后请回复 DONE。"
)

_BROWSER_TOOL_PROGRESS_JS = (
    "(() => window.__MYRM_E2E_CHAT__?.getBrowserToolProgress?.() ?? {})()"
)

_RECOVER_BROWSER_TAKEOVER_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.recoverPendingBrowserTakeover) {
    return { ok: false, err: 'no-recoverPendingBrowserTakeover' };
  }
  const result = await bridge.recoverPendingBrowserTakeover();
  return { ok: true, ...result };
})()"""

BROWSER_GATE_WAIT_SEC = 120.0
BROWSER_RECOVERY_DELAY_SEC = 12.0
BROWSER_RECOVERY_MIN_INTERVAL_SEC = 20.0
MAX_SEND_ATTEMPTS = 3

_ENABLE_YOLO_JS = """(() => {
  const key = 'securityConfig';
  const mgr = window.__MYRM_CONFIG_SYNC__?.get?.(key)
    ?? (typeof localStorage !== 'undefined' ? JSON.parse(localStorage.getItem(key) || 'null') : null);
  const next = {
    ...(mgr && typeof mgr === 'object' ? mgr : {}),
    yoloModeEnabled: true,
    yoloModeEnabledAt: Math.floor(Date.now() / 1000),
    permissions: { '*': 'allow' },
    domainHitlEnabled: false,
    autoReviewEnabled: false,
  };
  if (window.__MYRM_CONFIG_SYNC__?.set) {
    window.__MYRM_CONFIG_SYNC__.set(key, next);
  }
  return { ok: true, yoloModeEnabled: next.yoloModeEnabled === true };
})()"""

_ENABLE_BROWSER_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setCurrentBuiltinTools) {
    return { ok: false, err: 'no-bridge' };
  }
  bridge.setCurrentBuiltinTools(['browser']);
  const tools = bridge.getCurrentBuiltinTools?.() ?? [];
  return { ok: tools.includes('browser'), tools };
})()"""

_SET_BROWSER_CONNECT_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setBrowserSource) {
    return { ok: false, err: 'no-setBrowserSource' };
  }
  bridge.setBrowserSource('connect');
  const browserSource = bridge.getBrowserSource?.() ?? null;
  return { ok: browserSource === 'connect', browserSource };
})()"""

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

_CLICK_TOOL_APPROVE_JS = """(() => {
  const approveBtn = Array.from(document.querySelectorAll('button')).find((btn) => {
    const label = (btn.textContent || '').trim();
    return /^(Approve|Allow once|批准|允许一次|允许)$/i.test(label) && !btn.disabled;
  });
  if (approveBtn) {
    approveBtn.click();
    return { clicked: true, label: (approveBtn.textContent || '').trim() };
  }
  return {
    clicked: false,
    drawerOpen: Boolean(window.__MYRM_E2E_CHAT__?.isApprovalDrawerOpen?.()),
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


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
def test_extension_takeover_banner_shows_actions_and_dismisses_on_done() -> None:
    ui_url = get_e2e_ui_url()

    with open_mcp_page(ui_url) as (client, page):
        wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=60.0)

        triggered = client.evaluate(page, _TRIGGER_EXTENSION_TAKEOVER_JS, timeout_sec=10.0)
        assert isinstance(triggered, dict)
        assert triggered.get("pending") is True
        assert triggered.get("uiMode") == "extension"

        banner = wait_for_state(client, page, _BANNER_ASSERT_JS, timeout_sec=15.0)
        assert banner.get("hasAlert") is True, f"Missing takeover alert: {banner}"
        assert banner.get("hasExtensionTitle") is True, f"Missing extension title: {banner}"
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


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
@pytest.mark.integration
def test_extension_takeover_skip_dismisses_banner() -> None:
    ui_url = get_e2e_ui_url()

    with open_mcp_page(ui_url) as (client, page):
        wait_for_state(client, page, _BRIDGE_READY_JS, timeout_sec=60.0)

        triggered = client.evaluate(page, _TRIGGER_EXTENSION_TAKEOVER_JS, timeout_sec=10.0)
        assert isinstance(triggered, dict)
        assert triggered.get("pending") is True
        assert triggered.get("uiMode") == "extension"

        banner = wait_for_state(client, page, _BANNER_ASSERT_JS, timeout_sec=15.0)
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


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
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
        assert banner.get("hasCaptchaText") is True, f"Missing captcha auto copy: {banner}"
        assert banner.get("buttonCount") == 0, f"Expected no action buttons during auto-detect: {banner}"


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.chrome_e2e_browser_takeover_live
@pytest.mark.integration
@pytest.mark.asyncio
async def test_live_agent_browser_ask_human_shows_extension_banner_and_completes(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real model + WebUI send → browser_ask_human SSE → in-chat banner → Done → DONE."""
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

    async def _probe_browser_tool_progress(chat: McpChatSession) -> dict[str, object]:
        probe = await chat.evaluate(_BROWSER_TOOL_PROGRESS_JS, await_promise=False, recv_timeout=15.0)
        return probe if isinstance(probe, dict) else {"active": False}

    def _require_browser_gate_triggered(*, last_tool: str, takeover_pending: bool) -> None:
        if takeover_pending or last_tool.endswith("browser_ask_human_tool"):
            return
        raise AssertionError(
            "Model never triggered browser takeover gate "
            f"(lastTool={last_tool!r}, takeoverPending={takeover_pending}). "
            "Expected browser_ask_human_tool with extension in-chat banner."
        )

    async def _maybe_recover_browser_takeover(
        chat: McpChatSession,
        *,
        started_at: float,
        last_recovery_at: list[float],
    ) -> tuple[str, bool] | None:
        if time.monotonic() - started_at < BROWSER_RECOVERY_DELAY_SEC:
            return None
        if time.monotonic() - last_recovery_at[0] < BROWSER_RECOVERY_MIN_INTERVAL_SEC:
            return None
        last_recovery_at[0] = time.monotonic()
        recover = await chat.evaluate(
            _RECOVER_BROWSER_TAKEOVER_JS,
            await_promise=True,
            recv_timeout=45.0,
        )
        if isinstance(recover, dict) and recover.get("ok") and recover.get("pending") is True:
            return "browser_ask_human_tool", True
        return None

    async def _wait_for_browser_ask_human_gate(
        chat: McpChatSession,
        *,
        timeout_sec: float = BROWSER_GATE_WAIT_SEC,
    ) -> tuple[str, bool]:
        deadline = time.monotonic() + timeout_sec
        gate_started = time.monotonic()
        last_recovery_at = [0.0]
        last_tool = ""
        takeover_pending = False
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            progress = await _probe_browser_tool_progress(chat)
            last_tool = str(progress.get("lastTool") or "")
            takeover_pending = progress.get("takeoverPending") is True
            if takeover_pending or last_tool.endswith("browser_ask_human_tool"):
                return last_tool, takeover_pending

            banner = await chat.evaluate(_BANNER_ASSERT_JS, await_promise=False, recv_timeout=15.0)
            if isinstance(banner, dict) and (
                banner.get("ready") is True or banner.get("storePending") is True
            ):
                return last_tool or "browser_ask_human_tool", True

            recovered = await _maybe_recover_browser_takeover(
                chat,
                started_at=gate_started,
                last_recovery_at=last_recovery_at,
            )
            if recovered is not None:
                return recovered

            await asyncio.sleep(1.0)
        return last_tool, takeover_pending

    async def _wait_takeover_banner(chat: McpChatSession, *, timeout_sec: float = 90.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        banner_started = time.monotonic()
        last_recovery_at = [0.0]
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            if not wait_e2e_backend_ready(timeout_sec=3.0):
                await chat.ensure_e2e_api_base_binding()
                await asyncio.sleep(2.0)
                continue
            raw = await chat.evaluate(_BANNER_ASSERT_JS, await_promise=False, recv_timeout=30.0)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("backendUnreachable") is True:
                await chat.ensure_e2e_api_base_binding()
                await asyncio.sleep(2.0)
                continue
            if last.get("ready") is True:
                return last
            recovered = await _maybe_recover_browser_takeover(
                chat,
                started_at=banner_started,
                last_recovery_at=last_recovery_at,
            )
            if recovered is not None:
                raw = await chat.evaluate(_BANNER_ASSERT_JS, await_promise=False, recv_timeout=30.0)
                last = raw if isinstance(raw, dict) else {"value": raw}
                if last.get("ready") is True:
                    return last
            await asyncio.sleep(1.0)
        raise AssertionError(f"Browser takeover banner did not appear: {last}")

    async def _prepare_browser_turn(chat: McpChatSession) -> None:
        connect = await chat.evaluate(_SET_BROWSER_CONNECT_JS, await_promise=False, recv_timeout=15.0)
        assert isinstance(connect, dict)
        assert connect.get("ok") is True, f"Failed to set browser source connect: {connect}"
        enabled = await chat.evaluate(_ENABLE_BROWSER_JS, await_promise=False, recv_timeout=15.0)
        assert isinstance(enabled, dict)
        assert enabled.get("ok") is True, f"Failed to enable browser in chat session: {enabled}"
        await chat.evaluate(_ENABLE_YOLO_JS, await_promise=False, recv_timeout=15.0)

    async def _wait_api_done(chat_id: str, *, api_url: str, timeout_sec: float = 120.0) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            if chat_messages_have_done(chat_id, api_url=api_url):
                return True
            await asyncio.sleep(2.0)
        return False

    async def _run_flow(chat: McpChatSession) -> str:
        api_base = get_e2e_api_url()
        await chat.dismiss_modals()
        await chat.cdp("Page.navigate", {"url": f"{BASE_URL}/"}, recv_timeout=120.0)
        await asyncio.sleep(2.0)
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL, timeout_sec=120.0)
        await chat.ensure_model_ready(timeout_sec=180.0)
        await _prepare_browser_turn(chat)

        chat_id_hint: str | None = None
        banner: dict[str, object] | None = None
        last_prompt = E2E_PROMPT
        for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
            if attempt > 1:
                await chat.click_new_chat()
                await chat.ensure_chat_surface(BASE_URL, timeout_sec=120.0)
                await chat.ensure_model_ready(timeout_sec=180.0)
                await _prepare_browser_turn(chat)
            last_prompt = E2E_PROMPT if attempt == 1 else E2E_NUDGE_PROMPT
            heartbeat_e2e_lease()
            send_result = await chat.send_message(last_prompt, last_prompt)
            chat_id_hint = str(
                send_result.get("started", {}).get("chatId")
                or send_result.get("submit", {}).get("chatId")
                or chat_id_hint
                or ""
            ).strip() or None
            if not chat_id_hint:
                chat_id_hint = str((await chat.bridge_chat_id()) or "").strip() or None

            try:
                await chat.wait_stream_started(last_prompt, timeout_sec=90.0, chat_id_hint=chat_id_hint)
            except (AssertionError, TimeoutError, RuntimeError):
                pass

            last_tool, takeover_pending = await _wait_for_browser_ask_human_gate(chat)
            if not takeover_pending and not last_tool.endswith("browser_ask_human_tool"):
                if attempt >= MAX_SEND_ATTEMPTS:
                    _require_browser_gate_triggered(
                        last_tool=last_tool,
                        takeover_pending=takeover_pending,
                    )
                continue

            try:
                banner = await _wait_takeover_banner(chat, timeout_sec=90.0)
                break
            except AssertionError:
                if attempt >= MAX_SEND_ATTEMPTS:
                    raise
                heartbeat_e2e_lease()

        assert banner is not None

        assert banner.get("hasExtensionTitle") is True, f"Expected extension banner: {banner}"

        clicked = await chat.evaluate(_CLICK_DONE_JS, await_promise=False, recv_timeout=15.0)
        assert isinstance(clicked, dict)
        assert clicked.get("clicked") is True, f"Failed to click Done on takeover banner: {clicked}"

        try:
            after_turn = await chat.wait_turn_done(
                last_prompt,
                timeout_sec=300.0,
                chat_id_hint=chat_id_hint,
            )
        except TimeoutError:
            resolved_chat_id = chat_id_hint or str((await chat.bridge_chat_id()) or "").strip() or None
            if resolved_chat_id and await _wait_api_done(resolved_chat_id, api_url=api_base):
                after_turn = {
                    "chatId": resolved_chat_id,
                    "okViaApi": True,
                    "bridgeChatId": resolved_chat_id,
                }
            else:
                raise
        if str(after_turn.get("path", "")).startswith("/settings"):
            pytest.fail(f"Send redirected to settings: {after_turn}")

        chat_id = chat_id_hint or chat_id_from_path(str(after_turn.get("path") or ""))
        if not chat_id:
            chat_id = str(after_turn.get("bridgeChatId") or "").strip() or None
        assert chat_id, f"Expected chat id after browser takeover turn: {after_turn}; banner={banner}"

        if not chat_messages_have_done(chat_id, api_url=api_base):
            turn = await chat.evaluate(
                """(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null)()""",
                await_promise=False,
            )
            pytest.fail(f"Assistant did not reply DONE for chat {chat_id}: turn={turn}; after={after_turn}")

        assert chat_user_message_count(chat_id, api_url=api_base) >= 1
        e2e_resource_ledger.register("chat", chat_id)
        return chat_id

    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = None
        try:
            page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
        except TimeoutError:
            await asyncio.sleep(2.0)
            page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
        if page is None:
            raise RuntimeError("new_page returned no page")
        chat = McpChatSession(client, page)
        await chat.bootstrap(BASE_URL, timeout_sec=120.0)
        chat_id = await _run_flow(chat)
        assert chat_id
    finally:
        await asyncio.to_thread(client.close)
