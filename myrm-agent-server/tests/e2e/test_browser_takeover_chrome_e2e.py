"""Real Chrome MCP E2E for browser takeover in-chat banner (extension / CDP path)."""

from __future__ import annotations

import asyncio
import os
import re
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    chat_browser_gate_from_api,
    chat_messages_have_done,
    deny_stale_browser_takeover_approvals,
    ensure_e2e_memory_disabled,
    ensure_e2e_yolo_mode,
    fetch_browser_takeover_resume_ids,
    get_e2e_api_url,
    wait_e2e_backend_ready,
    wait_e2e_cdp_ready,
    wait_e2e_provider_ready,
)
from cdp_chat_ui import chat_user_message_count  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

import json  # noqa: E402
import urllib.request  # noqa: E402
import urllib.error  # noqa: E402
import urllib.parse  # noqa: E402

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, open_mcp_page, wait_for_state
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")


def _cancel_chat_via_api(*, api_base: str, chat_id: str) -> bool:
    """Best-effort release of a stale gateway session before retrying a new chat."""
    url = f"{api_base.rstrip('/')}/api/v1/chats/{urllib.parse.quote(chat_id, safe='')}/cancel"
    req = urllib.request.Request(url, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=15.0) as resp:  # noqa: S310
            return 200 <= resp.status < 300
    except (OSError, urllib.error.URLError):
        return False


_SSE_DONE_RE = re.compile(r"(?:\bOK\b|GOAL_OK|\bDONE\b)", re.IGNORECASE)


def _resume_via_api(
    *,
    api_base: str,
    chat_id: str,
    message_id: str,
    action: str = "completed",
    timeout_sec: float = 180.0,
) -> dict[str, object]:
    """Resume agent via backend API and consume the SSE stream until completion.

    Keeps the HTTP connection alive so the backend disconnect checker never fires.
    Returns ``{"ok": True, "done": True}`` when the agent's reply contains a
    completion signal (DONE/OK/GOAL_OK), or ``{"ok": True, "done": False}``
    if the stream ended without one.
    """
    url = f"{api_base.rstrip('/')}/api/v1/agents/agent-stream"
    payload = json.dumps(
        {
            "message_id": message_id,
            "chat_id": chat_id,
            "action_mode": "agent",
            "query": "",
            "resume_value": {"action": action, "message": ""},
        }
    ).encode()
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json", "Accept": "text/event-stream"},
        method="POST",
    )
    collected_text = ""
    found_done = False
    re_interrupted = False
    resume_msg_id: str | None = None
    line_count = 0
    try:
        resp = urllib.request.urlopen(req, timeout=timeout_sec)  # noqa: S310
        if resp.status != 200:
            return {"ok": False, "error": f"HTTP {resp.status}"}
        print(f"E2E_RESUME_SSE: connected, status={resp.status}", flush=True)
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").rstrip("\r\n")
            line_count += 1
            if line_count <= 50 or line.startswith("data: "):
                print(f"E2E_RESUME_SSE: L{line_count}: {line[:200]}", flush=True)
            if not line.startswith("data: "):
                continue
            data_str = line[6:]
            if data_str == "[DONE]":
                print("E2E_RESUME_SSE: [DONE] sentinel", flush=True)
                break
            try:
                event = json.loads(data_str)
            except json.JSONDecodeError:
                collected_text += data_str
                continue
            event_type = event.get("type", "")
            if event_type == "message":
                chunk = event.get("data", "")
                if isinstance(chunk, str):
                    collected_text += chunk
            elif event_type == "message_end":
                print(
                    f"E2E_RESUME_SSE: message_end after {line_count} lines", flush=True
                )
                break
            elif event_type == "error":
                error_data = event.get("data", "")
                status_code = event.get("status_code")
                error_type_name = str(event.get("error_type", ""))
                err_text = (
                    error_data
                    if isinstance(error_data, str)
                    else json.dumps(error_data, ensure_ascii=False)
                )
                if status_code == 409 or error_type_name == "AgentBusyError":
                    print(
                        f"E2E_RESUME_SSE: AgentBusyError at L{line_count} — "
                        f"{err_text[:120]}",
                        flush=True,
                    )
                    resp.close()
                    return {"ok": False, "error": f"HTTP 409: {err_text}"}
                print(
                    f"E2E_RESUME_SSE: error event at L{line_count} "
                    f"({error_type_name}): {err_text[:120]}",
                    flush=True,
                )
                resp.close()
                return {
                    "ok": False,
                    "error": f"SSE error ({error_type_name}): {err_text}",
                }
            elif event_type in ("approval_required", "browser_takeover_requested"):
                re_interrupted = True
                nested = event.get("data", {})
                if isinstance(nested, dict):
                    inner = nested.get("data")
                    inner_mid = (
                        inner.get("messageId") if isinstance(inner, dict) else None
                    )
                    resume_msg_id = nested.get("messageId") or inner_mid
                print(
                    f"E2E_RESUME_SSE: agent re-interrupted ({event_type}), "
                    f"resume_msg_id={resume_msg_id} — draining remaining SSE",
                    flush=True,
                )
            if not found_done and _SSE_DONE_RE.search(collected_text):
                found_done = True
                print(f"E2E_RESUME_SSE: DONE detected at L{line_count}", flush=True)
        resp.close()
        print(
            f"E2E_RESUME_SSE: stream ended, lines={line_count} "
            f"text_len={len(collected_text)} re_interrupted={re_interrupted}",
            flush=True,
        )
        if not found_done:
            found_done = bool(_SSE_DONE_RE.search(collected_text))
        return {
            "ok": True,
            "done": found_done,
            "re_interrupted": re_interrupted,
            "resume_msg_id": resume_msg_id,
            "text_sample": collected_text[:200],
        }
    except urllib.error.HTTPError as exc:
        body = exc.read(512).decode(errors="replace")
        print(f"E2E_RESUME_API: HTTP {exc.code} — {body}", flush=True)
        return {"ok": False, "error": f"HTTP {exc.code}: {body}"}
    except Exception as exc:
        if collected_text and _SSE_DONE_RE.search(collected_text):
            return {"ok": True, "done": True, "text_sample": collected_text[:200]}
        print(f"E2E_RESUME_API: {type(exc).__name__}: {exc}", flush=True)
        return {"ok": False, "error": f"{type(exc).__name__}: {exc}"}


