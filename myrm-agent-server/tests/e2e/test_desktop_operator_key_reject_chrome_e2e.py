"""Chrome E2E: WebUI computer_use rejects printable operators as vision key names.

Real Chrome composer → enable computer_use → send key='*' task → assert
Rejected printable operator appears in chat messages / page text.
"""

from __future__ import annotations

import asyncio
import json
import platform
import time

import pytest
from cdp_chat.mcp_ui import McpChatSession
from cdp_chat.support import (
    EvaluateIntent,
    fetch_provider_readiness_snapshot,
    get_e2e_api_url,
    get_e2e_ui_url,
    wait_e2e_provider_ready,
)

from tests.e2e.desktop_approval.constants import BASE_URL, progress
from tests.support.chrome_mcp_e2e import http_json, open_mcp_page_async
from tests.support.e2e_desktop_model_pin import ensure_desktop_basic_model_pinned_for_send
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once

_PROMPT = (
    "Call desktop_vision_tool exactly once with action=key and text=*. "
    "Do not use type or click. After the tool returns, reply DONE."
)
_REJECT = "Rejected printable operator"


def _messages_blob(api_url: str, chat_id: str) -> str:
    resp = http_json("GET", f"{api_url}/api/v1/chats/{chat_id}/messages")
    return json.dumps(resp, ensure_ascii=False, default=str)


def _trace_blob(api_url: str, chat_id: str) -> str:
    resp = http_json("GET", f"{api_url}/api/v1/statistics/session/{chat_id}/trace")
    return json.dumps(resp, ensure_ascii=False, default=str)


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="DESKTOP",
    private_reason="exclusive_backend",
)
@pytest.mark.chrome_e2e_desktop
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.skipif(platform.system() != "Darwin", reason="macOS computer_use only")
@pytest.mark.asyncio
async def test_chrome_ui_operator_as_key_rejected(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready(timeout_sec=120.0, poll_interval_sec=2.0):
        readiness = fetch_provider_readiness_snapshot()
        pytest.fail(f"Provider not ready for chrome e2e: {readiness}")

    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    deadline = time.monotonic() + 540.0

    async with open_mcp_page_async(ui_url, timeout_ms=120_000) as (client, page):
        chat = McpChatSession(client=client, page=page)
        await chat.bootstrap(BASE_URL, navigate=False, timeout_sec=90.0)
        await chat.click_new_chat(timeout_sec=60.0)
        await chat.ensure_chat_surface(BASE_URL, timeout_sec=90.0)
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)

        progress("enable computer_use")
        tools_setup = await chat.enable_computer_use()
        assert tools_setup.get("ok") is True, tools_setup
        tools_locked = await chat.evaluate(
            """(() => {
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge?.setCurrentBuiltinTools) {
                return { ok: false, err: 'no-builtin-tools-bridge' };
              }
              bridge.setCurrentBuiltinTools(['computer_use']);
              return { ok: true, tools: bridge.getCurrentBuiltinTools?.() ?? [] };
            })()""",
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        assert isinstance(tools_locked, dict) and tools_locked.get("ok") is True, tools_locked

        pin = await ensure_desktop_basic_model_pinned_for_send(chat)
        progress(f"model pin: {pin.get('debug')}")

        provider_debug = await chat.evaluate(
            """(() => window.__MYRM_E2E_CHAT__?.debugProviderState?.() ?? null)()""",
            intent=EvaluateIntent.SYNC_PROBE,
        )
        model_label = ""
        if isinstance(provider_debug, dict):
            model_label = str(
                provider_debug.get("selectedModel")
                or provider_debug.get("model")
                or provider_debug.get("modelId")
                or ""
            )
        progress(f"UI model={model_label!r} provider_debug={provider_debug}")

        send_result = await chat.send_message(_PROMPT, _PROMPT)
        chat_id = str(
            (send_result.get("started") or {}).get("chatId")
            or (send_result.get("submit") or {}).get("chatId")
            or ""
        ).strip()
        if not chat_id:
            chat_id = str((await chat.bridge_chat_id()) or "").strip()
        assert chat_id, f"missing chat id: {send_result}"
        e2e_resource_ledger.register("chat", chat_id)
        progress(f"sent chat_id={chat_id}")

        after = await chat.wait_turn_done(_PROMPT, timeout_sec=240, chat_id_hint=chat_id)
        progress(f"turn done: {after}")
        heartbeat_once()

        found = False
        blob = ""
        while time.monotonic() < deadline:
            page_text = await chat.evaluate(
                "(() => document.body?.innerText || '')()",
                intent=EvaluateIntent.SYNC_PROBE,
            )
            msg_blob = _messages_blob(api_url, chat_id)
            trace_blob = _trace_blob(api_url, chat_id)
            blob = f"{page_text}\n{msg_blob}\n{trace_blob}"
            if _REJECT in blob or "REMEDY_HINT: Printable operators" in blob:
                found = True
                break
            if "desktop_vision" in blob.lower() and ("Safety" in blob or "operator" in blob.lower()):
                # Soft signal — keep polling for exact marker.
                pass
            await asyncio.sleep(2.0)
            heartbeat_once()

        assert found, (
            f"Chrome UI turn did not surface operator reject. model={model_label!r} "
            f"chat_id={chat_id} sample={blob[:1500]!r}"
        )
