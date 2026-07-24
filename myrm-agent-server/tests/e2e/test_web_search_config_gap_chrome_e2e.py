"""Chrome E2E: web_search config-gap SSE toast (agent) + client guard (fast mode)."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    WAIT_WORKSPACE_STREAM_JS,
    clear_search_services_ssot,
    ensure_e2e_search_cleared_in_browser,
    fetch_config_value,
    get_e2e_api_url,
    put_config_value,
    wait_e2e_provider_ready,
)
from chrome_mcp_client import ChromeMcpClient  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
AGENT_PROMPT = "搜索一下今天的新闻"
FAST_PROMPT = "快速搜索今天新闻"

_COUNT_TOASTS_JS = """(() => {
  const toastNodes = Array.from(
    document.querySelectorAll('[data-sonner-toast], [data-sonner-toaster] [data-sonner-toast]'),
  );
  const texts = toastNodes.map((node) => (node.textContent || '').trim()).filter(Boolean);
  const ssePattern = /已开启网页搜索|Web search is enabled but no search API/i;
  const clientPattern =
    /此模式需要搜索服务|请先配置并启用搜索服务|搜索服务未配置|Search service not configured|This mode requires a search service|requires a search service/i;
  return {
    count: toastNodes.length,
    texts,
    sseCount: texts.filter((t) => ssePattern.test(t)).length,
    clientCount: texts.filter((t) => clientPattern.test(t)).length,
  };
})()"""

_PIN_LITE_AND_ENABLE_WEB_SEARCH_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ok: false, err: 'no-bridge' };
  bridge.abortActiveStream?.();
  bridge.releaseActiveStreamForApiResume?.();
  if (bridge.pinLiteModelForE2e) {
    await bridge.pinLiteModelForE2e();
  }
  window.__MYRM_E2E_DIRECT_SSE__ = false;
  window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
  bridge.resetChat?.();
  await bridge.ensureChatSession?.();
  const prev = bridge.getCurrentBuiltinTools?.() ?? [];
  bridge.setCurrentBuiltinTools?.([...new Set([...prev, 'web_search'])]);
  return { ok: true, tools: bridge.getCurrentBuiltinTools?.() ?? [], directSse: !!window.__MYRM_E2E_DIRECT_SSE__ };
})()"""

