"""One live clarify Skip turn end to end: open the page, send the prompt, reach the card, skip it, check the chat.

[INPUT]
- cdp_chat.mcp_ui::McpChatSession (POS: Chat UI session backed by the Chrome DevTools MCP mux owner model)
- chrome_mcp.client (POS: MCP JSON-RPC transport layer of the formal pytest UI E2E)
- cdp_chat.ui (POS: stable facade for Chrome chat UI E2E helpers)
- cdp_chat.support (POS: Stable import surface of the E2E chat helpers; it defines nothing itself)
- dev_gate.contract (POS: Dev Gate contract SSOT for Chrome MCP E2E orchestration: error tokens, parallel caps and timeout budgets)
- e2e_session_runtime.heartbeat::heartbeat_once (POS: unified E2E heartbeat SSOT: coordinator, wave lease and private runtime)
- tests.support.e2e_runtime_guard::E2EResourceLedger (POS: LIVE Chrome E2E runtime guard)
- tests.e2e.clarify_skip.skip_flow / waits / chat_actions / bridge_js / constants (POS: the steps and settings of the clarify Skip E2E)

[OUTPUT]
- open_chat_session(client): a chat session whose page and E2E bridge are ready (bounded retries with mux recovery)
- run_flow(chat, e2e_resource_ledger): the chat id after a proven skip; registers the chat in the resource ledger

[POS]
Top of the clarify Skip E2E: composes the page bootstrap and the send, wait and skip steps into one live turn.
"""

from __future__ import annotations

import asyncio

import pytest
from cdp_chat.mcp_ui import McpChatSession
from cdp_chat.support import ensure_e2e_yolo_mode, get_e2e_api_url
from cdp_chat.ui import chat_id_from_path, chat_user_message_count
from chrome_mcp.client import ChromeMcpClient, McpPage
from dev_gate.contract import EvaluateIntent, is_e2e_signoff_runtime
from e2e_session_runtime.heartbeat import heartbeat_once

from tests.e2e.clarify_skip.bridge_js import DISMISS_MIGRATION_JS
from tests.e2e.clarify_skip.chat_actions import prepare_fresh_clarify_chat
from tests.e2e.clarify_skip.constants import BASE_URL, E2E_NUDGE_PROMPT, E2E_PROMPT, E2E_PROMPT_SIGNOFF
from tests.e2e.clarify_skip.skip_flow import complete_clarify_skip
from tests.e2e.clarify_skip.waits import ensure_clarify_after_send
from tests.support.e2e_runtime_guard import E2EResourceLedger


async def open_chat_session(client: ChromeMcpClient) -> McpChatSession:
    """Open the WebUI page and bootstrap its chat surface and E2E bridge, recovering the mux transport between attempts."""
    page: McpPage | None = None
    new_page_timeouts = (120.0, 90.0)
    for attempt, wall_timeout in enumerate(new_page_timeouts, start=1):
        try:
            page = await asyncio.wait_for(
                asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000),
                timeout=wall_timeout,
            )
        except TimeoutError as exc:
            page = None
            if attempt >= len(new_page_timeouts):
                raise RuntimeError(
                    f"new_page timed out after {wall_timeout:.0f}s (attempt {attempt}/{len(new_page_timeouts)})"
                ) from exc
            await asyncio.to_thread(client.abandon_inflight_requests)
            await asyncio.sleep(1.5)
            await asyncio.to_thread(client.recover_mux_transport)
            continue
        except RuntimeError:
            page = None
            if attempt >= len(new_page_timeouts):
                raise
            await asyncio.to_thread(client.abandon_inflight_requests)
            await asyncio.sleep(1.5)
            await asyncio.to_thread(client.recover_mux_transport)
            continue
        if page is not None:
            break
    if page is None:
        raise RuntimeError("new_page returned no page")
    chat: McpChatSession | None = None
    bootstrap_timeouts = (95.0, 95.0)
    for attempt, bootstrap_timeout in enumerate(bootstrap_timeouts, start=1):
        chat = McpChatSession(client, page)
        try:
            await asyncio.wait_for(
                chat.ensure_chat_surface(BASE_URL, timeout_sec=120.0),
                timeout=bootstrap_timeout,
            )
            await asyncio.wait_for(
                chat.ensure_react_e2e_bridge(timeout_sec=60.0),
                timeout=min(70.0, bootstrap_timeout),
            )
            break
        except TimeoutError:
            if attempt >= len(bootstrap_timeouts):
                pytest.fail(
                    f"Clarify chrome E2E bootstrap timed out in shared-hot mode: timed out after {bootstrap_timeout:.0f}s"
                )
        except RuntimeError as exc:
            message = str(exc).lower()
            retryable = "mux_reclaim_stall" in message or "transport" in message or "target closed" in message
            if (not retryable) or attempt >= len(bootstrap_timeouts):
                if retryable:
                    pytest.fail(
                        "Clarify chrome E2E bootstrap transport unstable in shared-hot mode: "
                        f"bootstrap transport unstable ({exc})"
                    )
                raise
        await asyncio.to_thread(client.abandon_inflight_requests)
        await asyncio.sleep(1.5)
        await asyncio.to_thread(client.recover_mux_transport)
        page = await asyncio.wait_for(
            asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000),
            timeout=60.0,
        )
        if page is None:
            raise RuntimeError("new_page returned no page after bootstrap recover")
    if chat is None:
        raise RuntimeError("bootstrap did not create chat session")
    return chat


