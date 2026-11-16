"""Waits of the clarify Skip live E2E: the clarification card, the skip result, the Skip button.

[INPUT]
- cdp_chat.mcp_ui::McpChatSession (POS: Chat UI session backed by the Chrome DevTools MCP mux owner model)
- cdp_chat.support (POS: Stable import surface of the E2E chat helpers; it defines nothing itself)
- dev_gate.contract (POS: Dev Gate contract SSOT for Chrome MCP E2E orchestration: error tokens, parallel caps and timeout budgets)
- e2e_core.orchestrator (POS: single import path for E2E session orchestration)
- e2e_session_runtime.heartbeat (POS: unified E2E heartbeat SSOT: coordinator, wave lease and private runtime)
- tests.api.agent.utils::get_lite_model_selection (POS: Agent test helpers: lite model selection and provider-prefix handling)
- tests.e2e.clarify_skip.bridge_js (POS: page-side scripts of the clarify Skip E2E)
- tests.e2e.clarify_skip.chat_actions (POS: chat-page setup and stream hand-over steps)
- tests.e2e.clarify_skip.constants (POS: page origin, prompts and wait budget of the clarify Skip E2E)

[OUTPUT]
- ensure_clarify_after_send(chat, chat_id=, api_base=, prompt=): the clarification card is open — API pending first, DOM second;
  under E2E_SIGNOFF the API stream starts it when the page does not show it
- wait_api_skip_done / wait_ui_skip_done: continuation evidence after a skip, read from the chat messages or from the UI bridge
- wait_dom_skip_button: poll the page until its Skip button exists

[POS]
Polling layer of the clarify Skip E2E; every loop touches the wall-clock progress and the heartbeat.
"""

from __future__ import annotations

import asyncio
import time

from cdp_chat.mcp_ui import McpChatSession
from cdp_chat.support import (
    chat_has_pending_clarification,
    chat_messages_have_clarify_skip_done,
    start_clarify_turn_via_api,
)
from dev_gate.contract import EvaluateIntent, is_e2e_signoff_runtime
from e2e_core.orchestrator import remaining_wall_sec, touch_wall_progress
from e2e_session_runtime.heartbeat import heartbeat_once

from tests.api.agent.utils import get_lite_model_selection
from tests.e2e.clarify_skip.bridge_js import CLARIFY_FORM_READY_JS, UI_SKIP_DONE_JS
from tests.e2e.clarify_skip.chat_actions import release_ui_stream_for_api
from tests.e2e.clarify_skip.constants import skip_api_wait_sec


def _signoff_clarify_api_poll_budget(*, reserve_sec: float) -> float:
    """Reserve wall for skip resume after API clarify fallback (signoff MTB-600)."""
    return float(min(90.0, max(25.0, remaining_wall_sec() - reserve_sec)))


async def _wait_clarify_ready(
    chat: McpChatSession,
    *,
    chat_id: str,
    api_base: str,
    timeout_sec: float | None = None,
) -> dict[str, object]:
    """Wait for clarify ready via API pending (SSOT) or DOM Skip button (whichever first)."""
    wait_sec = skip_api_wait_sec() if timeout_sec is None else float(timeout_sec)
    wait_sec = min(wait_sec, max(10.0, remaining_wall_sec() - 45.0))
    deadline = time.monotonic() + wait_sec
    last_dom: dict[str, object] = {}
    normalized_chat_id = chat_id.strip()
    while time.monotonic() < deadline:
        touch_wall_progress()
        heartbeat_once()
        if normalized_chat_id:
            api_pending = await asyncio.to_thread(
                chat_has_pending_clarification,
                normalized_chat_id,
                api_url=api_base,
            )
            if api_pending:
                return {
                    "ready": True,
                    "source": "api",
                    "hasSkip": last_dom.get("hasSkip") is True,
                    "hasForm": True,
                }
        try:
            raw = await chat.evaluate(CLARIFY_FORM_READY_JS, intent=EvaluateIntent.BRIDGE_POLL)
        except TimeoutError:
            await asyncio.sleep(1.0)
            continue
        except RuntimeError as exc:
            message = str(exc).lower()
            if "transport unavailable" in message or "transport dead" in message or "transport closed" in message:
                raise AssertionError(f"Chrome MCP transport dead during clarify DOM wait: {exc}") from exc
            if "mux_reclaim_stall" in message:
                await asyncio.sleep(1.0)
                continue
            raise
        last_dom = raw if isinstance(raw, dict) else {"value": raw}
        if last_dom.get("ready") is True:
            return {**last_dom, "source": "dom"}
        if last_dom.get("hasForm") is True:
            return {
                "ready": True,
                "source": "dom-form",
                "hasSkip": last_dom.get("hasSkip") is True,
                "hasForm": True,
                "sample": str(last_dom.get("sample") or ""),
            }
        await asyncio.sleep(1.0)
    raise AssertionError(f"Clarification not ready within {wait_sec}s (chat_id={normalized_chat_id!r}, dom={last_dom})")