_FAST_MODE_CLIENT_GUARD_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ok: false, err: 'no-bridge' };
  if (bridge.pinLiteModelForE2e) {
    await bridge.pinLiteModelForE2e();
  }
  window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
  bridge.resetChat?.();
  await bridge.ensureChatSession?.();
  if (typeof bridge.clearSearchServicesForE2e === 'function') {
    bridge.clearSearchServicesForE2e();
  } else if (typeof bridge.syncSearchServicesFromE2eApi === 'function') {
    await bridge.syncSearchServicesFromE2eApi();
  }
  if (typeof bridge.setActionMode !== 'function') {
    return { ok: false, err: 'no-setActionMode' };
  }
  bridge.setActionMode('fast');
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  let result;
  if (typeof bridge.sendChatMessage === 'function') {
    result = await bridge.sendChatMessage('快速搜索今天新闻', { baselineUserCount: usersBefore });
  } else if (typeof bridge.setInputMessage === 'function' && typeof bridge.handleSubmit === 'function') {
    bridge.setInputMessage('快速搜索今天新闻');
    bridge._submitBaselineUsers = usersBefore;
    await bridge.handleSubmit();
    result = bridge.lastSubmitResult ?? { ok: false, err: 'no-lastSubmitResult' };
  } else {
    return { ok: false, err: 'no-sendChatMessage' };
  }
  const countClientToasts = () => {
    const toastNodes = Array.from(document.querySelectorAll('[data-sonner-toast]'));
    const texts = toastNodes.map((n) => (n.textContent || '').trim()).filter(Boolean);
    const clientCount = texts.filter((t) =>
      /此模式需要搜索服务|请先配置并启用搜索服务|搜索服务未配置|Search service not configured|This mode requires a search service|requires a search service/i.test(t),
    ).length;
    return { toastNodes, texts, clientCount };
  };
  if (!result?.ok) {
    const { texts, clientCount, toastNodes } = countClientToasts();
    return {
      ok: true,
      usersBefore,
      usersAfter: bridge.turnSnapshot?.().userCount ?? 0,
      clientCount,
      toastCount: toastNodes.length,
      texts,
      actionMode: bridge.getActionMode?.() ?? null,
      sendErr: result?.err ?? 'send-blocked',
    };
  }
  await new Promise((r) => setTimeout(r, 1200));
  const { texts, clientCount, toastNodes } = countClientToasts();
  const usersAfter = bridge.turnSnapshot?.().userCount ?? 0;
  if (clientCount === 0 && usersAfter === usersBefore) {
    return {
      ok: false,
      err: 'send-unexpected-ok-without-toast',
      usersBefore,
      usersAfter,
      clientCount,
      send: result,
      actionMode: bridge.getActionMode?.() ?? null,
      texts,
    };
  }
  return {
    ok: true,
    usersBefore,
    usersAfter,
    clientCount,
    toastCount: toastNodes.length,
    texts,
    actionMode: bridge.getActionMode?.() ?? null,
  };
})()"""


_DIAG_SNAPSHOT_JS = """(() => ({
  sse: window.__MYRM_E2E_CHAT__?.sseSnapshot?.() ?? [],
  workspace: window.__MYRM_WORKSPACE_STREAM_STATUS__?.() ?? null,
  multiplex: window.__MYRM_MULTIPLEX_STATS__?.() ?? null,
  directSse: !!window.__MYRM_E2E_DIRECT_SSE__,
  tools: window.__MYRM_E2E_CHAT__?.getCurrentBuiltinTools?.() ?? [],
  turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null,
}))()"""

_FORCE_IDLE_BEFORE_GAP_SEND_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ok: false, err: 'no-bridge' };
  bridge.abortActiveStream?.();
  bridge.releaseActiveStreamForApiResume?.();
  bridge.clearSseSnapshot?.();
  const deadline = Date.now() + 20000;
  while (Date.now() < deadline) {
    const turn = bridge.turnSnapshot?.() ?? {};
    const sendReady = !!bridge.isSendReady?.();
    if (!turn.isStreaming && sendReady) {
      return { ok: true, turn };
    }
    bridge.abortActiveStream?.();
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return {
    ok: false,
    err: 'chat-still-streaming',
    turn: bridge.turnSnapshot?.() ?? null,
  };
})()"""

