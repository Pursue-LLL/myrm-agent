"""Browser takeover LIVE — gate / MUX probe helpers (R98)."""

from __future__ import annotations

import asyncio
import time
import urllib.error

from cdp_chat_support import (
    chat_browser_gate_from_api,
    get_e2e_api_url,
    wait_e2e_backend_ready,
)
from mcp_chat_ui import McpChatSession
from e2e_lease_heartbeat import heartbeat_e2e_lease

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

BROWSER_TOOL_PROGRESS_JS = (
    "(() => window.__MYRM_E2E_CHAT__?.getBrowserToolProgress?.() ?? {})()"
)

RECOVER_BROWSER_TAKEOVER_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.recoverPendingBrowserTakeover) {
    return { ok: false, err: 'no-recoverPendingBrowserTakeover' };
  }
  const result = await bridge.recoverPendingBrowserTakeover();
  return { ok: true, ...result };
})()"""

BANNER_ASSERT_JS = """(() => {
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

ENABLE_YOLO_JS = """(() => {
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

ENABLE_BROWSER_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setCurrentBuiltinTools) {
    return { ok: false, err: 'no-bridge' };
  }
  bridge.setCurrentBuiltinTools(['browser']);
  const tools = bridge.getCurrentBuiltinTools?.() ?? [];
  return { ok: tools.includes('browser'), tools };
})()"""

SET_BROWSER_CONNECT_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setBrowserSource) {
    return { ok: false, err: 'no-setBrowserSource' };
  }
  bridge.setBrowserSource('connect');
  const browserSource = bridge.getBrowserSource?.() ?? null;
  return { ok: browserSource === 'connect', browserSource };
})()"""

BROWSER_GATE_WAIT_SEC = 180.0
BROWSER_GATE_API_TIMEOUT_SEC = 25.0
BROWSER_RECOVERY_DELAY_SEC = 12.0
BROWSER_RECOVERY_MIN_INTERVAL_SEC = 20.0
MAX_SEND_ATTEMPTS = 3


def is_gate_mux_stall(exc: BaseException) -> bool:
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


async def gate_probe_evaluate(
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
        if is_gate_mux_stall(exc):
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


async def quiesce_mux_before_retry(chat: McpChatSession) -> None:
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
        print(
            "E2E_MUX_QUIESCE: reset_after_orphan timed out — continue retry",
            flush=True,
        )
    await asyncio.sleep(1.0)


async def wait_ui_stream_idle(
    chat: McpChatSession, *, timeout_sec: float = 45.0
) -> bool:
    """Wait until sendTurn UI stream releases loading/abortController before API resume."""
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        raw = await gate_probe_evaluate(
            chat,
            """(() => {
              const turn = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
              return {
                isStreaming: Boolean(turn.isStreaming),
                chatId: turn.chatId ?? null,
              };
            })()""",
            label="wait_ui_stream_idle",
        )
        if isinstance(raw, dict) and raw.get("isStreaming") is not True:
            print(
                f"E2E_UI_STREAM_IDLE: chatId={raw.get('chatId')!r}",
                flush=True,
            )
            return True
        await asyncio.sleep(1.0)
    print("E2E_UI_STREAM_IDLE: timeout — proceed STREAM_CONVERGE anyway", flush=True)
    return False


def require_browser_gate_triggered(*, last_tool: str, takeover_pending: bool) -> None:
    if takeover_pending or last_tool.endswith("browser_ask_human_tool"):
        return
    raise AssertionError(
        "Model never triggered browser takeover gate "
        f"(lastTool={last_tool!r}, takeoverPending={takeover_pending}). "
        "Expected browser_ask_human_tool with extension in-chat banner."
    )


async def probe_browser_tool_progress(chat: McpChatSession) -> dict[str, object]:
    probe = await gate_probe_evaluate(
        chat, BROWSER_TOOL_PROGRESS_JS, label="tool_progress"
    )
    if probe is None:
        return {"active": False, "muxStall": True}
    return probe if isinstance(probe, dict) else {"active": False}


async def maybe_recover_browser_takeover(
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
    recover = await gate_probe_evaluate(
        chat,
        RECOVER_BROWSER_TAKEOVER_JS,
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


async def api_browser_gate_progress(
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


async def wait_for_browser_ask_human_gate(
    chat: McpChatSession,
    *,
    chat_id: str | None = None,
    api_url: str | None = None,
    timeout_sec: float = BROWSER_GATE_WAIT_SEC,
) -> tuple[str, bool, bool]:
    """Return (lastTool, takeoverPending, api_hitl_confirmed)."""
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
            api_progress = await api_browser_gate_progress(
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
                    return api_tool or "browser_ask_human_tool", True, True
        progress = await probe_browser_tool_progress(chat)
        if progress.get("muxStall") is True:
            mux_degraded = True
        last_tool = str(progress.get("lastTool") or "")
        takeover_pending = progress.get("takeoverPending") is True
        if takeover_pending or last_tool.endswith("browser_ask_human_tool"):
            return last_tool, takeover_pending, False

        if progress.get("muxStall") is True:
            mux_degraded = True
            api_progress = await api_browser_gate_progress(
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
                    return api_tool or "browser_ask_human_tool", True, True
                if api_tool and not last_tool:
                    last_tool = api_tool

        banner = await gate_probe_evaluate(chat, BANNER_ASSERT_JS, label="gate_banner")
        if isinstance(banner, dict) and (
            banner.get("ready") is True or banner.get("storePending") is True
        ):
            return last_tool or "browser_ask_human_tool", True, False

        recovered = await maybe_recover_browser_takeover(
            chat,
            started_at=gate_started,
            last_recovery_at=last_recovery_at,
        )
        if recovered is not None:
            tool, pending = recovered
            return tool, pending, False

        await asyncio.sleep(1.0)
    return last_tool, takeover_pending, False


async def wait_takeover_banner(
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
        raw = await gate_probe_evaluate(chat, BANNER_ASSERT_JS, label="wait_banner")
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
        recovered = await maybe_recover_browser_takeover(
            chat,
            started_at=banner_started,
            last_recovery_at=last_recovery_at,
        )
        if recovered is not None:
            raw = await gate_probe_evaluate(
                chat, BANNER_ASSERT_JS, label="banner_after_recovery"
            )
            if raw is None:
                await asyncio.sleep(1.0)
                continue
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
        await asyncio.sleep(1.0)
    raise AssertionError(f"Browser takeover banner did not appear: {last}")


async def prepare_browser_turn(chat: McpChatSession) -> None:
    connect = await chat.evaluate(
        SET_BROWSER_CONNECT_JS, await_promise=False, recv_timeout=15.0
    )
    assert isinstance(connect, dict)
    assert connect.get("ok") is True, f"Failed to set browser source connect: {connect}"
    enabled = await chat.evaluate(
        ENABLE_BROWSER_JS, await_promise=False, recv_timeout=15.0
    )
    assert isinstance(enabled, dict)
    assert enabled.get("ok") is True, f"Failed to enable browser in chat session: {enabled}"
    await chat.evaluate(ENABLE_YOLO_JS, await_promise=False, recv_timeout=15.0)