async def ensure_clarify_after_send(
    chat: McpChatSession,
    *,
    chat_id: str,
    api_base: str,
    prompt: str,
) -> dict[str, object]:
    """Wait for clarify after sendTurnSealed; signoff uses API stream fallback."""
    try:
        return await _wait_clarify_ready(
            chat,
            chat_id=chat_id,
            api_base=api_base,
        )
    except AssertionError as first_exc:
        if not is_e2e_signoff_runtime():
            raise
        if "transport dead" in str(first_exc).lower():
            raise
        print(
            "E2E_SIGNOFF_CLARIFY: chrome wait failed; API stream fallback",
            flush=True,
        )
        await release_ui_stream_for_api(chat)
        poll_budget = _signoff_clarify_api_poll_budget(reserve_sec=200.0)
        api_result = await asyncio.to_thread(
            start_clarify_turn_via_api,
            chat_id,
            query=prompt,
            model_selection=get_lite_model_selection(),
            api_url=api_base,
            timeout_sec=poll_budget,
        )
        if api_result.get("has_clarification") is not True:
            raise AssertionError(f"signoff API clarify fallback failed: {api_result}; prior={first_exc}") from first_exc
        await asyncio.sleep(2.0)
        await release_ui_stream_for_api(chat)
        # private API stream is SSOT once clarification_required is seen.
        # Second chrome _wait_clarify_ready caused signoff retry + model-not-ready.
        print(
            "E2E_SIGNOFF_CLARIFY: API clarify confirmed; proceed API skip path",
            flush=True,
        )
        return {
            "ready": True,
            "source": "api-fallback",
            "api_stream_fallback": True,
            "hasForm": False,
            "hasSkip": False,
        }


async def wait_api_skip_done(
    *,
    chat_id: str,
    api_base: str,
    timeout_sec: float | None = None,
) -> dict[str, object]:
    wait_sec = skip_api_wait_sec() if timeout_sec is None else float(timeout_sec)
    wait_sec = min(wait_sec, max(10.0, remaining_wall_sec() - 45.0))
    deadline = time.monotonic() + wait_sec
    while time.monotonic() < deadline:
        touch_wall_progress()
        heartbeat_once()
        api_ready = await asyncio.to_thread(
            chat_messages_have_clarify_skip_done,
            chat_id,
            api_url=api_base,
        )
        if api_ready:
            return {
                "ready": True,
                "source": "api",
                "doneSkipped": True,
                "answered": True,
            }
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"API did not show clarify skip completion for chat {chat_id} within {wait_sec}s",
    )


async def wait_ui_skip_done(
    chat: McpChatSession,
    *,
    timeout_sec: float | None = None,
) -> dict[str, object]:
    wait_sec = skip_api_wait_sec() if timeout_sec is None else float(timeout_sec)
    wait_sec = min(wait_sec, max(10.0, remaining_wall_sec() - 45.0))
    deadline = time.monotonic() + wait_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        touch_wall_progress()
        heartbeat_once()
        raw = await chat.evaluate(UI_SKIP_DONE_JS, intent=EvaluateIntent.BRIDGE_POLL)
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ready") is True and last.get("isStreaming") is not True:
            return {
                "ready": True,
                "source": "ui_bridge",
                "doneSkipped": last.get("doneSkipped") is True,
                "answered": True,
            }
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"UI bridge skip did not complete within {wait_sec}s (last={last})",
    )


async def wait_dom_skip_button(
    chat: McpChatSession,
    *,
    timeout_sec: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        touch_wall_progress()
        heartbeat_once()
        try:
            raw = await chat.evaluate(CLARIFY_FORM_READY_JS, intent=EvaluateIntent.BRIDGE_POLL)
        except (TimeoutError, RuntimeError):
            await asyncio.sleep(1.0)
            continue
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("hasSkip") is True:
            return last
        await asyncio.sleep(1.0)
    return last
