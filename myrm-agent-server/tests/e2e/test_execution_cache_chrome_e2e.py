"""Chrome E2E: POOLED execution cache via real WebUI and MCP mux."""

from __future__ import annotations

import asyncio
import json
import os
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

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
API_URL = os.getenv("E2E_API_BASE", "http://127.0.0.1:8080").rstrip("/")
E2E_PROMPT = "只回复 OK"


def _provider_ready() -> bool:
    try:
        response = urllib.request.urlopen(  # noqa: S310 - fixed loopback endpoint
            f"{API_URL}/api/v1/config/readiness",
            timeout=5,
        )
        payload = json.loads(response.read())
    except Exception:
        return False
    provider = payload.get("provider")
    return isinstance(provider, dict) and bool(provider.get("is_ready"))


def _extract_chat_id(url: str) -> str | None:
    from urllib.parse import urlparse

    return chat_id_from_path(urlparse(url).path)


async def _resolve_chat_id(
    chat: McpChatSession,
    state: dict[str, object],
) -> str | None:
    chat_id = _extract_chat_id(str(state.get("url") or ""))
    if not chat_id:
        value = str(state.get("chatId") or "").strip()
        chat_id = value or None
    if chat_id:
        return chat_id
    href = await chat.evaluate(
        f"""(() => {{
          const base = {json.dumps(BASE_URL)};
          const links = Array.from(document.querySelectorAll('aside a[href]'))
            .map((anchor) => anchor.href)
            .filter((url) => url.startsWith(base) && !url.endsWith('/') && !url.includes('/settings'));
          return links[0] || location.href;
        }})()""",
        await_promise=False,
    )
    return _extract_chat_id(str(href) if href else "")


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_chrome_ui_same_chat_two_ok_messages(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not _provider_ready():
        pytest.skip(
            "Provider config not ready - configure a model at /settings/models"
        )

    log_offset = snapshot_backend_log_offset()

    async def run_chat_flow(chat: McpChatSession) -> None:
        await chat.bootstrap(BASE_URL, navigate=False, timeout_sec=120.0)
        await chat.click_new_chat()
        await chat.send_message(E2E_PROMPT, E2E_PROMPT)
        after_first = await chat.wait_turn_done(E2E_PROMPT)
        if str(after_first.get("path", "")).startswith("/settings"):
            pytest.fail(f"Send redirected to settings: {after_first}")

        chat_id = await _resolve_chat_id(chat, after_first)
        assert chat_id, f"Expected chat id after first turn: {after_first}"
        heartbeat_e2e_lease()
        e2e_resource_ledger.register("chat", chat_id)

        await chat.wait_input_empty(chat_id_hint=chat_id)
        heartbeat_e2e_lease()
        await chat.send_message(E2E_PROMPT, E2E_PROMPT, chat_id_hint=chat_id, base_url=BASE_URL)
        after_second = await chat.wait_turn_done(
            E2E_PROMPT,
            chat_id_hint=chat_id,
            min_user_msgs=2,
        )
        chat_id_second = await _resolve_chat_id(chat, after_second)
        assert chat_id_second == chat_id, (
            f"Second turn changed chat id: {chat_id} -> {chat_id_second}"
        )
        assert chat_user_message_count(chat_id) >= 2, (
            f"Expected two user messages in chat {chat_id}: "
            f"{after_first} -> {after_second}"
        )

    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    try:
        page = await asyncio.to_thread(
            client.new_page,
            BASE_URL,
            timeout_ms=120_000,
        )
        await run_chat_flow(McpChatSession(client, page))
    finally:
        await asyncio.to_thread(client.close)

    created, reused = count_execution_cache_in_log(since_offset=log_offset)
    assert created == 1, f"expected execution_cache_created x1 in backend log (got {created})"
    assert reused >= 1, f"expected execution_cache_reuse >=1 in backend log (got {reused})"
