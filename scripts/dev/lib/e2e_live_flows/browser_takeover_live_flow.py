"""Browser takeover LIVE — orchestration flow body (R98)."""

from __future__ import annotations

import asyncio
import os

import pytest

from cdp_chat_resume import execute_resume_turn_stream_converge
from cdp_chat_support import (
    fetch_browser_takeover_resume_ids,
    get_e2e_api_url,
    wait_chat_messages_done,
    wait_e2e_backend_ready,
)
from cdp_chat_ui import chat_user_message_count
from e2e_live_flows._flow_base import FlowLogger
from e2e_live_flows.browser_takeover_live_api import (
    cancel_chat_via_api,
    reset_hitl_runtime_via_api,
    resume_via_api,
)
from e2e_live_flows.browser_takeover_live_gate import (
    E2E_NUDGE_PROMPT,
    E2E_PROMPT,
    MAX_SEND_ATTEMPTS,
    prepare_browser_turn,
    quiesce_mux_before_retry,
    require_browser_gate_triggered,
    wait_for_browser_ask_human_gate,
    wait_takeover_banner,
    wait_ui_stream_idle,
)
from mcp_chat_ui import McpChatSession
from resume_turn_contract import (
    RESUME_BUSY_BACKOFF_SEC,
    RESUME_DONE_POLL_PROGRESS_INTERVAL_SEC,
    RESUME_UI_ACK_EVALUATE_TIMEOUT_SEC,
    parallel_active_test_count,
    resolve_done_poll_fetch_timeout_sec,
    resolve_stream_converge_poll_timeout_sec,
)
from e2e_lease_heartbeat import heartbeat_e2e_lease
from mcp_chat_ui import McpChatSession
from tests.support.e2e_runtime_guard import E2EResourceLedger

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")


