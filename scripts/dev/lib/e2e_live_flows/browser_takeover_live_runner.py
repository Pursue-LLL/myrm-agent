"""Browser takeover LIVE runner — client lifecycle SSOT (R98)."""

from __future__ import annotations

import asyncio
import os

from chrome_mcp_client import ChromeMcpClient, McpPage
from e2e_live_flows._flow_base import FlowLogger
from mcp_chat_ui import McpChatSession
from tests.support.e2e_runtime_guard import E2EResourceLedger

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")


async def run_browser_takeover_live_session(
    *,
    ledger: E2EResourceLedger,
    run_flow,
) -> str:
    """Start MCP client, bootstrap chat shell, delegate flow body, always close client."""
    log = FlowLogger()
    client = ChromeMcpClient(request_timeout_sec=180.0)
    log.emit("client.start()")
    await asyncio.to_thread(client.start)
    log.emit("client started — new_page()")
    try:
        page: McpPage | None = None
        try:
            page = await asyncio.to_thread(
                client.new_page, BASE_URL, timeout_ms=120_000
            )
        except TimeoutError:
            log.emit("new_page timeout — retry")
            await asyncio.sleep(2.0)
            page = await asyncio.to_thread(
                client.new_page, BASE_URL, timeout_ms=120_000
            )
        if page is None:
            raise RuntimeError("new_page returned no page")
        log.emit(f"page opened id={page.page_id}")
        chat = McpChatSession(client, page)
        log.emit("bootstrap()")
        await chat.bootstrap(BASE_URL, timeout_sec=120.0)
        log.emit("bootstrap done — entering run_flow()")
        chat_id = await run_flow(chat, log=log, ledger=ledger)
        if not chat_id:
            raise RuntimeError("run_flow returned empty chat_id")
        return chat_id
    finally:
        await asyncio.to_thread(client.close)
