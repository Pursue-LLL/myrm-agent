"""Chrome LIVE_AGENT E2E: user clicks inline A2UI button → ui_action user message."""

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
    chat_user_message_count,
    fetch_chat_messages,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)
from cdp_chat_ui import chat_id_from_path  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

E2E_PROMPT = (
    "Call render_ui_tool exactly once. Required arguments: "
    'title="E2E_UI_MARKER_ALPHA"; '
    'components=['
    '{"id":"t1","type":"text","props":{"text":"E2E_UI_MARKER_BETA"}},'
    '{"id":"btn_confirm","type":"button","props":{"label":"E2E_UI_CLICK_CONFIRM","variant":"primary"},'
    '"events":{"onClick":"confirm_restart"}}'
    ']; '
    'root_ids=["t1","btn_confirm"]; '
    'actions=[{"id":"confirm_restart","type":"submit","label":"Confirm restart"}]. '
    "Every component MUST include a type field. "
    "Do not use any other tools. After render_ui_tool succeeds, reply DONE."
)

_ENABLE_RENDER_UI_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setCurrentBuiltinTools) {
    return { ok: false, err: 'no-bridge' };
  }
  bridge.setCurrentBuiltinTools(['render_ui']);
  const tools = bridge.getCurrentBuiltinTools?.() ?? [];
  return { ok: tools.includes('render_ui'), tools };
})()"""

_INLINE_UI_READY_JS = """(() => {
  const assistant = document.querySelector('[data-test-id="assistant-message"]');
  const root = assistant || document.querySelector('main');
  const text = root?.innerText || '';
  const hasTitle = /E2E_UI_MARKER_ALPHA/.test(text);
  const hasBody = /E2E_UI_MARKER_BETA/.test(text);
  const sending = !!document.querySelector('main')?.querySelector('button[aria-label="Stop"]');
  const buttons = Array.from(root?.querySelectorAll('button') || []);
  const confirmBtn = buttons.find((btn) => /E2E_UI_CLICK_CONFIRM/.test(btn.textContent || ''));
  return {
    ready: !!assistant && hasTitle && hasBody && !!confirmBtn && !sending,
    hasAssistant: !!assistant,
    hasTitle,
    hasBody,
    hasButton: !!confirmBtn,
    sending,
    onChat: /^\\/c-/.test(location.pathname),
    path: location.pathname,
    sample: text.slice(0, 800),
  };
})()"""

_CLICK_CONFIRM_BUTTON_JS = """(() => {
  const assistant = document.querySelector('[data-test-id="assistant-message"]');
  const root = assistant || document.querySelector('main');
  const buttons = Array.from(root?.querySelectorAll('button') || []);
  const confirmBtn = buttons.find((btn) => /E2E_UI_CLICK_CONFIRM/.test(btn.textContent || ''));
  if (!confirmBtn) {
    return { clicked: false, reason: 'missing-button' };
  }
  confirmBtn.click();
  return { clicked: true };
})()"""

_UI_ACTION_FEEDBACK_READY_JS = """(() => {
  const main = document.querySelector('main');
  const text = main?.innerText || '';
  const hasSubmittedBadge = /已提交|Submitted/.test(text);
  const hasUserActionLine = /操作[:：]\\s*(提交|Submit)|Action[:：]\\s*(Submit|提交)/.test(text);
  return {
    ready: hasSubmittedBadge && hasUserActionLine,
    hasSubmittedBadge,
    hasUserActionLine,
    sample: text.slice(0, 1200),
  };
})()"""


def _user_messages(chat_id: str, *, api_url: str) -> list[dict[str, object]]:
    messages = fetch_chat_messages(chat_id, api_url=api_url)
    return [msg for msg in messages if isinstance(msg, dict) and msg.get("role") == "user"]


def _last_user_message_has_ui_action(chat_id: str, *, api_url: str) -> bool:
    users = _user_messages(chat_id, api_url=api_url)
    if len(users) < 2:
        return False
    content = str(users[-1].get("content") or "")
    return "<ui_action_data>" in content and "ui_action" in content


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_render_ui_inline_button_click_sends_ui_action_message(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live render_ui interaction Chrome E2E — run via "
            "./myrm test -m chrome_e2e after ./myrm ready --chrome",
        )

    api_base = get_e2e_api_url()

    async def _wait_inline_button(
        chat: McpChatSession,
        chat_id: str,
        *,
        timeout_sec: float = 300.0,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            raw = await chat.evaluate(_INLINE_UI_READY_JS, await_promise=False, recv_timeout=30.0)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
            if last.get("onChat") is not True and chat_id:
                await chat.navigate_to_chat(chat_id, BASE_URL, timeout_sec=60.0)
            await asyncio.sleep(1.0)
        raise AssertionError(f"Inline A2UI confirm button did not render: {last}")

    async def _wait_ui_action_feedback(chat: McpChatSession, *, timeout_sec: float = 90.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            raw = await chat.evaluate(_UI_ACTION_FEEDBACK_READY_JS, await_promise=False, recv_timeout=30.0)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
            await asyncio.sleep(0.75)
        raise AssertionError(f"UI action feedback not visible after button click: {last}")

    async def _run_flow(chat: McpChatSession) -> str:
        await chat.dismiss_modals()
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL)

        enabled = await chat.evaluate(_ENABLE_RENDER_UI_JS, await_promise=False, recv_timeout=15.0)
        assert isinstance(enabled, dict)
        assert enabled.get("ok") is True, f"Failed to enable render_ui in chat session: {enabled}"

        send_result = await chat.send_message(E2E_PROMPT, E2E_PROMPT)
        submit_block = send_result.get("submit")
        assert isinstance(submit_block, dict) or isinstance(send_result.get("started"), dict), (
            f"Unexpected send_result shape: {send_result}"
        )
        chat_id_hint = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or ""
        ).strip()
        if not chat_id_hint:
            chat_id_hint = str((await chat.bridge_chat_id()) or "").strip() or None

        heartbeat_e2e_lease()
        started = await chat.wait_stream_started(E2E_PROMPT, timeout_sec=120.0, chat_id_hint=chat_id_hint)
        chat_id = chat_id_hint or str(started.get("chatId") or "").strip() or None
        if not chat_id:
            after_start = await chat.main_state(E2E_PROMPT, recv_timeout=30.0)
            chat_id = chat_id_from_path(str(after_start.get("path") or "")) or str(
                after_start.get("bridgeChatId") or ""
            ).strip() or None
        assert chat_id, f"Expected chat id after stream start: started={started}; send={send_result}"
        await chat.navigate_to_chat(chat_id, BASE_URL, timeout_sec=90.0)
        await chat.ensure_chat_surface(BASE_URL)

        await _wait_inline_button(chat, chat_id, timeout_sec=300.0)

        baseline_user_count = chat_user_message_count(chat_id, api_url=api_base)
        assert baseline_user_count >= 1, f"Expected initial user message for chat {chat_id}"

        clicked = await chat.evaluate(_CLICK_CONFIRM_BUTTON_JS, await_promise=False, recv_timeout=15.0)
        assert isinstance(clicked, dict)
        assert clicked.get("clicked") is True, f"Failed to click inline confirm button: {clicked}"

        feedback = await _wait_ui_action_feedback(chat, timeout_sec=90.0)

        deadline = time.monotonic() + 45.0
        ui_action_persisted = False
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            if chat_user_message_count(chat_id, api_url=api_base) >= baseline_user_count + 1:
                ui_action_persisted = _last_user_message_has_ui_action(chat_id, api_url=api_base)
                if ui_action_persisted:
                    break
            await asyncio.sleep(0.75)

        assert ui_action_persisted, (
            f"Expected persisted ui_action user message for chat {chat_id}; "
            f"feedback={feedback}; users={_user_messages(chat_id, api_url=api_base)!r}"
        )

        e2e_resource_ledger.register("chat", chat_id)
        return chat_id

    client = ChromeMcpClient(request_timeout_sec=120.0)
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