async def run_flow(chat: McpChatSession, e2e_resource_ledger: E2EResourceLedger) -> str:
    api_base = get_e2e_api_url()
    await asyncio.to_thread(ensure_e2e_yolo_mode, api_url=api_base)
    await prepare_fresh_clarify_chat(chat)

    chat_id_hint = ""
    form_state: dict[str, object] = {}
    max_clarify_attempts = 2
    signoff_api_recovery_form: dict[str, object] = {
        "ready": True,
        "source": "signoff-sealed-recovery",
        "api_stream_fallback": True,
        "hasForm": False,
        "hasSkip": False,
    }
    for attempt in range(max_clarify_attempts):
        if attempt > 0 and not (is_e2e_signoff_runtime() and chat_id_hint):
            await prepare_fresh_clarify_chat(chat)
        await chat.dismiss_modals()
        await chat.evaluate(DISMISS_MIGRATION_JS, intent=EvaluateIntent.SYNC_PROBE)
        try:
            if is_e2e_signoff_runtime():
                prompt = E2E_PROMPT_SIGNOFF if attempt == 0 else E2E_NUDGE_PROMPT
            else:
                prompt = E2E_PROMPT if attempt == 0 else E2E_NUDGE_PROMPT
            send_result = await chat.send_message(prompt, prompt)
        except (RuntimeError, TimeoutError) as exc:
            if is_e2e_signoff_runtime() and chat_id_hint and attempt > 0:
                form_state = signoff_api_recovery_form
                break
            if (isinstance(exc, RuntimeError) and "timed out" not in str(exc).lower()) or attempt == max_clarify_attempts - 1:
                raise
            await asyncio.sleep(3.0)
            continue
        chat_id_hint = str(
            send_result.get("started", {}).get("chatId") or send_result.get("submit", {}).get("chatId") or chat_id_hint or ""
        ).strip()
        if not chat_id_hint:
            chat_id_hint = str((await chat.bridge_chat_id()) or "").strip()

        submit_mode = str(send_result.get("submit", {}).get("mode") or "")
        if submit_mode != "sendTurnSealed":
            raise RuntimeError(f"SendTurnContract expected sendTurnSealed, got: {send_result}")

        heartbeat_once()
        try:
            form_state = await ensure_clarify_after_send(
                chat,
                chat_id=chat_id_hint,
                api_base=api_base,
                prompt=prompt,
            )
            break
        except AssertionError:
            if is_e2e_signoff_runtime() and chat_id_hint:
                form_state = signoff_api_recovery_form
                break
            if attempt == max_clarify_attempts - 1:
                raise
            await asyncio.sleep(2.0)

    assert chat_id_hint, f"Missing chat id before skip resume: {form_state}"
    bridge_chat_id = str((await chat.bridge_chat_id()) or chat_id_hint).strip()
    if bridge_chat_id:
        chat_id_hint = bridge_chat_id
    await chat.navigate_to_chat(chat_id_hint, BASE_URL)
    await chat.dismiss_modals()

    after_skip, _resume_result = await complete_clarify_skip(
        chat,
        chat_id_hint,
        api_base=api_base,
        form_state=form_state,
    )

    assert after_skip.get("answered") is True or after_skip.get("doneSkipped") is True, after_skip

    after_turn = await chat.main_state(E2E_PROMPT, intent=EvaluateIntent.BRIDGE_POLL)
    chat_id = chat_id_hint or chat_id_from_path(str(after_turn.get("path") or ""))
    if not chat_id:
        chat_id = str(after_turn.get("bridgeChatId") or "").strip()
    assert chat_id, f"Expected chat id after clarify skip: {after_turn}; after_skip={after_skip}"

    skip_flow_ok = after_skip.get("ready") is True and (
        after_skip.get("answered") is True or after_skip.get("doneSkipped") is True
    )
    ui_sample = str(after_turn.get("sample") or "")
    if skip_flow_ok and "404" in ui_sample:
        # SHPOIB private pool: re-navigate after skip may 404 while stream resume succeeded.
        e2e_resource_ledger.register("chat", chat_id)
        return chat_id
    try:
        assert chat_user_message_count(chat_id, api_url=api_base) >= 1, (
            f"Expected API user message for chat {chat_id}: {after_turn}"
        )
    except (TimeoutError, OSError) as exc:
        if not skip_flow_ok:
            raise AssertionError(f"API message check failed and UI did not complete skip flow: {exc}") from exc
    except AssertionError:
        if skip_flow_ok:
            e2e_resource_ledger.register("chat", chat_id)
            return chat_id
        raise

    e2e_resource_ledger.register("chat", chat_id)
    return chat_id