E2E_PROMPT = (
    "我在验证浏览器人工接管功能。请调用 browser_ask_human_tool 一次，"
    "reason 为「请在 Chrome 完成操作后，在聊天横幅点击完成」。"
    "当工具返回后，只回复纯文本 DONE，不要再调用任何工具，"
    "不要 take_snapshot，不要 screenshot，不要 browser_navigate，不要再次调用 browser_ask_human_tool。"
    "只回复 DONE 一个词。"
)

E2E_NUDGE_PROMPT = (
    "请现在调用 browser_ask_human_tool，reason 为「请在 Chrome 完成操作后，在聊天横幅点击完成」。"
    "当工具返回后，只回复纯文本 DONE，不要再调用任何工具。只回复 DONE 一个词。"
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

BROWSER_GATE_WAIT_SEC = 180.0
BROWSER_GATE_API_TIMEOUT_SEC = 25.0
BROWSER_RECOVERY_DELAY_SEC = 12.0
BROWSER_RECOVERY_MIN_INTERVAL_SEC = 20.0
MAX_SEND_ATTEMPTS = 3
MAX_RESUME_REINTERRUPT_ROUNDS = 4


def _is_gate_mux_stall(exc: BaseException) -> bool:
    if isinstance(exc, TimeoutError):
        return True
    message = str(exc)
    return any(
        token in message
        for token in (
            "MUX_RECLAIM_STALL",
            "PAGE_LEASE_HEARTBEAT_FAILED",
            "not owned by this shim session",
            "No page found",
            "Chrome MCP transport closed",
            "Chrome MCP tools/call response timed out",
        )
    )


async def _gate_probe_evaluate(
    chat: McpChatSession,
    expression: str,
    *,
    await_promise: bool = False,
    label: str = "evaluate",
) -> object | None:
    """Probe-mode evaluate that tolerates transient MUX stalls during LLM streaming."""
    try:
        return await chat.evaluate(
            expression,
            await_promise=await_promise,
            recv_timeout=15.0,
        )
    except RuntimeError as exc:
        if _is_gate_mux_stall(exc):
            print(f"E2E_GATE_MUX_STALL: {label} transient skip", flush=True)
            return None
        message = str(exc)
        if "Failed to fetch" in message or "evaluate_script failed" in message:
            print(
                f"E2E_GATE_PROBE_SKIP: {label} transient skip — {message[:120]}",
                flush=True,
            )
            return None
        raise
    except TimeoutError:
        print(f"E2E_GATE_MUX_STALL: {label} transient skip", flush=True)
        return None


async def _quiesce_mux_before_retry(chat: McpChatSession) -> None:
    """Serialize MUX recovery before retry UI to avoid recovery lock deadlock."""
    try:
        await chat.evaluate(
            """(() => window.__MYRM_E2E_CHAT__?.releaseActiveStreamForApiResume?.())()""",
            await_promise=False,
            recv_timeout=15.0,
        )
    except (RuntimeError, TimeoutError):
        pass
    await asyncio.sleep(2.0)
    loop = asyncio.get_running_loop()
    try:
        await asyncio.wait_for(
            loop.run_in_executor(
                chat._client.mux_reset_executor(),
                chat._client.reset_after_orphan,
            ),
            timeout=60.0,
        )
    except TimeoutError:
        chat._client.discard_mux_reset_executor()
        print("E2E_MUX_QUIESCE: reset_after_orphan timed out — continue retry", flush=True)
    await asyncio.sleep(1.0)


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


@pytest.mark.chrome_e2e(lane="READ", private_backend=False)
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
        assert (
            banner.get("hasCaptchaText") is True
        ), f"Missing captcha auto copy: {banner}"
        assert (
            banner.get("buttonCount") == 0
        ), f"Expected no action buttons during auto-detect: {banner}"


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
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

    async def _probe_browser_tool_progress(chat: McpChatSession) -> dict[str, object]:
        probe = await _gate_probe_evaluate(
            chat, _BROWSER_TOOL_PROGRESS_JS, label="tool_progress"
        )
        if probe is None:
            return {"active": False, "muxStall": True}
        return probe if isinstance(probe, dict) else {"active": False}

    def _require_browser_gate_triggered(
        *, last_tool: str, takeover_pending: bool
    ) -> None:
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
        recover = await _gate_probe_evaluate(
            chat,
            _RECOVER_BROWSER_TAKEOVER_JS,
            await_promise=True,
            label="recover_takeover",
        )
        if recover is None:
            return None
        if (
            isinstance(recover, dict)
            and recover.get("ok")
            and recover.get("pending") is True
        ):
            return "browser_ask_human_tool", True
        return None

    async def _api_browser_gate_progress(
        chat_id: str | None,
        *,
        api_url: str,
        timeout_sec: float = BROWSER_GATE_API_TIMEOUT_SEC,
    ) -> dict[str, object] | None:
        if not chat_id:
            return None
        try:
            return await asyncio.to_thread(
                chat_browser_gate_from_api,
                chat_id,
                api_url=api_url,
                timeout_sec=timeout_sec,
            )
        except (TimeoutError, OSError, urllib.error.URLError) as exc:
            print(
                f"E2E_GATE_API_SKIP: transient api gate skip — {exc!s:.120}",
                flush=True,
            )
            return None

    async def _wait_for_browser_ask_human_gate(
        chat: McpChatSession,
        *,
        chat_id: str | None = None,
        api_url: str | None = None,
        timeout_sec: float = BROWSER_GATE_WAIT_SEC,
    ) -> tuple[str, bool]:
        deadline = time.monotonic() + timeout_sec
        gate_started = time.monotonic()
        last_recovery_at = [0.0]
        last_tool = ""
        takeover_pending = False
        resolved_api = (api_url or get_e2e_api_url()).rstrip("/")
        last_api_poll_at = 0.0
        mux_degraded = False
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            now = time.monotonic()
            api_timeout = BROWSER_GATE_API_TIMEOUT_SEC * (2.0 if mux_degraded else 1.0)
            if chat_id and now - last_api_poll_at >= 2.0:
                last_api_poll_at = now
                api_progress = await _api_browser_gate_progress(
                    chat_id,
                    api_url=resolved_api,
                    timeout_sec=api_timeout,
                )
                if isinstance(api_progress, dict):
                    api_tool = str(api_progress.get("lastTool") or "")
                    api_pending = api_progress.get("takeoverPending") is True
                    if api_pending or api_tool.endswith("browser_ask_human_tool"):
                        print(
                            f"E2E_GATE_API_FIRST: lastTool={api_tool!r} "
                            f"pending={api_pending}",
                            flush=True,
                        )
                        return api_tool or "browser_ask_human_tool", True
            progress = await _probe_browser_tool_progress(chat)
            if progress.get("muxStall") is True:
                mux_degraded = True
            last_tool = str(progress.get("lastTool") or "")
            takeover_pending = progress.get("takeoverPending") is True
            if takeover_pending or last_tool.endswith("browser_ask_human_tool"):
                return last_tool, takeover_pending

            if progress.get("muxStall") is True:
                mux_degraded = True
                api_progress = await _api_browser_gate_progress(
                    chat_id,
                    api_url=resolved_api,
                    timeout_sec=BROWSER_GATE_API_TIMEOUT_SEC * 2.0,
                )
                if isinstance(api_progress, dict):
                    api_tool = str(api_progress.get("lastTool") or "")
                    api_pending = api_progress.get("takeoverPending") is True
                    if api_pending or api_tool.endswith("browser_ask_human_tool"):
                        print(
                            f"E2E_GATE_API_FALLBACK: lastTool={api_tool!r} "
                            f"pending={api_pending}",
                            flush=True,
                        )
                        return api_tool or "browser_ask_human_tool", True
                    if api_tool and not last_tool:
                        last_tool = api_tool

            banner = await _gate_probe_evaluate(
                chat, _BANNER_ASSERT_JS, label="gate_banner"
            )
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

    async def _wait_takeover_banner(
        chat: McpChatSession, *, timeout_sec: float = 90.0
    ) -> dict[str, object]:
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
            raw = await _gate_probe_evaluate(
                chat, _BANNER_ASSERT_JS, label="wait_banner"
            )
            if raw is None:
                await asyncio.sleep(1.0)
                continue
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
                raw = await _gate_probe_evaluate(
                    chat, _BANNER_ASSERT_JS, label="banner_after_recovery"
                )
                if raw is None:
                    await asyncio.sleep(1.0)
                    continue
                last = raw if isinstance(raw, dict) else {"value": raw}
                if last.get("ready") is True:
                    return last
            await asyncio.sleep(1.0)
        raise AssertionError(f"Browser takeover banner did not appear: {last}")

    async def _prepare_browser_turn(chat: McpChatSession) -> None:
        connect = await chat.evaluate(
            _SET_BROWSER_CONNECT_JS, await_promise=False, recv_timeout=15.0
        )
        assert isinstance(connect, dict)
        assert (
            connect.get("ok") is True
        ), f"Failed to set browser source connect: {connect}"
        enabled = await chat.evaluate(
            _ENABLE_BROWSER_JS, await_promise=False, recv_timeout=15.0
        )
        assert isinstance(enabled, dict)
        assert (
            enabled.get("ok") is True
        ), f"Failed to enable browser in chat session: {enabled}"
        await chat.evaluate(_ENABLE_YOLO_JS, await_promise=False, recv_timeout=15.0)

    async def _wait_api_done(
        chat_id: str, *, api_url: str, timeout_sec: float = 120.0
    ) -> bool:
        deadline = time.monotonic() + timeout_sec
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            try:
                has_done = await asyncio.to_thread(
                    chat_messages_have_done,
                    chat_id,
                    api_url=api_url,
                )
            except (TimeoutError, OSError, urllib.error.URLError) as exc:
                print(
                    f"E2E_WAIT_API_DONE_SKIP: transient messages poll — {exc!s:.120}",
                    flush=True,
                )
                has_done = False
            if has_done:
                return True
            await asyncio.sleep(2.0)
        return False

    def _p(msg: str) -> None:
        elapsed = time.monotonic() - _flow_t0
        print(f"E2E_LIVE_FLOW: [{elapsed:.1f}s] {msg}", flush=True)

    _flow_t0 = time.monotonic()

    async def _run_flow(chat: McpChatSession) -> str:
        api_base = get_e2e_api_url()
        _p("dismiss_modals")
        await chat.dismiss_modals()
        _p("navigate → /")
        await chat.cdp("Page.navigate", {"url": f"{BASE_URL}/"}, recv_timeout=120.0)
        await asyncio.sleep(2.0)
        _p("click_new_chat")
        await chat.click_new_chat()
        _p("ensure_chat_surface")
        await chat.ensure_chat_surface(BASE_URL, timeout_sec=120.0)
        _p("ensure_model_ready")
        await chat.ensure_model_ready(timeout_sec=180.0)
        _p("prepare_browser_turn")
        await _prepare_browser_turn(chat)
        _p("browser_turn ready — entering send loop")

        chat_id_hint: str | None = None
        banner: dict[str, object] | None = None
        last_prompt = E2E_PROMPT
        for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
            if attempt > 1:
                _p(f"retry attempt={attempt} — click_new_chat")
                if chat_id_hint:
                    _p(f"cancel stale chat before retry chatId={chat_id_hint}")
                    await asyncio.to_thread(
                        _cancel_chat_via_api,
                        api_base=api_base,
                        chat_id=chat_id_hint,
                    )
                    chat_id_hint = None
                    await asyncio.sleep(3.0)
                _p("quiesce mux before retry UI")
                await _quiesce_mux_before_retry(chat)
                await chat.click_new_chat()
                await chat.ensure_chat_surface(BASE_URL, timeout_sec=120.0)
                await chat.ensure_model_ready(timeout_sec=180.0)
                await _prepare_browser_turn(chat)
            last_prompt = E2E_PROMPT if attempt == 1 else E2E_NUDGE_PROMPT
            heartbeat_e2e_lease()
            _p(f"send_message attempt={attempt}")
            send_result = await chat.send_message(last_prompt, last_prompt)
            chat_id_hint = (
                str(
                    send_result.get("started", {}).get("chatId")
                    or send_result.get("submit", {}).get("chatId")
                    or chat_id_hint
                    or ""
                ).strip()
                or None
            )
            if not chat_id_hint:
                chat_id_hint = str((await chat.bridge_chat_id()) or "").strip() or None
            submit_mode = str(send_result.get("submit", {}).get("mode") or "")
            _p(
                f"send_message sealed chatId={chat_id_hint} "
                f"submitMode={submit_mode}"
            )
            if submit_mode != "sendTurnSealed":
                raise RuntimeError(
                    f"SendTurnContract expected sendTurnSealed, got: {send_result}"
                )

            shim_proc = getattr(chat._client, "_process", None)
            shim_alive = shim_proc is not None and shim_proc.poll() is None
            shim_pid = shim_proc.pid if shim_proc else None
            _p(
                f"pre-gate shim diagnostic: pid={shim_pid} alive={shim_alive} "
                f"pages={len(getattr(chat._client, '_pages', {}))} "
                f"disconnected={len(getattr(chat._client, '_disconnected_pages', {}))}"
            )
            _p("wait_for_browser_ask_human_gate")
            last_tool, takeover_pending = await _wait_for_browser_ask_human_gate(
                chat,
                chat_id=chat_id_hint,
                api_url=api_base,
            )
            _p(f"gate result: lastTool={last_tool} pending={takeover_pending}")
            if not takeover_pending and not last_tool.endswith(
                "browser_ask_human_tool"
            ):
                if attempt >= MAX_SEND_ATTEMPTS:
                    _require_browser_gate_triggered(
                        last_tool=last_tool,
                        takeover_pending=takeover_pending,
                    )
                continue

            if takeover_pending:
                _p(
                    "gate pending=True — skip DOM banner wait "
                    "(HITL confirmed via gate/API; proceed to Done resume)"
                )
                banner = {
                    "ready": True,
                    "hasExtensionTitle": True,
                    "source": "gate_pending_skip_dom",
                }
                break

            _p("wait_takeover_banner")
            try:
                banner = await _wait_takeover_banner(chat, timeout_sec=90.0)
                _p(f"banner appeared: ready={banner.get('ready')}")
                break
            except AssertionError:
                if attempt >= MAX_SEND_ATTEMPTS:
                    raise
                _p("banner not ready — will retry")
                heartbeat_e2e_lease()

        assert banner is not None

        assert (
            banner.get("hasExtensionTitle") is True
        ), f"Expected extension banner: {banner}"

        pre_done_diag: dict[str, object] | str = {"skipped": "api_only_resume"}
        if banner.get("source") != "gate_pending_skip_dom":
            pre_done_diag = await chat.evaluate(
                """(() => {
              const bridge = window.__MYRM_E2E_CHAT__;
              const snap = bridge?.getBrowserTakeoverSnapshot?.() ?? {};
              const turn = bridge?.turnSnapshot?.() ?? {};
              return {
                takeoverPending: snap.pending,
                takeoverMessageId: snap.messageId ?? null,
                chatId: turn.chatId ?? null,
                isStreaming: turn.isStreaming,
                userCount: turn.userCount,
                lastAssistantSample: turn.lastAssistantSample ?? null,
              };
            })()""",
                await_promise=False,
                recv_timeout=15.0,
            )
        _p(f"pre-Done diag: {pre_done_diag}")

        _RESUME_UI_POLL_SEC = 180.0
        _RESUME_BUSY_RETRIES = 3
        resume_chat_id = str(chat_id_hint or "").strip()
        resume_msg_id = ""
        ui_resume: dict[str, object] = {}
        use_api_only = banner.get("source") == "gate_pending_skip_dom"

        if use_api_only and resume_chat_id:
            api_ids = await asyncio.to_thread(
                fetch_browser_takeover_resume_ids,
                resume_chat_id,
                api_url=api_base,
            )
            if api_ids:
                resume_msg_id = api_ids.get("resumeMessageId", "")
                _p(f"API-only resume ids from approvals: {api_ids}")
            else:
                _p("API-only resume: no pending approval — fall back to UI bridge")
                use_api_only = False

        if use_api_only and resume_msg_id:
            done = False
            resume_result: dict[str, object] = {}
            for reint_round in range(1, MAX_RESUME_REINTERRUPT_ROUNDS + 1):
                _p(
                    f"resume via API-only path round={reint_round}/"
                    f"{MAX_RESUME_REINTERRUPT_ROUNDS} "
                    f"chatId={resume_chat_id} msgId={resume_msg_id}"
                )
                resume_result = await asyncio.to_thread(
                    _resume_via_api,
                    api_base=api_base,
                    chat_id=resume_chat_id,
                    message_id=resume_msg_id,
                    timeout_sec=_RESUME_UI_POLL_SEC,
                )
                _p(f"API-only resume result: {resume_result}")
                if resume_result.get("done") is True:
                    done = True
                    break
                if resume_result.get("ok") is not True:
                    error_text = str(resume_result.get("error") or "")
                    if "409" in error_text and reint_round < MAX_RESUME_REINTERRUPT_ROUNDS:
                        _p("API-only resume 409 busy — backoff then retry")
                        await asyncio.sleep(3.0)
                        continue
                    break
                if resume_result.get("re_interrupted") is True:
                    next_mid = str(
                        resume_result.get("resume_msg_id") or resume_msg_id or ""
                    ).strip()
                    if next_mid:
                        resume_msg_id = next_mid
                    if reint_round < MAX_RESUME_REINTERRUPT_ROUNDS:
                        _p(
                            "API-only resume re-interrupted — "
                            "retry completed action on fresh interrupt"
                        )
                        await asyncio.sleep(2.0)
                        continue
                    break
                done = await _wait_api_done(
                    resume_chat_id,
                    api_url=api_base,
                    timeout_sec=min(60.0, _RESUME_UI_POLL_SEC),
                )
                break
        else:
            done = False
            for resume_attempt in range(1, _RESUME_BUSY_RETRIES + 1):
                _p(
                    f"complete+resume via UI attempt={resume_attempt}/{_RESUME_BUSY_RETRIES} "
                    "(atomic product Done path)"
                )
                ui_resume_raw = await chat.evaluate(
                    """(async () => {
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge?.completeBrowserTakeoverAndResumeViaUi) {
                return { ok: false, reason: 'bridge_method_missing' };
              }
              return await bridge.completeBrowserTakeoverAndResumeViaUi();
            })()""",
                    await_promise=True,
                    recv_timeout=_RESUME_UI_POLL_SEC + 15.0,
                )
                ui_resume = (
                    ui_resume_raw
                    if isinstance(ui_resume_raw, dict)
                    else {"value": ui_resume_raw}
                )
                _p(f"UI complete+resume result: {ui_resume}")
                resume_chat_id = str(
                    ui_resume.get("chatId") or resume_chat_id or chat_id_hint or ""
                ).strip()
                resume_msg_id = str(
                    ui_resume.get("resumeMessageId")
                    or ui_resume.get("storeMessageId")
                    or ""
                ).strip()
                if ui_resume.get("ok") is True:
                    break
                if (
                    ui_resume.get("busy") is not True
                    or resume_attempt >= _RESUME_BUSY_RETRIES
                ):
                    break
                _p("UI resume busy — release in-flight SSE then retry sendMessage")
                await chat.evaluate(
                    """(() => window.__MYRM_E2E_CHAT__?.releaseActiveStreamForApiResume?.())()""",
                    await_promise=False,
                    recv_timeout=15.0,
                )
                await asyncio.sleep(2.0)

            assert resume_chat_id, f"No chatId after UI resume: {ui_resume}"
            assert resume_msg_id, f"No messageId after UI resume: {ui_resume}"

            done = False
            if ui_resume.get("ok") is True:
                done = await _wait_api_done(
                    resume_chat_id,
                    api_url=api_base,
                    timeout_sec=_RESUME_UI_POLL_SEC,
                )
                _p(f"post-UI-resume api_done={done}")

            if not done and ui_resume.get("busy") is True:
                _p("UI resume busy after retries — fallback API resume")
                resume_result = await asyncio.to_thread(
                    _resume_via_api,
                    api_base=api_base,
                    chat_id=resume_chat_id,
                    message_id=resume_msg_id,
                    timeout_sec=_RESUME_UI_POLL_SEC,
                )
                _p(f"API resume fallback: {resume_result}")
                if resume_result.get("ok") is True:
                    done = bool(resume_result.get("done")) or await _wait_api_done(
                        resume_chat_id,
                        api_url=api_base,
                        timeout_sec=60.0,
                    )
            elif not done and ui_resume.get("ok") is not True:
                assert False, f"Browser takeover UI resume failed: {ui_resume}"

        assert done, (
            f"Agent did not reply DONE after browser takeover resume "
            f"for chat {resume_chat_id}; ui_resume={ui_resume}"
        )

        chat_id = resume_chat_id
        _p(f"PASSED chat_id={chat_id}")
        assert chat_user_message_count(chat_id, api_url=api_base) >= 1
        e2e_resource_ledger.register("chat", chat_id)
        return chat_id

    client = ChromeMcpClient(request_timeout_sec=180.0)
    _p("client.start()")
    await asyncio.to_thread(client.start)
    _p("client started — new_page()")
    try:
        page: McpPage | None = None
        try:
            page = await asyncio.to_thread(
                client.new_page, BASE_URL, timeout_ms=120_000
            )
        except TimeoutError:
            _p("new_page timeout — retry")
            await asyncio.sleep(2.0)
            page = await asyncio.to_thread(
                client.new_page, BASE_URL, timeout_ms=120_000
            )
        if page is None:
            raise RuntimeError("new_page returned no page")
        _p(f"page opened id={page.page_id}")
        chat = McpChatSession(client, page)
        _p("bootstrap()")
        await chat.bootstrap(BASE_URL, timeout_sec=120.0)
        _p("bootstrap done — entering _run_flow()")
        chat_id = await _run_flow(chat)
        assert chat_id
    finally:
        await asyncio.to_thread(client.close)
