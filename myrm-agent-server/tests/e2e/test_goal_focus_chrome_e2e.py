"""Chrome E2E: Goal mode via real WebUI and MCP mux.

Prerequisites:
  ./myrm ready --chrome
  WebUI default model configured (E2E Chrome profile DB)
"""

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

from cdp_chat_ui import chat_id_from_path, chat_user_message_count  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
API_URL = os.getenv("E2E_API_BASE", "http://127.0.0.1:8080").rstrip("/")
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


def _fetch_goal_status(chat_id: str) -> dict[str, object] | None:
    try:
        resp = urllib.request.urlopen(  # noqa: S310
            f"{API_URL}/api/v1/goals/{chat_id}/status",
            timeout=15,
        )
        payload = json.loads(resp.read())
    except Exception:
        return None
    goal = payload.get("goal")
    return goal if isinstance(goal, dict) else None


@pytest.mark.e2e
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_chrome_ui_goal_mode_stream(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not _provider_ready():
        pytest.fail(
            "Provider config not ready for live Goal E2E — run via ./myrm test -m e2e "
            "after ./myrm ready --chrome (preflight seeds model; "
            "API /api/v1/config/readiness provider.is_ready must be true)"
        )

    async def _resolve_chat_id(
        chat: McpChatSession,
        state: dict[str, object],
    ) -> str | None:
        explicit = str(state.get("chatId") or "").strip()
        if explicit:
            return explicit
        chat_id = chat_id_from_path(str(state.get("url") or ""))
        if chat_id:
            return chat_id
        path = await chat.evaluate("(() => location.pathname)()", await_promise=False)
        return chat_id_from_path(str(path) if path else "")

    async def _run_goal_flow(chat: McpChatSession) -> str:
        await chat.dismiss_modals()
        await chat.click_new_chat()

        goal_setup = await chat.enable_goal_mode(budget_tokens=50_000)
        assert goal_setup.get("ok") is True, f"Goal mode bridge failed: {goal_setup}"

        send_result = await chat.send_message(E2E_PROMPT, E2E_PROMPT)
        chat_id_hint = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or ""
        ).strip()
        if not chat_id_hint:
            chat_id_hint = str((await chat.bridge_chat_id()) or "").strip() or None
        heartbeat_e2e_lease()
        after_turn = await chat.wait_turn_done(
            E2E_PROMPT,
            timeout_sec=180,
            chat_id_hint=chat_id_hint,
        )
        if str(after_turn.get("path", "")).startswith("/settings"):
            pytest.fail(f"Send redirected to settings: {after_turn}")

        chat_id = await _resolve_chat_id(chat, after_turn)
        assert chat_id, f"Expected chat id after goal turn: {after_turn}"
        assert chat_user_message_count(chat_id) >= 1, (
            f"Expected API user message for chat {chat_id}: {after_turn}"
        )
        e2e_resource_ledger.register("chat", chat_id)
        return chat_id

    async def _run_goal_turn() -> str:
        client = ChromeMcpClient(request_timeout_sec=120.0)
        await asyncio.to_thread(client.start)
        isolated = f"e2e-goal-focus-{os.getpid()}"
        try:
            page: McpPage | None = None
            last_timeout: TimeoutError | None = None
            for attempt in range(2):
                try:
                    page = await asyncio.to_thread(
                        client.new_page,
                        BASE_URL,
                        timeout_ms=120_000,
                        isolated_context=isolated,
                    )
                    break
                except TimeoutError as exc:
                    last_timeout = exc
                    if attempt == 0:
                        await asyncio.sleep(2.0)
                        continue
                    raise
            if page is None:
                raise last_timeout or RuntimeError("new_page returned no page")
            chat = McpChatSession(client, page)
            await chat.bootstrap(BASE_URL, timeout_sec=120.0)
            return await _run_goal_flow(chat)
        finally:
            await asyncio.to_thread(client.close)

    chat_id = await _run_goal_turn()

    goal = _fetch_goal_status(chat_id)
    assert goal is not None, f"Goal status missing for chat {chat_id}"
    assert goal.get("objective"), f"Goal objective empty: {goal}"
    assert goal.get("status") in {"active", "budget_limited", "complete", "paused"}, (
        f"Unexpected goal status: {goal.get('status')}"
    )
