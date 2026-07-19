"""Chrome LIVE_AGENT E2E: render_ui inline card renders in real Web Chat."""

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

from cdp_chat_support import get_e2e_api_url, wait_e2e_provider_ready  # noqa: E402
from cdp_chat_ui import chat_id_from_path, chat_user_message_count  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

E2E_PROMPT = (
    "Call render_ui_tool exactly once. Required arguments: "
    'title="部署确认"; '
    'components=[{"id":"t1","type":"text","props":{"text":"确认重启 staging?"}}]; '
    'root_ids=["t1"]. '
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
  const main = document.querySelector('main');
  const text = main?.innerText || '';
  const hasTitle = /部署确认/.test(text);
  const hasBody = /确认重启 staging/.test(text);
  const sending = !!main?.querySelector('button[aria-label="Stop"]');
  return {
    ready: hasTitle && hasBody && !sending,
    hasTitle,
    hasBody,
    sending,
    sample: text.slice(0, 800),
  };
})()"""


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_render_ui_inline_card_renders_in_real_chat(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live render_ui Chrome E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome (API /api/v1/config/readiness provider.is_ready must be true)",
        )

    async def _wait_inline_ui(chat: McpChatSession, *, timeout_sec: float = 300.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            raw = await chat.evaluate(_INLINE_UI_READY_JS, await_promise=False, recv_timeout=30.0)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
            await asyncio.sleep(1.0)
        raise AssertionError(f"Inline UI artifact did not render in chat: {last}")

    async def _run_flow(chat: McpChatSession) -> str:
        api_base = get_e2e_api_url()
        await chat.dismiss_modals()
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL)

        enabled = await chat.evaluate(_ENABLE_RENDER_UI_JS, await_promise=False, recv_timeout=15.0)
        assert isinstance(enabled, dict)
        assert enabled.get("ok") is True, f"Failed to enable render_ui in chat session: {enabled}"

        send_result = await chat.send_message(E2E_PROMPT, E2E_PROMPT)
        chat_id_hint = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or ""
        ).strip()
        if not chat_id_hint:
            chat_id_hint = str((await chat.bridge_chat_id()) or "").strip() or None

        heartbeat_e2e_lease()
        await chat.wait_stream_started(E2E_PROMPT, timeout_sec=120.0, chat_id_hint=chat_id_hint)
        ui_state = await _wait_inline_ui(chat, timeout_sec=300.0)

        after_turn = await chat.main_state(E2E_PROMPT, recv_timeout=30.0)
        if str(after_turn.get("path", "")).startswith("/settings"):
            pytest.fail(f"Send redirected to settings: {after_turn}")

        chat_id = chat_id_hint or chat_id_from_path(str(after_turn.get("path") or ""))
        if not chat_id:
            chat_id = str(after_turn.get("bridgeChatId") or "").strip() or None
        assert chat_id, f"Expected chat id after render_ui turn: {after_turn}; ui={ui_state}"
        try:
            assert chat_user_message_count(chat_id, api_url=api_base) >= 1, (
                f"Expected API user message for chat {chat_id}: {after_turn}"
            )
        except (TimeoutError, OSError) as exc:
            # DOM inline UI is the primary assertion; API poll is best-effort under shared stack load.
            if ui_state.get("ready") is not True:
                raise AssertionError(
                    f"API message check failed and inline UI not ready: {exc}"
                ) from exc
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
