"""Chrome E2E: POOLED execution cache via real WebUI and MCP mux."""

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
from cdp_chat.support import get_e2e_api_url, get_e2e_ui_url  # noqa: E402
from cdp_chat.ui import (  # noqa: E402
    chat_id_from_path,
    chat_user_message_count,
    count_execution_cache_in_log,
    count_turn_prewarm_in_log,
    snapshot_backend_log_offset,
    wait_e2e_provider_ready,
)
from chrome_mcp.client import ChromeMcpClient, McpPage  # noqa: E402
from dev_gate.contract import EvaluateIntent  # noqa: E402
from e2e_core.llm_receipt import emit_llm_receipt  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once

E2E_PROMPT = "只回复 OK"
TURN_WAIT_SEC = 300.0


def _base_url() -> str:
    return get_e2e_ui_url().rstrip("/")


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
          const base = {json.dumps(_base_url())};
          const links = Array.from(document.querySelectorAll('aside a[href]'))
            .map((anchor) => anchor.href)
            .filter((url) => url.startsWith(base) && !url.endsWith('/') && !url.includes('/settings'));
          return links[0] || location.href;
        }})()""",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    return _extract_chat_id(str(href) if href else "")


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_chrome_ui_same_chat_two_ok_messages(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome (API /api/v1/config/readiness provider.is_ready must be true)"
        )

    async def run_chat_flow(chat: McpChatSession) -> tuple[int, str]:
        ui_base = _base_url()
        await chat.bootstrap(ui_base, navigate=False, timeout_sec=180.0)
        await chat.click_new_chat()
        log_offset = snapshot_backend_log_offset(api_url=get_e2e_api_url())
        first_send = await chat.send_message(E2E_PROMPT, E2E_PROMPT)
        first_chat_id = str(
            first_send.get("started", {}).get("chatId")
            or first_send.get("submit", {}).get("chatId")
            or ""
        ).strip() or None
        after_first = await chat.wait_turn_done(
            E2E_PROMPT,
            chat_id_hint=first_chat_id,
            timeout_sec=TURN_WAIT_SEC,
        )
        if str(after_first.get("path", "")).startswith("/settings"):
            pytest.fail(f"Send redirected to settings: {after_first}")

        chat_id = await _resolve_chat_id(chat, after_first)
        assert chat_id, f"Expected chat id after first turn: {after_first}"
        heartbeat_once()
        e2e_resource_ledger.register("chat", chat_id)

        await chat.wait_input_empty(chat_id_hint=chat_id)
        heartbeat_once()
        await chat.send_message(
            E2E_PROMPT, E2E_PROMPT, chat_id_hint=chat_id, base_url=_base_url()
        )
        after_second = await chat.wait_turn_done(
            E2E_PROMPT,
            chat_id_hint=chat_id,
            min_user_msgs=2,
            timeout_sec=TURN_WAIT_SEC,
        )
        chat_id_second = await _resolve_chat_id(chat, after_second)
        assert (
            chat_id_second == chat_id
        ), f"Second turn changed chat id: {chat_id} -> {chat_id_second}"
        assert chat_user_message_count(chat_id) >= 2, (
            f"Expected two user messages in chat {chat_id}: "
            f"{after_first} -> {after_second}"
        )
        return log_offset, chat_id

    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = None
        try:
            page = await asyncio.to_thread(
                client.new_page,
                _base_url(),
                timeout_ms=120_000,
            )
        except TimeoutError:
            await asyncio.sleep(2.0)
            page = await asyncio.to_thread(
                client.new_page,
                _base_url(),
                timeout_ms=120_000,
            )
        if page is None:
            raise RuntimeError("new_page returned no page")
        log_offset, chat_id = await run_chat_flow(McpChatSession(client, page))
    finally:
        await asyncio.to_thread(client.close)

    receipt = emit_llm_receipt(chat_id=chat_id)
    assert receipt.get("model_id"), f"LLMReceipt missing model_id: {receipt}"
    assert receipt.get("assistant_snippet"), f"LLMReceipt missing assistant_snippet: {receipt}"
    assert receipt.get("api_port"), f"LLMReceipt missing api_port: {receipt}"

    prewarm_requests = count_turn_prewarm_in_log(
        since_offset=log_offset, api_url=get_e2e_api_url()
    )
    assert (
        prewarm_requests >= 1
    ), f"expected Turn prewarm requested >=1 in backend log (got {prewarm_requests})"

    created, reused = count_execution_cache_in_log(
        since_offset=log_offset, api_url=get_e2e_api_url()
    )
    assert (
        created >= 1
    ), f"expected execution_cache_created >=1 in backend log (got {created})"
    assert (
        reused >= 1
    ), f"expected execution_cache_reuse >=1 in backend log (got {reused})"
