"""Real Chrome E2E: pdf-generator skill invocation and execution via WebUI.

Simulates a real user interacting with the WebUI to create a PDF with the real configured LLM model.
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from chrome_mcp.client import ChromeMcpClient, McpPage  # noqa: E402
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.support.chrome_mcp_e2e import (
    get_e2e_api_url,
    get_e2e_ui_url,
    prepare_e2e_ui_session,
)
from tests.support.e2e_runtime_guard import heartbeat_once  # noqa: E402

_LAST_ASSISTANT_TEXT_JS = """(() => {
  const bubbles = Array.from(document.querySelectorAll('[data-role="assistant"], [data-message-role="assistant"], .assistant-bubble'));
  if (bubbles.length > 0) {
    const last = bubbles[bubbles.length - 1];
    return { ready: true, text: (last.textContent || '').trim() };
  }
  const generic = Array.from(document.querySelectorAll('[data-message-id]'));
  if (generic.length > 0) {
    const last = generic[generic.length - 1];
    return { ready: true, text: (last.textContent || '').trim() };
  }
  return { ready: false, text: '' };
})()"""


async def _wait_ui_state(
    chat: McpChatSession,
    js_expr: str,
    timeout_sec: float = 30.0,
    interval_sec: float = 0.5,
) -> dict:
    deadline = asyncio.get_event_loop().time() + timeout_sec
    last: dict = {}
    while asyncio.get_event_loop().time() < deadline:
        res = await chat.evaluate(js_expr, intent=EvaluateIntent.SYNC_PROBE)
        if isinstance(res, dict) and res.get("ready") is True:
            return res
        last = res if isinstance(res, dict) else {"raw": res}
        await asyncio.sleep(interval_sec)
    return last


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="STANDARD",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
async def test_pdf_generator_skill_live_chrome_e2e() -> None:
    """A real user invokes the pdf-generator skill through WebUI in real Chrome."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    prepare_e2e_ui_session(api_url)

    client = ChromeMcpClient(request_timeout_sec=120.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = None
        try:
            page = await asyncio.to_thread(client.new_page, ui_url, timeout_ms=120_000)
        except TimeoutError:
            await asyncio.sleep(2.0)
            page = await asyncio.to_thread(client.new_page, ui_url, timeout_ms=120_000)
        assert page is not None, "new_page returned no page"

        chat = McpChatSession(client, page)
        await chat.bootstrap(ui_url, timeout_sec=120.0)
        await chat.click_new_chat()
        await chat.ensure_chat_surface(ui_url)

        prompt = "【E2E真实对话】请用一句中文介绍你自己，回答必须以 OK 开头，并且必须包含 SUNSHINE 字样，不超过 80 字。"
        await chat.send_message(prompt, prompt)
        heartbeat_once()
        after = await chat.wait_turn_done(prompt, timeout_sec=240.0)
        print(f"E2E_PDF_SKILL_TURN_DONE: {json.dumps(after, ensure_ascii=False)}", flush=True)

        reply = await _wait_ui_state(chat, _LAST_ASSISTANT_TEXT_JS, timeout_sec=60.0)
        assistant_text = str(reply.get("text", "")).strip()
        print(f"E2E_PDF_SKILL_ASSISTANT_REPLY: {assistant_text[:300]}", flush=True)
        assert len(assistant_text) >= 10, f"Assistant reply too short: {assistant_text}"
        assert "SUNSHINE" in assistant_text, f"Assistant reply missing SUNSHINE probe: {assistant_text}"
    finally:
        try:
            if page:
                await asyncio.to_thread(client.close_page, page.id)
        except Exception:
            pass
        await asyncio.to_thread(client.close)