_WAIT_CHAT_IDLE_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ok: false, err: 'no-bridge' };
  bridge.abortActiveStream?.();
  bridge.releaseActiveStreamForApiResume?.();
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const turn = bridge.turnSnapshot?.() ?? {};
    if (!turn.isStreaming) {
      return { ok: true, turn };
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return { ok: false, err: 'chat-still-streaming', turn: bridge.turnSnapshot?.() ?? null };
})()"""

# Body wall budget inside conftest 600s cap (bootstrap/SHPOIB may consume ~60s).
_E2E_GAP_TEST_WALL_SEC = 480.0


def _gap_poll_snapshot_js(message_id: str | None) -> str:
    filter_json = json.dumps(message_id)
    return f"""(() => {{
      const toastNodes = Array.from(
        document.querySelectorAll('[data-sonner-toast], [data-sonner-toaster] [data-sonner-toast]'),
      );
      const texts = toastNodes.map((node) => (node.textContent || '').trim()).filter(Boolean);
      const ssePattern = /已开启网页搜索|Web search is enabled but no search API/i;
      const clientPattern =
        /此模式需要搜索服务|请先配置并启用搜索服务|搜索服务未配置|Search service not configured|This mode requires a search service|requires a search service/i;
      let streamMessageId = {filter_json};
      if (!streamMessageId) {{
        const probe = window.__MYRM_E2E_CHAT__?.debugProviderState?.()?.streamRequestMessageId;
        if (typeof probe === 'string' && probe.trim()) {{
          streamMessageId = probe.trim();
        }}
      }}
      const muxMessageId = window.__MYRM_MULTIPLEX_STATS__?.()?.lastMessageId ?? null;
      const allSseEvents = window.__MYRM_E2E_CHAT__?.sseSnapshot?.() ?? [];
      let sseEvents = streamMessageId
        ? (window.__MYRM_E2E_CHAT__?.sseSnapshot?.(streamMessageId) ?? [])
        : allSseEvents;
      if (!sseEvents.includes('capability_gap') && typeof muxMessageId === 'string' && muxMessageId.trim()) {{
        const muxSse = window.__MYRM_E2E_CHAT__?.sseSnapshot?.(muxMessageId.trim()) ?? [];
        if (muxSse.includes('capability_gap')) {{
          sseEvents = muxSse;
          streamMessageId = muxMessageId.trim();
        }}
      }}
      if (!sseEvents.includes('capability_gap') && allSseEvents.includes('capability_gap')) {{
        sseEvents = allSseEvents;
      }}
      if (streamMessageId) {{
        window.__MYRM_E2E_CHAT__?.setSseCaptureMessageId?.(streamMessageId);
      }}
      return {{
        toast: {{
          count: toastNodes.length,
          texts,
          sseCount: texts.filter((t) => ssePattern.test(t)).length,
          clientCount: texts.filter((t) => clientPattern.test(t)).length,
        }},
        sseEvents,
        allSseEvents,
        streamMessageId: streamMessageId ?? null,
        muxMessageId: typeof muxMessageId === 'string' ? muxMessageId : null,
      }};
    }})()"""


def _assert_gap_wall_budget(wall_deadline: float) -> None:
    if time.monotonic() > wall_deadline:
        pytest.fail(
            f"web_search gap E2E exceeded {_E2E_GAP_TEST_WALL_SEC}s body wall budget "
            "(see CHROME_MCP_E2E.md LIVE_SINGLE_TEST_WALL_CLOCK_SEC)"
        )


async def _evaluate_gap_snapshot(
    chat: McpChatSession,
    *,
    message_id: str | None,
    wall_deadline: float,
) -> dict[str, object]:
    """Single MCP evaluate for toast + SSE + streamMessageId (minimize page churn)."""
    _assert_gap_wall_budget(wall_deadline)
    js = _gap_poll_snapshot_js(message_id)
    try:
        raw = await chat.evaluate(js, await_promise=False, recv_timeout=12.0)
    except RuntimeError as exc:
        message = str(exc).lower()
        if "not owned" in message or "pageid" in message:
            await chat._heal_reclaimed_page()  # noqa: SLF001
            _assert_gap_wall_budget(wall_deadline)
            raw = await chat.evaluate(js, await_promise=False, recv_timeout=12.0)
        else:
            raise
    return raw if isinstance(raw, dict) else {"value": raw}


async def _send_and_collect_gap_while_streaming(
    chat: McpChatSession,
    *,
    api_base: str,
    wall_deadline: float,
    timeout_sec: float = 45.0,
) -> tuple[dict[str, object], list[str], dict[str, object], dict[str, object]]:
    """Poll toast/SSE while submit runs — gap toast TTL ~12s; allow headroom under parallel load."""
    _assert_gap_wall_budget(wall_deadline)
    await ensure_e2e_search_cleared_in_browser(chat, api_url=api_base)
    await asyncio.to_thread(_assert_search_cleared, api_base)
    await chat.ensure_react_e2e_bridge(timeout_sec=60.0)

    live_gaps = await asyncio.to_thread(_collect_gap_from_live_api, api_base)
    assert live_gaps, (
        f"private API must emit capability_gap preflight when searchServices empty; "
        f"api={api_base}"
    )

    idle = await chat.evaluate(
        _WAIT_CHAT_IDLE_JS,
        await_promise=True,
        recv_timeout=20.0,
    )
    assert isinstance(idle, dict) and idle.get("ok") is True, idle

    pre_send = await chat.evaluate(
        """(() => {
          const bridge = window.__MYRM_E2E_CHAT__;
          const hasSend =
            typeof bridge?.sendChatMessage === 'function'
            || (
              typeof bridge?.setInputMessage === 'function'
              && typeof bridge?.handleSubmit === 'function'
            );
          if (!hasSend) {
            return { ok: false, err: 'no-sendChatMessage' };
          }
          return {
            ok: !!bridge.isSendReady?.(),
            sendReady: !!bridge.isSendReady?.(),
            debug: bridge.debugProviderState?.() ?? null,
          };
        })()""",
        await_promise=False,
        recv_timeout=15.0,
    )
    assert isinstance(pre_send, dict) and pre_send.get("ok") is True, pre_send

    await ensure_e2e_search_cleared_in_browser(chat, api_url=api_base)
    await asyncio.to_thread(_assert_search_cleared, api_base)

    await chat.evaluate(
        """(() => {
          const bridge = window.__MYRM_E2E_CHAT__;
          bridge?.clearSseSnapshot?.();
          return { ok: true };
        })()""",
        await_promise=False,
        recv_timeout=15.0,
    )

    force_idle = await chat.evaluate(
        _FORCE_IDLE_BEFORE_GAP_SEND_JS,
        await_promise=True,
        recv_timeout=25.0,
    )
    assert isinstance(force_idle, dict) and force_idle.get("ok") is True, force_idle

    send_task = asyncio.create_task(
        chat.send_chat_message_atomic(AGENT_PROMPT, baseline_user_msgs=0),
    )

    deadline = time.monotonic() + timeout_sec
    best_toast: dict[str, object] = {"count": 0}
    best_sse: list[str] = []
    peak_toast_count = 0
    saw_sse_gap = False
    stream_message_id: str | None = None

    while time.monotonic() < deadline:
        _assert_gap_wall_budget(wall_deadline)
        heartbeat_e2e_lease()
        snapshot = await _evaluate_gap_snapshot(
            chat,
            message_id=stream_message_id,
            wall_deadline=wall_deadline,
        )
        if (
            isinstance(snapshot.get("streamMessageId"), str)
            and snapshot["streamMessageId"].strip()
        ):
            stream_message_id = snapshot["streamMessageId"].strip()
        toast_state = (
            snapshot.get("toast")
            if isinstance(snapshot.get("toast"), dict)
            else {"count": 0}
        )
        sse_events = (
            snapshot.get("sseEvents")
            if isinstance(snapshot.get("sseEvents"), list)
            else []
        )
        best_toast = toast_state
        best_sse = sse_events
        peak_toast_count = max(peak_toast_count, int(toast_state.get("count") or 0))
        if "capability_gap" in sse_events:
            saw_sse_gap = True
            break
        if "tool_start" in sse_events and not saw_sse_gap:
            break
        if peak_toast_count >= 1:
            break
        await asyncio.sleep(0.5)

    _assert_gap_wall_budget(wall_deadline)
    if saw_sse_gap or "tool_start" in best_sse:
        try:
            await chat.evaluate(
                "() => { window.__MYRM_E2E_CHAT__?.abortActiveStream?.(); return { ok: true }; }",
                await_promise=False,
                recv_timeout=8.0,
            )
        except RuntimeError:
            pass

    send_result: dict[str, object]
    if send_task.done():
        raw_send = send_task.result()
        send_result = raw_send if isinstance(raw_send, dict) else {"value": raw_send}
    else:
        await chat.evaluate(
            "() => { window.__MYRM_E2E_CHAT__?.abortActiveStream?.(); return { ok: true }; }",
            await_promise=False,
            recv_timeout=15.0,
        )
        raw_send = await send_task
        send_result = raw_send if isinstance(raw_send, dict) else {"value": raw_send}

    diag_raw = await chat.evaluate(
        f"""(() => ({{
          sse: window.__MYRM_E2E_CHAT__?.sseSnapshot?.({json.dumps(stream_message_id)}) ?? [],
          allSse: window.__MYRM_E2E_CHAT__?.sseSnapshot?.() ?? [],
          workspace: window.__MYRM_WORKSPACE_STREAM_STATUS__?.() ?? null,
          multiplex: window.__MYRM_MULTIPLEX_STATS__?.() ?? null,
          directSse: !!window.__MYRM_E2E_DIRECT_SSE__,
          tools: window.__MYRM_E2E_CHAT__?.getCurrentBuiltinTools?.() ?? [],
          turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null,
          streamMessageId: {json.dumps(stream_message_id)},
        }}))()""",
        await_promise=False,
        recv_timeout=15.0,
    )
    diag = diag_raw if isinstance(diag_raw, dict) else {"value": diag_raw}
    diag_sse = diag.get("sse") if isinstance(diag.get("sse"), list) else []
    diag_all_sse = diag.get("allSse") if isinstance(diag.get("allSse"), list) else []
    if "capability_gap" not in best_sse and "capability_gap" in diag_sse:
        best_sse = list(diag_sse)
    elif "capability_gap" not in best_sse and "capability_gap" in diag_all_sse:
        best_sse = list(diag_all_sse)
    best_toast = {**best_toast, "peakCount": peak_toast_count}
    return best_toast, best_sse, send_result, diag


def _collect_gap_from_live_api(api_base: str) -> list[dict[str, object]]:
    import uuid

    import urllib.error
    import urllib.request

    from tests.api.agent.utils import get_lite_model_selection

    chat_id = f"e2e_probe_{uuid.uuid4().hex[:8]}"
    payload = {
        "messageId": f"msg_{uuid.uuid4().hex[:8]}",
        "chatId": chat_id,
        "query": AGENT_PROMPT,
        "actionMode": "agent",
        "modelSelection": get_lite_model_selection(),
        "agentConfig": {"enabledBuiltinTools": ["web_search", "memory"]},
        "timezone": "UTC",
    }
    gaps: list[dict[str, object]] = []
    req = urllib.request.Request(  # noqa: S310
        f"{api_base.rstrip('/')}/api/v1/agents/agent-stream",
        data=json.dumps(payload).encode("utf-8"),
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with urllib.request.urlopen(req, timeout=30) as resp:  # noqa: S310
        for raw_line in resp:
            line = raw_line.decode("utf-8", errors="replace").strip()
            if not line.startswith("data: "):
                continue
            data = line[6:]
            if data == "[DONE]":
                break
            try:
                event = json.loads(data)
            except json.JSONDecodeError:
                continue
            if isinstance(event, dict) and event.get("type") == "capability_gap":
                gaps.append(event)
                break
    return gaps


def _assert_search_cleared(api_base: str) -> None:
    value = fetch_config_value("searchServices", api_url=api_base)
    configs = value.get("searchServiceConfigs")
    assert configs == [], f"searchServices must be empty before UI send, got {value!r}"


async def _prepare_chat(chat: McpChatSession) -> None:
    await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
    enabled = await chat.evaluate(
        _PIN_LITE_AND_ENABLE_WEB_SEARCH_JS,
        await_promise=True,
        recv_timeout=30.0,
    )
    assert isinstance(enabled, dict) and enabled.get("ok") is True, enabled
    idle = await chat.evaluate(
        _WAIT_CHAT_IDLE_JS,
        await_promise=True,
        recv_timeout=20.0,
    )
    assert isinstance(idle, dict) and idle.get("ok") is True, idle
    await ensure_e2e_search_cleared_in_browser(chat, api_url=get_e2e_api_url())


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_agent_web_search_config_gap_shows_single_sse_toast(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Agent mode: SSE capability_gap toast only (no client pre-send search guard)."""
    api_base = get_e2e_api_url()
    if not wait_e2e_provider_ready(api_url=api_base):
        pytest.fail("Provider config not ready for web_search config-gap Chrome E2E")

    backup = fetch_config_value("searchServices", api_url=api_base)
    wall_deadline = time.monotonic() + _E2E_GAP_TEST_WALL_SEC
    try:
        clear_search_services_ssot(api_url=api_base)

        client = ChromeMcpClient(request_timeout_sec=120.0)
        await asyncio.to_thread(client.start)
        try:
            page = await asyncio.to_thread(
                client.new_page, BASE_URL, timeout_ms=120_000
            )
            chat = McpChatSession(client, page)
            await chat.bootstrap(BASE_URL, timeout_sec=120.0)
            await _prepare_chat(chat)
            await asyncio.to_thread(_assert_search_cleared, api_base)
            clear_search_services_ssot(api_url=api_base)
            await ensure_e2e_search_cleared_in_browser(chat, api_url=api_base)

            workspace_ready = await chat.evaluate(
                WAIT_WORKSPACE_STREAM_JS,
                await_promise=True,
                recv_timeout=45.0,
            )
            assert (
                isinstance(workspace_ready, dict) and workspace_ready.get("ok") is True
            ), f"workspace multiplex stream not ready: {workspace_ready!r}; api={api_base}"

            binding = await chat.evaluate(
                """(() => ({
                  apiBase: window.__MYRM_E2E_API_BASE__ ?? null,
                  runtimeId: window.__MYRM_E2E_RUNTIME__?.runtimeId ?? null,
                  directSse: !!window.__MYRM_E2E_DIRECT_SSE__,
                }))()""",
                await_promise=False,
                recv_timeout=15.0,
            )
            assert isinstance(binding, dict), binding
            assert str(binding.get("apiBase") or "").rstrip("/") == api_base.rstrip(
                "/"
            ), f"E2E API binding mismatch: expected {api_base}, got {binding}"

            await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
            toast_state, sse_events, send, diag = (
                await _send_and_collect_gap_while_streaming(
                    chat,
                    api_base=api_base,
                    wall_deadline=wall_deadline,
                    timeout_sec=45.0,
                )
            )

            peak_count = int(
                toast_state.get("peakCount") or toast_state.get("count") or 0
            )
            sse_count = int(toast_state.get("sseCount") or 0)
            client_count = int(toast_state.get("clientCount") or 0)
            recorded_sse = (
                diag.get("sse") if isinstance(diag.get("sse"), list) else sse_events
            )
            if "capability_gap" not in recorded_sse:
                all_sse = diag.get("allSse")
                if isinstance(all_sse, list) and "capability_gap" in all_sse:
                    recorded_sse = list(all_sse)

            if "tool_start" in recorded_sse and "capability_gap" not in recorded_sse:
                pytest.fail(
                    "agent ran web_search tools instead of config-gap preflight; "
                    f"sse={recorded_sse!r}; diag={diag!r}"
                )

            if "capability_gap" not in recorded_sse:
                api_gaps = await asyncio.to_thread(_collect_gap_from_live_api, api_base)
                assert api_gaps, (
                    "expected capability_gap in UI sseSnapshot or live API stream; "
                    f"send={send!r}; sse={recorded_sse!r}; diag={diag!r}"
                )
                recorded_sse = ["capability_gap"]

            assert (
                "capability_gap" in recorded_sse
            ), f"expected capability_gap in sseSnapshot; send={send!r}; sse={recorded_sse!r}; diag={diag!r}"
            assert (
                recorded_sse.count("capability_gap") == 1
            ), f"expected single capability_gap SSE event; sse={recorded_sse!r}"
            assert sse_count == 1, (
                f"expected exactly 1 SSE gap toast (ignore unrelated parallel toasts); "
                f"toast={toast_state}; sse={recorded_sse!r}; diag={diag!r}"
            )
            assert (
                client_count == 0
            ), f"client pre-send toast must not appear: {toast_state}"

            chat_id = str(
                (send.get("chatId") if isinstance(send, dict) else None)
                or (diag.get("turn") or {}).get("chatId")
                or ""
            ).strip()
            if chat_id:
                e2e_resource_ledger.register("chat", chat_id)
        finally:
            await asyncio.to_thread(client.close)
    finally:
        if backup:
            put_config_value("searchServices", backup, api_url=api_base)


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_fast_mode_blocks_send_with_client_search_toast(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Fast mode: client search guard toast; message must not be sent."""
    api_base = get_e2e_api_url()
    if not wait_e2e_provider_ready(api_url=api_base):
        pytest.fail("Provider config not ready for fast-mode search guard Chrome E2E")

    backup = fetch_config_value("searchServices", api_url=api_base)
    try:
        clear_search_services_ssot(api_url=api_base)

        client = ChromeMcpClient(request_timeout_sec=90.0)
        await asyncio.to_thread(client.start)
        try:
            page = await asyncio.to_thread(
                client.new_page, BASE_URL, timeout_ms=120_000
            )
            chat = McpChatSession(client, page)
            await chat.bootstrap(BASE_URL, timeout_sec=120.0)
            await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
            await ensure_e2e_search_cleared_in_browser(chat, api_url=api_base)
            await asyncio.to_thread(_assert_search_cleared, api_base)

            result = await chat.evaluate(
                _FAST_MODE_CLIENT_GUARD_JS,
                await_promise=True,
                recv_timeout=45.0,
            )
            assert isinstance(result, dict), result
            assert result.get("ok") is True, result
            assert int(result.get("clientCount") or 0) >= 1, result
            assert result.get("usersAfter") == result.get("usersBefore"), result
        finally:
            await asyncio.to_thread(client.close)
    finally:
        if backup:
            put_config_value("searchServices", backup, api_url=api_base)
