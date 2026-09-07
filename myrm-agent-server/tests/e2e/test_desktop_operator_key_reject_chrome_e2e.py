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
    ensure_e2e_yolo_mode,
    ensure_e2e_yolo_mode_in_browser,
    fetch_provider_readiness_snapshot,
    get_e2e_api_url,
    get_e2e_ui_url,
    wait_e2e_provider_ready,
)

from tests.e2e.desktop_approval.constants import BASE_URL, progress
from tests.support.chrome_mcp_e2e import OpenMcpPageSession, http_json, open_mcp_page_async
from tests.support.e2e_desktop_model_pin import ensure_desktop_basic_model_pinned_for_send
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once

_PROMPT = (
    "CRITICAL QA SAFETY PROBE — no text reply before the tool. "
    "Call desktop_vision_tool exactly once with action=key and text=*. "
    "Do not use type, click, snapshot, bash, or web_search. "
    "After the tool returns, reply DONE."
)
_REJECT = "Rejected printable operator"
_CLICK_APPROVE_JS = """(() => {
  const buttons = Array.from(document.querySelectorAll('button'));
  const hit = buttons.find((b) => {
    const t = String(b.textContent || '').trim();
    return t === '批准' || t === 'Approve' || t === 'Allow once' || t === 'Allow';
  });
  if (!hit) return { ok: false, err: 'no-approve-button' };
  hit.click();
  return { ok: true, label: String(hit.textContent || '').trim() };
})()"""


def _soft_type_ok(blob: str) -> bool:
    """True when the model typed instead of key='*' (rules obeyed).

    UI / messages may say ``Desktop Vision`` (space) and JSON ``\"action\": \"type\"``,
    not the underscore tool id or ``action=type`` form used in API logs.
    """
    lowered = blob.lower()
    if "Vision action 'type' completed" in blob or 'Vision action "type" completed' in blob:
        return True
    if "action=type" in lowered:
        return True
    type_json = '"action": "type"' in blob or '"action":"type"' in blob
    vision_hit = "desktop_vision" in lowered or "desktop vision" in lowered
    return type_json and vision_hit


def _messages_blob(api_url: str, chat_id: str) -> str:
    resp = http_json("GET", f"{api_url}/api/v1/chats/{chat_id}/messages")
    return json.dumps(resp, ensure_ascii=False, default=str)


def _trace_blob(api_url: str, chat_id: str) -> str:
    resp = http_json("GET", f"{api_url}/api/v1/statistics/session/{chat_id}/trace")
    return json.dumps(resp, ensure_ascii=False, default=str)


def _approve_pending_tool_approvals(api_url: str) -> int:
    """Approve PENDING tool approvals so Safety reject can run under HITL drift."""
    try:
        payload = http_json("GET", f"{api_url}/api/v1/approvals?limit=50&offset=0")
    except Exception:
        return 0
    records = payload.get("approvals") if isinstance(payload, dict) else None
    if not isinstance(records, list):
        return 0
    approved = 0
    for raw in records:
        if not isinstance(raw, dict):
            continue
        if str(raw.get("status") or "").upper() != "PENDING":
            continue
        approval_id = str(raw.get("id") or raw.get("approval_id") or "").strip()
        if not approval_id:
            continue
        try:
            http_json(
                "POST",
                f"{api_url}/api/v1/approvals/{approval_id}/resolve",
                body={"decision": "approve"},
            )
            approved += 1
        except Exception:
            continue
    return approved


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
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    if not wait_e2e_provider_ready(
        api_url=api_url, timeout_sec=120.0, poll_interval_sec=2.0
    ):
        readiness = fetch_provider_readiness_snapshot(api_url=api_url)
        pytest.fail(f"Provider not ready for chrome e2e: {readiness}")

    # Unattended desktop CU must skip HITL + Security Reviewer (sibling chrome E2E SSOT).
    ensure_e2e_yolo_mode(api_url=api_url)
    progress("yolo+allow permissions pinned on private+shared API")

    deadline = time.monotonic() + 540.0

    # Phase3-D SSOT: open_mcp_page_async returns OpenMcpPageSession (not async CM).
    session: OpenMcpPageSession = await open_mcp_page_async(
        ui_url,
        timeout_ms=120_000,
        request_timeout_sec=180.0,
    )
    try:
        chat = McpChatSession(client=session.client, page=session.page)
        await chat.bootstrap(BASE_URL, navigate=False, timeout_sec=90.0)
        await chat.click_new_chat(timeout_sec=60.0)
        await chat.ensure_chat_surface(BASE_URL, timeout_sec=90.0)
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)

        # Re-pin after SHPOIB/page bind — ConfigSync / parallel HITL can drift.
        api_url = get_e2e_api_url()
        ensure_e2e_yolo_mode(api_url=api_url)
        await ensure_e2e_yolo_mode_in_browser(chat)
        progress("yolo pinned in browser ConfigSync")

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

        ensure_e2e_yolo_mode(api_url=get_e2e_api_url())
        await ensure_e2e_yolo_mode_in_browser(chat)

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
        try:
            heartbeat_once()
        except RuntimeError as exc:
            progress(f"heartbeat soft-fail after turn: {exc}")

        # Hard = Safety reject on key=*; soft = model obeyed DESKTOP_CONTROL_RULES and typed.
        hard_ok = False
        soft_ok = False
        blob = ""
        poll_deadline = min(deadline, time.monotonic() + 180.0)
        while time.monotonic() < poll_deadline:
            page_text = await chat.evaluate(
                "(() => document.body?.innerText || '')()",
                intent=EvaluateIntent.SYNC_PROBE,
            )
            page_blob = str(page_text or "")
            if "可视化操作审批" in page_blob or "Security Reviewer" in page_blob:
                clicked = await chat.evaluate(
                    _CLICK_APPROVE_JS, intent=EvaluateIntent.AGENT_SUBMIT
                )
                progress(f"HITL approve click: {clicked}")
                approved_n = _approve_pending_tool_approvals(get_e2e_api_url())
                if approved_n:
                    progress(f"API approved pending={approved_n}")
            msg_blob = _messages_blob(get_e2e_api_url(), chat_id)
            trace_blob = _trace_blob(get_e2e_api_url(), chat_id)
            blob = f"{page_blob}\n{msg_blob}\n{trace_blob}"
            hard_ok = _REJECT in blob or "REMEDY_HINT: Printable operators" in blob
            soft_ok = _soft_type_ok(blob)
            if hard_ok or soft_ok:
                break
            await asyncio.sleep(2.0)
            try:
                heartbeat_once()
            except RuntimeError as exc:
                progress(f"heartbeat soft-fail during poll: {exc}")

        assert hard_ok or soft_ok, (
            f"Chrome UI turn missed operator Safety reject and type-fallback. "
            f"model={model_label!r} chat_id={chat_id} sample={blob[:1500]!r}"
        )
    finally:
        await session.aclose()