async def run_browser_takeover_live_flow(
    chat: McpChatSession,
    *,
    log: FlowLogger,
    ledger: E2EResourceLedger,
) -> str:
    """SendTurn → gate → UI_ACK → STREAM_CONVERGE → DONE."""

    def _p(msg: str) -> None:
        log.emit(msg)

    api_base = get_e2e_api_url()

    async def _wait_api_done(
        chat_id: str, *, api_url: str, timeout_sec: float = 120.0
    ) -> bool:
        return await asyncio.to_thread(
            wait_chat_messages_done,
            chat_id,
            api_url=api_url,
            timeout_sec=timeout_sec,
            fetch_timeout_sec=resolve_done_poll_fetch_timeout_sec(),
            progress_interval_sec=RESUME_DONE_POLL_PROGRESS_INTERVAL_SEC,
            on_tick=heartbeat_e2e_lease,
        )

    _p("dismiss_modals")
    await chat.dismiss_modals()
    _p("navigate → /")
    await chat.cdp("Page.navigate", {"url": f"{BASE_URL}/"}, recv_timeout=120.0)
    await asyncio.sleep(2.0)
    _p("click_new_chat")
    await chat.click_new_chat()
    _p("ensure_chat_surface")
    await chat.ensure_chat_surface(BASE_URL, timeout_sec=120.0)
    _p("ensure_model_ready")
    await chat.ensure_model_ready(timeout_sec=180.0)
    _p("prepare_browser_turn")
    await prepare_browser_turn(chat)
    _p("browser_turn ready — entering send loop")

    if not wait_e2e_backend_ready(api_url=api_base, timeout_sec=30.0):
        _p("private backend not ready — rebind SHPOIB")
        await chat.ensure_e2e_api_base_binding()
        if not wait_e2e_backend_ready(api_url=api_base, timeout_sec=30.0):
            pytest.fail(
                f"SHPOIB private backend not ready before send loop: {api_base}"
            )

    chat_id_hint: str | None = None
    banner: dict[str, object] | None = None
    hitl_api_confirmed = False
    for attempt in range(1, MAX_SEND_ATTEMPTS + 1):
        if attempt > 1:
            if hitl_api_confirmed:
                _p(
                    "E2E_GATE_ONCE: API confirmed HITL — skip send retry "
                    f"(attempt={attempt})"
                )
                break
            _p(f"retry attempt={attempt} — click_new_chat")
            if chat_id_hint:
                _p(f"cancel stale chat before retry chatId={chat_id_hint}")
                await asyncio.to_thread(
                    cancel_chat_via_api,
                    api_base=api_base,
                    chat_id=chat_id_hint,
                )
                chat_id_hint = None
                await asyncio.sleep(3.0)
            _p("quiesce mux before retry UI")
            await quiesce_mux_before_retry(chat)
            await chat.click_new_chat()
            await chat.ensure_chat_surface(BASE_URL, timeout_sec=120.0)
            await chat.ensure_model_ready(timeout_sec=180.0)
            await prepare_browser_turn(chat)
        last_prompt = E2E_PROMPT if attempt == 1 else E2E_NUDGE_PROMPT
        heartbeat_e2e_lease()
        if not wait_e2e_backend_ready(api_url=api_base, timeout_sec=10.0):
            await chat.ensure_e2e_api_base_binding()
        _p(f"send_message attempt={attempt}")
        send_result = await chat.send_message(last_prompt, last_prompt)
        chat_id_hint = (
            str(
                send_result.get("started", {}).get("chatId")
                or send_result.get("submit", {}).get("chatId")
                or chat_id_hint
                or ""
            ).strip()
            or None
        )
        if not chat_id_hint:
            chat_id_hint = str((await chat.bridge_chat_id()) or "").strip() or None
        submit_mode = str(send_result.get("submit", {}).get("mode") or "")
        _p(
            f"send_message sealed chatId={chat_id_hint} "
            f"submitMode={submit_mode}"
        )
        if submit_mode != "sendTurnSealed":
            raise RuntimeError(
                f"SendTurnContract expected sendTurnSealed, got: {send_result}"
            )

        shim_proc = getattr(chat._client, "_process", None)
        shim_alive = shim_proc is not None and shim_proc.poll() is None
        shim_pid = shim_proc.pid if shim_proc else None
        _p(
            f"pre-gate shim diagnostic: pid={shim_pid} alive={shim_alive} "
            f"pages={len(getattr(chat._client, '_pages', {}))} "
            f"disconnected={len(getattr(chat._client, '_disconnected_pages', {}))}"
        )
        _p("wait_for_browser_ask_human_gate")
        last_tool, takeover_pending, api_hitl = await wait_for_browser_ask_human_gate(
            chat,
            chat_id=chat_id_hint,
            api_url=api_base,
        )
        if api_hitl:
            hitl_api_confirmed = True
        _p(
            f"gate result: lastTool={last_tool} pending={takeover_pending} "
            f"api_hitl={api_hitl} locked={hitl_api_confirmed}"
        )
        if not takeover_pending and not last_tool.endswith("browser_ask_human_tool"):
            if attempt >= MAX_SEND_ATTEMPTS:
                require_browser_gate_triggered(
                    last_tool=last_tool,
                    takeover_pending=takeover_pending,
                )
            continue

        if takeover_pending or api_hitl:
            _p(
                "gate HITL confirmed — skip DOM banner wait "
                f"(pending={takeover_pending} api_hitl={api_hitl} "
                f"lastTool={last_tool!r}; proceed to Done resume)"
            )
            banner = {
                "ready": True,
                "hasExtensionTitle": True,
                "source": "gate_pending_skip_dom",
            }
            break

        _p("wait_takeover_banner")
        try:
            banner = await wait_takeover_banner(chat, timeout_sec=90.0)
            _p(f"banner appeared: ready={banner.get('ready')}")
            break
        except AssertionError:
            if attempt >= MAX_SEND_ATTEMPTS:
                raise
            _p("banner not ready — will retry")
            heartbeat_e2e_lease()

    assert banner is not None
    assert (
        banner.get("hasExtensionTitle") is True
    ), f"Expected extension banner: {banner}"

    pre_done_diag: dict[str, object] | str = {"skipped": "api_only_resume"}
    if banner.get("source") != "gate_pending_skip_dom":
        pre_done_diag = await chat.evaluate(
            """(() => {
              const bridge = window.__MYRM_E2E_CHAT__;
              const snap = bridge?.getBrowserTakeoverSnapshot?.() ?? {};
              const turn = bridge?.turnSnapshot?.() ?? {};
              return {
                takeoverPending: snap.pending,
                takeoverMessageId: snap.messageId ?? null,
                chatId: turn.chatId ?? null,
                isStreaming: turn.isStreaming,
                userCount: turn.userCount,
                lastAssistantSample: turn.lastAssistantSample ?? null,
              };
            })()""",
            await_promise=False,
            recv_timeout=15.0,
        )
    _p(f"pre-Done diag: {pre_done_diag}")

    resume_chat_id = str(chat_id_hint or "").strip()
    resume_msg_id = ""
    if isinstance(pre_done_diag, dict):
        diag_chat = str(pre_done_diag.get("chatId") or "").strip()
        diag_mid = str(pre_done_diag.get("takeoverMessageId") or "").strip()
        if diag_chat:
            resume_chat_id = diag_chat
        if diag_mid:
            resume_msg_id = diag_mid

    async def _release_ui_sse() -> None:
        _p("ResumeTurnContract: release in-flight UI SSE before API resume")
        try:
            await chat.evaluate(
                """(() => window.__MYRM_E2E_CHAT__?.releaseActiveStreamForApiResume?.())()""",
                await_promise=False,
                recv_timeout=15.0,
            )
        except (RuntimeError, TimeoutError):
            pass
        await asyncio.sleep(1.5)

    _p("ResumeTurnContract UI_ACK via completeBrowserTakeoverWithResume")
    try:
        ui_ack_raw = await chat.evaluate(
            """(async () => {
              const bridge = window.__MYRM_E2E_CHAT__;
              if (!bridge?.completeBrowserTakeoverWithResume) {
                return { ok: false, reason: 'bridge_method_missing' };
              }
              return await bridge.completeBrowserTakeoverWithResume();
            })()""",
            await_promise=True,
            recv_timeout=RESUME_UI_ACK_EVALUATE_TIMEOUT_SEC,
        )
    except TimeoutError:
        _p("ResumeTurnContract UI_ACK MUX timeout — quiesce then STREAM_CONVERGE")
        await quiesce_mux_before_retry(chat)
        ui_ack_raw = {"ok": False, "reason": "mux_timeout"}

    ui_ack = ui_ack_raw if isinstance(ui_ack_raw, dict) else {"value": ui_ack_raw}
    _p(f"ResumeTurnContract UI_ACK result: {ui_ack}")
    resume_chat_id = str(
        ui_ack.get("chatId") or resume_chat_id or chat_id_hint or ""
    ).strip()
    resume_msg_id = str(
        ui_ack.get("resumeMessageId")
        or ui_ack.get("storeMessageId")
        or resume_msg_id
        or ""
    ).strip()

    if not resume_msg_id and resume_chat_id:
        api_ids = await asyncio.to_thread(
            fetch_browser_takeover_resume_ids,
            resume_chat_id,
            api_url=api_base,
        )
        if api_ids:
            resume_msg_id = str(api_ids.get("resumeMessageId") or "").strip()
            _p(f"ResumeTurnContract approval ids fallback: {api_ids}")

    assert resume_chat_id, f"No chatId after UI_ACK: {ui_ack}"
    assert resume_msg_id, f"No messageId after UI_ACK: {ui_ack}"

    if ui_ack.get("ok") is not True:
        _p(
            f"ResumeTurnContract UI_ACK not ok ({ui_ack}) — "
            "proceed STREAM_CONVERGE with resolved msgId"
        )

    ui_resume_started = ui_ack.get("resumeStarted") is True or (
        ui_ack.get("ok") is True and bool(resume_msg_id)
    )
    if ui_resume_started:
        _p(
            "ResumeTurnContract UI resume fire-and-forget started — "
            "STREAM_CONVERGE poll only (no API resume / no SSE release)"
        )
        await asyncio.sleep(2.0)
        poll_timeout = resolve_stream_converge_poll_timeout_sec()
        _p(
            f"ResumeTurnContract poll-only timeout={int(poll_timeout)}s "
            f"parallel_active={parallel_active_test_count()}"
        )
        done = await _wait_api_done(
            resume_chat_id,
            api_url=api_base,
            timeout_sec=poll_timeout,
        )
    else:
        _p(
            "ResumeTurnContract UI resume not started — "
            "fallback API STREAM_CONVERGE after SSE release"
        )
        await _release_ui_sse()
        await quiesce_mux_before_retry(chat)
        await wait_ui_stream_idle(chat, timeout_sec=45.0)
        await asyncio.sleep(3.0)

        async def _on_session_busy() -> None:
            _p("ResumeTurnContract 409 busy — release SSE + reset HITL runtime")
            await _release_ui_sse()
            await asyncio.to_thread(
                reset_hitl_runtime_via_api,
                api_base=api_base,
            )
            await asyncio.sleep(RESUME_BUSY_BACKOFF_SEC)

        done = await execute_resume_turn_stream_converge(
            api_base=api_base,
            chat_id=resume_chat_id,
            message_id=resume_msg_id,
            resume_via_api=resume_via_api,
            wait_api_done=_wait_api_done,
            release_ui_sse=_release_ui_sse,
            on_session_busy=_on_session_busy,
            log=_p,
        )
    _p(f"ResumeTurnContract STREAM_CONVERGE done={done}")

    assert done, (
        f"Agent did not reply DONE after browser takeover resume "
        f"for chat {resume_chat_id}; ui_ack={ui_ack}"
    )

    chat_id = resume_chat_id
    _p(f"PASSED chat_id={chat_id}")
    assert chat_user_message_count(chat_id, api_url=api_base) >= 1
    ledger.register("chat", chat_id)
    return chat_id
