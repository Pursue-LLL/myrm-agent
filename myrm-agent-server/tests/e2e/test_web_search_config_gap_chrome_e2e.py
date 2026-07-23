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
    fetch_config_value,
    get_e2e_api_url,
    put_config_value,
    wait_e2e_provider_ready,
)
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
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
  const clientPattern = /此模式需要搜索服务|Search service not configured|requires a search service/i;
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
  if (bridge.pinLiteModelForE2e) {
    await bridge.pinLiteModelForE2e();
  }
  bridge.resetChat?.();
  await bridge.ensureChatSession?.();
  const prev = bridge.getCurrentBuiltinTools?.() ?? [];
  bridge.setCurrentBuiltinTools?.([...new Set([...prev, 'web_search'])]);
  return { ok: true, tools: bridge.getCurrentBuiltinTools?.() ?? [] };
})()"""

_FAST_MODE_CLIENT_GUARD_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ok: false, err: 'no-bridge' };
  if (bridge.pinLiteModelForE2e) {
    await bridge.pinLiteModelForE2e();
  }
  bridge.resetChat?.();
  await bridge.ensureChatSession?.();
  const storeModule = await import('/src/store/useChatStore');
  const store = storeModule.default;
  store.getState().setActionMode('fast');
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  store.getState().setInputMessage('快速搜索今天新闻');
  try {
    await store.getState().sendMessage('快速搜索今天新闻', undefined);
  } catch (err) {
    return { ok: false, err: String(err), usersBefore };
  }
  await new Promise((r) => setTimeout(r, 1200));
  const toastNodes = Array.from(document.querySelectorAll('[data-sonner-toast]'));
  const texts = toastNodes.map((n) => (n.textContent || '').trim()).filter(Boolean);
  const clientCount = texts.filter((t) =>
    /此模式需要搜索服务|Search service not configured|requires a search service/i.test(t),
  ).length;
  const usersAfter = bridge.turnSnapshot?.().userCount ?? 0;
  return {
    ok: true,
    usersBefore,
    usersAfter,
    clientCount,
    toastCount: toastNodes.length,
    texts,
    actionMode: store.getState().actionMode,
  };
})()"""


async def _wait_toasts(chat: McpChatSession, *, timeout_sec: float = 20.0) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {"count": 0}
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        raw = await chat.evaluate(_COUNT_TOASTS_JS, await_promise=False, recv_timeout=15.0)
        last = raw if isinstance(raw, dict) else {"value": raw}
        if int(last.get("count") or 0) >= 1:
            return last
        await asyncio.sleep(0.5)
    return last


async def _prepare_chat(chat: McpChatSession) -> None:
    await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
    enabled = await chat.evaluate(
        _PIN_LITE_AND_ENABLE_WEB_SEARCH_JS,
        await_promise=True,
        recv_timeout=30.0,
    )
    assert isinstance(enabled, dict) and enabled.get("ok") is True, enabled


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
    try:
        put_config_value(
            "searchServices",
            {"searchServiceConfigs": []},
            api_url=api_base,
        )

        client = ChromeMcpClient(request_timeout_sec=120.0)
        await asyncio.to_thread(client.start)
        try:
            page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
            chat = McpChatSession(client, page)
            await chat.bootstrap(BASE_URL, timeout_sec=120.0)
            await _prepare_chat(chat)

            send = await chat.evaluate(
                f"""(() => {{
                  const bridge = window.__MYRM_E2E_CHAT__;
                  if (!bridge?.sendChatMessage) return {{ ok: false, err: 'no-sendChatMessage' }};
                  return Promise.resolve(
                    bridge.sendChatMessage({json.dumps(AGENT_PROMPT)}, {{ baselineUserCount: 0 }}),
                  );
                }})()""",
                await_promise=True,
                recv_timeout=120.0,
            )
            assert isinstance(send, dict) and send.get("ok") is True, send

            toast_state = await _wait_toasts(chat, timeout_sec=25.0)
            sse_events = await chat.evaluate(
                "() => window.__MYRM_E2E_CHAT__?.sseSnapshot?.() ?? []",
                await_promise=False,
                recv_timeout=15.0,
            )
            await chat.evaluate(
                "() => { window.__MYRM_E2E_CHAT__?.abortActiveStream?.(); return { ok: true }; }",
                await_promise=False,
                recv_timeout=15.0,
            )

            count = int(toast_state.get("count") or 0)
            sse_count = int(toast_state.get("sseCount") or 0)
            client_count = int(toast_state.get("clientCount") or 0)
            has_gap_event = isinstance(sse_events, list) and "capability_gap" in sse_events

            assert count == 1, f"expected exactly 1 toast, got {toast_state}"
            assert sse_count >= 1, f"expected SSE gap copy, got {toast_state}"
            assert client_count == 0, f"client pre-send toast must not appear: {toast_state}"
            assert has_gap_event, f"expected capability_gap in SSE events, got {sse_events!r}"

            chat_id = str(send.get("chatId") or "").strip()
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
        put_config_value(
            "searchServices",
            {"searchServiceConfigs": []},
            api_url=api_base,
        )

        client = ChromeMcpClient(request_timeout_sec=90.0)
        await asyncio.to_thread(client.start)
        try:
            page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
            chat = McpChatSession(client, page)
            await chat.bootstrap(BASE_URL, timeout_sec=120.0)
            await chat.ensure_react_e2e_bridge(timeout_sec=60.0)

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
