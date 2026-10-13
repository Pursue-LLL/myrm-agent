"""Chrome E2E: the post-run idle chain completes after a real WebUI chat turn.

Task flow: a user sends one message in the real WebUI (which keeps posting the activity
heartbeat that pauses background maintenance), the tab is closed, and the idle tasks the
turn queued must run to completion once the foreground pause lapses.

Prerequisites:
  ./myrm ready --chrome
  WebUI default model configured (E2E Chrome profile DB)
"""

from __future__ import annotations

import asyncio
import os
import sqlite3
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import get_e2e_api_url, wait_e2e_provider_ready  # noqa: E402
from chrome_mcp.client import ChromeMcpClient, McpPage  # noqa: E402
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.support.bash_compressor_e2e import _backend_runtime_data_dir
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
E2E_PROMPT = "只回复 OK"
SUPPORTED_IDLE_TASKS = frozenset({"cognitive_consolidation", "context_compaction", "cognitive_subsumption"})
# Foreground pause window (120s) + one deferred-retry interval (60s) + the idle delay, with headroom.
IDLE_CHAIN_TIMEOUT_S = 330.0


def _idle_rows(data_dir: Path, since: float, session_id: str) -> list[tuple[str, str]]:
    """(task_type, status) rows queued for this chat's session."""
    rows: list[tuple[str, str]] = []
    for db_path in data_dir.rglob("idle_tasks.db"):
        if db_path.stat().st_mtime < since:
            continue
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            rows.extend(conn.execute("SELECT task_type, status FROM idle_tasks WHERE session_id = ?", (session_id,)).fetchall())
    return rows


async def _bound_api_base(chat: McpChatSession) -> str:
    page_api = await chat.evaluate(
        "(() => (typeof window.__MYRM_E2E_API_BASE__ === 'string' ? window.__MYRM_E2E_API_BASE__.trim() : '') || null)()",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    return page_api.strip().rstrip("/") if isinstance(page_api, str) and page_api.strip() else get_e2e_api_url()


async def _send_one_turn(chat: McpChatSession) -> tuple[str, str]:
    """Returns (chat id, API base the page is bound to)."""
    api_base = await _bound_api_base(chat)
    await chat.dismiss_modals()
    await chat.click_new_chat()
    await chat.ensure_chat_surface(BASE_URL)
    send_result = await chat.send_message(E2E_PROMPT, E2E_PROMPT)
    chat_id_hint = str(send_result.get("started", {}).get("chatId") or send_result.get("submit", {}).get("chatId") or "").strip()
    if not chat_id_hint:
        chat_id_hint = str((await chat.bridge_chat_id()) or "").strip()
    heartbeat_once()
    after_turn = await chat.wait_turn_done(E2E_PROMPT, timeout_sec=240, chat_id_hint=chat_id_hint or None)
    if str(after_turn.get("path", "")).startswith("/settings"):
        pytest.fail(f"Send redirected to settings: {after_turn}")
    chat_id = await chat.resolve_chat_id(
        path=str(after_turn.get("path") or ""), hint=str(after_turn.get("chatId") or chat_id_hint) or None
    )
    assert chat_id, f"Expected chat id after the turn: {after_turn}"
    return chat_id, api_base


async def _run_turn_in_browser() -> tuple[str, str]:
    client = ChromeMcpClient(request_timeout_sec=120.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
        if page is None:
            raise RuntimeError("new_page returned no page")
        chat = McpChatSession(client, page)
        await chat.bootstrap(BASE_URL, timeout_sec=120.0)
        return await _send_one_turn(chat)
    finally:
        # Closing the tab stops the activity heartbeat, which is what lets the pause lapse.
        await asyncio.to_thread(client.close)


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_chrome_ui_turn_idle_chain_completes(e2e_resource_ledger: E2EResourceLedger) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail("Provider config not ready for the live idle-chain E2E; run via ./myrm test -m chrome_e2e")

    started = time.time()
    chat_id, api_base = await _run_turn_in_browser()
    e2e_resource_ledger.register("chat", chat_id)

    data_dir = _backend_runtime_data_dir(api_base)
    assert data_dir is not None, "the chrome E2E backend must be an isolated runtime to read its idle queue"

    rows: list[tuple[str, str]] = []
    timeline: list[str] = []
    turn_done = time.time()
    deadline = turn_done + IDLE_CHAIN_TIMEOUT_S
    while time.time() < deadline:
        current = _idle_rows(data_dir, since=started, session_id=f"chat_{chat_id}")
        if current != rows:
            timeline.append(f"+{time.time() - turn_done:.0f}s {sorted(current)}")
        rows = current
        if rows and all(status in ("completed", "error") for _, status in rows):
            break
        await asyncio.sleep(5)
        heartbeat_once()

    assert rows, "no idle task was queued after the WebUI turn"
    task_types = {task_type for task_type, _ in rows}
    assert task_types <= SUPPORTED_IDLE_TASKS, f"unexpected idle task types: {sorted(task_types - SUPPORTED_IDLE_TASKS)}"
    assert "cognitive_consolidation" in task_types, rows
    assert all(status == "completed" for _, status in rows), f"{rows}; idle queue timeline: {timeline}"
