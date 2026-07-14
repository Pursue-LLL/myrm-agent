"""Chrome E2E: POOLED execution cache via real WebUI and MCP mux.

Prerequisites:
  ./myrm ready --chrome
  WebUI default model configured (E2E Chrome profile DB)
"""

from __future__ import annotations

import asyncio
import json
import sys
import urllib.request
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_ui import (  # noqa: E402
    chat_id_from_path,
    chat_user_message_count,
    count_execution_cache_in_log,
    snapshot_backend_log_offset,
)
from chrome_mcp_client import ChromeMcpClient  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger

BASE_URL = "http://127.0.0.1:3000"
API_URL = "http://127.0.0.1:8080"
E2E_PROMPT = "只回复 OK"


def _provider_ready() -> bool:
    try:
        resp = urllib.request.urlopen(  # noqa: S310 - fixed loopback E2E endpoint
            f"{API_URL}/api/v1/config/readiness",
            timeout=5,
        )
        payload = json.loads(resp.read())
    except Exception:
        return False
    provider = payload.get("provider")
    return isinstance(provider, dict) and bool(provider.get("is_ready"))


def _extract_chat_id(url: str) -> str | None:
    from urllib.parse import urlparse

    return chat_id_from_path(urlparse(url).path)


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(300)
@pytest.mark.asyncio
async def test_chrome_ui_same_chat_two_ok_messages(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not _provider_ready():
        pytest.skip(
            "Provider config not ready — configure model at /settings/models "
            "(API /api/v1/config/readiness provider.is_ready must be true)"
        )

    log_offset = snapshot_backend_log_offset()

    async def _run_chat_flow(chat: McpChatSession) -> None:
        await chat.bootstrap(BASE_URL, navigate=False, timeout_sec=45.0)
        await chat.click_new_chat()
        await chat.send_message(E2E_PROMPT, E2E_PROMPT)
        after_first = await chat.wait_turn_done(E2E_PROMPT)
        if str(after_first.get("path", "")).startswith("/settings"):
            pytest.fail(f"Send redirected to settings: {after_first}")

        chat_id = _extract_chat_id(str(after_first.get("url") or "")) or str(after_first.get("chatId") or "").strip() or None
        if not chat_id:
            href = await chat.evaluate(
                """(() => {
                  const links = Array.from(document.querySelectorAll('aside a[href]'))
                    .map((a) => a.href)
                    .filter((h) => /:3000\\//.test(h) && !h.endsWith('/') && !h.includes('/settings'));
                  return links[0] || location.href;
                })()""",
                await_promise=False,
            )
            chat_id = _extract_chat_id(str(href) if href else "")
        assert chat_id, f"Expected chat id after first turn: {after_first}"
        e2e_resource_ledger.register("chat", chat_id)

        await chat.wait_input_empty()
        await chat.send_message(E2E_PROMPT, E2E_PROMPT)
        after_second = await chat.wait_turn_done(
            E2E_PROMPT,
            chat_id_hint=chat_id,
            min_user_msgs=2,
        )
        chat_id_second = _extract_chat_id(str(after_second.get("url") or "")) or str(after_second.get("chatId") or "").strip() or None
        if not chat_id_second:
            href = await chat.evaluate(
                """(() => {
                  const links = Array.from(document.querySelectorAll('aside a[href]'))
                    .map((a) => a.href)
                    .filter((h) => /:3000\\//.test(h) && !h.endsWith('/') && !h.includes('/settings'));
                  return links[0] || location.href;
                })()""",
                await_promise=False,
            )
            chat_id_second = _extract_chat_id(str(href) if href else "")
        assert chat_id_second == chat_id, f"Second turn changed chat id: {chat_id} -> {chat_id_second}"
        assert chat_user_message_count(chat_id) >= 2, (
            f"Expected two user messages in chat {chat_id}: {after_first} -> {after_second}"
        )

    async def _run_turns() -> None:
        client = ChromeMcpClient(request_timeout_sec=15.0)
        await asyncio.to_thread(client.start)
        try:
            page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=15_000)
            chat = McpChatSession(client, page)
            await _run_chat_flow(chat)
        except BaseException as exc:
            await asyncio.to_thread(
                client.__exit__, type(exc), exc, exc.__traceback__
            )
            raise
        else:
            await asyncio.to_thread(client.close)

    await _run_turns()

    created, reused = count_execution_cache_in_log(since_offset=log_offset)
    assert created == 1, f"expected execution_cache_created×1 in backend log (got {created})"
    assert reused >= 1, f"expected execution_cache_reuse≥1 in backend log (got {reused})"
