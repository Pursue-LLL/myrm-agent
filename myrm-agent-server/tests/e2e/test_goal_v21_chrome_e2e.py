"""Chrome E2E: Goal v2.1 UI flows — pause+note, draft composer bind, bg-finish refresh.

Prerequisites:
  ./myrm ready --chrome
  WebUI default model configured (E2E Chrome profile DB)
"""

from __future__ import annotations

import asyncio
import os
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    ensure_e2e_goal_active,
    fetch_e2e_goal_status,
    get_e2e_api_url,
    post_goal_status_action,
    wait_e2e_goal_status,
    wait_e2e_provider_ready,
)
from cdp_chat_ui import chat_id_from_path, chat_user_message_count  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
E2E_PROMPT = (
    "【E2E v2.1 持续监控】本轮只回复 OK。"
    "禁止调用 complete_goal_tool，禁止标记 goal 完成。"
)
DRAFT_OBJECTIVE = "Add health check endpoint returning 200 JSON"
PAUSE_NOTE = "E2E pause note for v2.1"


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_chrome_ui_goal_v21_pause_draft_bg_refresh(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready — run via ./myrm test -m chrome_e2e after ./myrm ready --chrome"
        )

    async def _resolve_bound_api_base(chat: McpChatSession) -> str:
        page_api = await chat.evaluate(
            """(() => {
              const base = typeof window.__MYRM_E2E_API_BASE__ === 'string'
                ? window.__MYRM_E2E_API_BASE__.trim()
                : '';
              return base || null;
            })()""",
            await_promise=False,
        )
        if isinstance(page_api, str) and page_api.strip():
            return page_api.strip().rstrip("/")
        return get_e2e_api_url()

    async def _require_active_goal_ui(
        chat: McpChatSession,
        chat_id: str,
        api_base: str,
    ) -> None:
        normalized = ensure_e2e_goal_active(chat_id, api_url=api_base)
        assert normalized.get("ok") is True, (
            f"Goal must be ACTIVE before B/D UI flows (terminal goals cannot resume): {normalized}"
        )
        loaded = await chat.load_active_goal_from_api()
        assert loaded.get("ok") is True and loaded.get("status") == "active", loaded
        pause_probe = await chat.probe_goal_pause_trigger()
        assert pause_probe.get("hasPauseTrigger") is True, pause_probe

    async def _run_session(chat: McpChatSession) -> tuple[str, str]:
        api_base = await _resolve_bound_api_base(chat)
        await chat.dismiss_modals()
        path_probe = await chat.evaluate("(() => location.pathname)()", await_promise=False)
        if isinstance(path_probe, str) and (
            path_probe.startswith("/settings") or path_probe.startswith("/login")
        ):
            await chat.cdp("Page.navigate", {"url": f"{BASE_URL}/"})
            await asyncio.sleep(3.0)
            await chat.bootstrap(BASE_URL, timeout_sec=120.0)
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL)

        goal_setup = await chat.enable_goal_mode(budget_tokens=50_000, convergence_window=None)
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
        chat_id = chat_id_from_path(str(after_turn.get("path") or "")) or chat_id_hint
        assert chat_id, f"Expected chat id after goal turn: {after_turn}"
        assert chat_user_message_count(chat_id, api_url=api_base) >= 1
        e2e_resource_ledger.register("chat", chat_id)

        goal = wait_e2e_goal_status(chat_id, timeout_sec=120.0, api_url=api_base)
        assert goal is not None, f"Goal not persisted for chat {chat_id}"

        await _require_active_goal_ui(chat, chat_id, api_base)

        # B: Pause + optional note via real UI dialog (unconditional)
        pause_result = await chat.pause_goal_via_ui(PAUSE_NOTE)
        assert pause_result.get("ok") is True, pause_result
        snap = pause_result.get("snapshot")
        assert isinstance(snap, dict), pause_result
        assert snap.get("status") == "paused", snap
        assert snap.get("reason") == PAUSE_NOTE, snap
        api_goal = fetch_e2e_goal_status(chat_id, api_url=api_base)
        assert api_goal is not None and api_goal.get("status") == "paused", api_goal

        resume_payload = post_goal_status_action(chat_id, "resume", api_url=api_base)
        assert resume_payload.get("new_status") == "active", resume_payload
        await _require_active_goal_ui(chat, chat_id, api_base)

        # C: Draft binds composer objective (store gate + draft API)
        await chat.fill_input(DRAFT_OBJECTIVE)
        draft_state = await chat.get_goal_draft_state()
        assert draft_state.get("composerObjective") == DRAFT_OBJECTIVE, draft_state
        assert draft_state.get("draftButtonDisabled") is False, draft_state

        draft_result = await chat.run_goal_draft_from_composer()
        assert draft_result.get("ok") is True, draft_result
        assert int(draft_result.get("acceptanceCount") or 0) >= 1 or int(
            draft_result.get("constraintsCount") or 0
        ) >= 1, draft_result

        await _require_active_goal_ui(chat, chat_id, api_base)

        # D: background_job_finish SSE → refreshActiveGoal (stale WAIT → ACTIVE, unconditional)
        wait_payload = post_goal_status_action(
            chat_id,
            "wait",
            api_url=api_base,
            wait_reason="E2E bg bash simulation",
        )
        assert wait_payload.get("new_status") == "wait", wait_payload
        loaded_wait = await chat.load_active_goal_from_api()
        assert loaded_wait.get("status") == "wait", loaded_wait

        unwait_payload = post_goal_status_action(chat_id, "unwait", api_url=api_base)
        assert unwait_payload.get("new_status") == "active", unwait_payload
        stale = await chat.get_active_goal_snapshot()
        assert isinstance(stale, dict) and stale.get("status") == "wait", stale
        api_before_dispatch = fetch_e2e_goal_status(chat_id, api_url=api_base)
        assert api_before_dispatch is not None and api_before_dispatch.get("status") == "active", (
            f"API must be ACTIVE while UI stays stale WAIT before bg-finish refresh: {api_before_dispatch}"
        )

        dispatch = await chat.dispatch_background_job_finish(chat_id)
        assert dispatch.get("ok") is True, dispatch
        assert dispatch.get("status") == "active", dispatch

        refreshed = await chat.get_active_goal_snapshot()
        assert isinstance(refreshed, dict) and refreshed.get("status") == "active", refreshed
        api_after = fetch_e2e_goal_status(chat_id, api_url=api_base)
        assert api_after is not None and api_after.get("status") == "active", api_after

        return chat_id, api_base

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
        chat_id, api_base = await _run_session(chat)
        assert chat_id and api_base
    finally:
        await asyncio.to_thread(client.close)
