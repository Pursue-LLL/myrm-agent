"""API skip resume of the clarify Skip live E2E: skip the open card over the API, addressed to its pause, with retries.

[INPUT]
- cdp_chat.mcp_ui::McpChatSession (POS: Chat UI session backed by the Chrome DevTools MCP mux owner model)
- cdp_chat.support (POS: Stable import surface of the E2E chat helpers; it defines nothing itself)
- dev_gate.contract::is_e2e_signoff_runtime (POS: Dev Gate contract SSOT for Chrome MCP E2E orchestration: error tokens, parallel caps and timeout budgets)
- e2e_core.orchestrator::remaining_wall_sec (POS: single import path for E2E session orchestration)
- e2e_session_runtime.heartbeat::heartbeat_once (POS: unified E2E heartbeat SSOT: coordinator, wave lease and private runtime)
- tests.api.agent.utils::get_lite_model_selection (POS: Agent test helpers: lite model selection and provider-prefix handling)
- tests.e2e.clarify_skip.chat_actions (POS: chat-page setup and stream hand-over steps)
- tests.e2e.clarify_skip.constants (POS: page origin, prompts and wait budget of the clarify Skip E2E)

[OUTPUT]
- resume_clarify_skip_after_ui_release(chat, chat_id, api_base=, max_attempts=): the final resume result — releases the UI
  stream, finds the open card's interrupt id, skips it over the API and retries stalls and transient errors with backoff

[POS]
Retry policy of the clarify Skip E2E's API path; classifies resume results (no user query, stall, transient transport error).
"""

from __future__ import annotations

import asyncio

from cdp_chat.mcp_ui import McpChatSession
from cdp_chat.support import (
    chat_pending_clarification_interrupt_id,
    clarify_skip_resume_should_retry,
    is_hitl_already_resolved,
    resume_clarify_skip_via_api,
)
from dev_gate.contract import is_e2e_signoff_runtime
from e2e_core.orchestrator import remaining_wall_sec
from e2e_session_runtime.heartbeat import heartbeat_once

from tests.api.agent.utils import get_lite_model_selection
from tests.e2e.clarify_skip.chat_actions import release_ui_stream_for_api
from tests.e2e.clarify_skip.constants import E2E_SKIP_RESUME_QUERY, skip_api_wait_sec


def _failed_resume(error_type: str, message: str) -> dict[str, object]:
    return {
        "ok": False,
        "events": [],
        "event_types": [],
        "final_text": "",
        "error": {"type": "error", "error_type": error_type, "error": message},
    }


def _is_resume_progress_stall(result: dict[str, object]) -> bool:
    if result.get("ok") is True:
        return False
    event_types = result.get("event_types")
    if not isinstance(event_types, list):
        return False
    if "error" in event_types:
        return False
    final_text = str(result.get("final_text") or "").strip()
    if final_text:
        return False
    normalized = {str(item) for item in event_types if item is not None}
    return normalized == {"progress"} or (normalized.issubset({"progress"}) and "progress" in normalized)


def _is_no_user_query_error(result: dict[str, object]) -> bool:
    error = result.get("error")
    if isinstance(error, dict):
        message = str(error.get("error") or error.get("message") or "").lower()
        if "no user query found in messages" in message:
            return True
    return False


def _is_resume_retryable_transient_error(result: dict[str, object]) -> bool:
    error = result.get("error")
    if not isinstance(error, dict):
        return False
    error_type = str(error.get("error_type") or "").lower()
    message = str(error.get("error") or error.get("message") or "").lower()
    if "resumestreamidletimeout" in error_type:
        return True
    if "resumeapiconnecttimeout" in error_type:
        return True
    if "resumeapicalltimeout" in error_type:
        return True
    if "transport closed" in message:
        return True
    if "idle timeout" in message and "resume stream" in message:
        return True
    if "timed out" in message:
        return True
    return False


def _signoff_clarify_resume_max_attempts() -> int:
    remaining = remaining_wall_sec()
    if remaining >= 240.0:
        return 4
    if remaining >= 150.0:
        return 3
    if remaining >= 90.0:
        return 2
    return 1


async def resume_clarify_skip_after_ui_release(
    chat: McpChatSession,
    chat_id: str,
    *,
    api_base: str,
    max_attempts: int | None = None,
) -> dict[str, object]:
    """Drop WebUI SSE lease (no cancel API) then skip the open card over the API, addressed to its pause."""
    if max_attempts is None:
        max_attempts = _signoff_clarify_resume_max_attempts() if is_e2e_signoff_runtime() else 5
    last: dict[str, object] = {"ok": False, "err": "not-attempted"}
    backoff_sec = (
        (3.0, 5.0, 8.0, 12.0, 20.0, 30.0, 45.0, 60.0)
        if is_e2e_signoff_runtime()
        else (5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 75.0)
    )
    for attempt in range(max_attempts):
        await release_ui_stream_for_api(chat)
        pause = backoff_sec[min(attempt, len(backoff_sec) - 1)]
        await asyncio.sleep(0.75 + pause * 0.1)
        if is_e2e_signoff_runtime():
            api_timeout = min(45.0, max(20.0, remaining_wall_sec() - 50.0))
        else:
            api_timeout = min(
                skip_api_wait_sec(),
                max(60.0, remaining_wall_sec() - 60.0),
            )
        call_timeout = api_timeout + 10.0
        interrupt_id = await asyncio.to_thread(chat_pending_clarification_interrupt_id, chat_id, api_url=api_base)
        if interrupt_id is None:
            # The card may not be persisted yet, or the backend stalled: retry like any other transient outcome.
            last = _failed_resume("NoOpenClarification", f"chat {chat_id} has no open clarification card to skip")
            if attempt + 1 < max_attempts:
                heartbeat_once()
                await asyncio.sleep(pause)
                continue
            return last
        try:
            last = await asyncio.wait_for(
                asyncio.to_thread(
                    resume_clarify_skip_via_api,
                    chat_id,
                    interrupt_id=interrupt_id,
                    model_selection=get_lite_model_selection(),
                    api_url=api_base,
                    timeout_sec=api_timeout,
                ),
                timeout=call_timeout + 5.0,
            )
        except asyncio.TimeoutError:
            last = _failed_resume("ResumeApiCallTimeout", f"clarify resume to_thread timeout after {call_timeout + 5.0:.0f}s")
        if _is_no_user_query_error(last):
            heartbeat_once()
            try:
                last = await asyncio.wait_for(
                    asyncio.to_thread(
                        resume_clarify_skip_via_api,
                        chat_id,
                        interrupt_id=interrupt_id,
                        model_selection=get_lite_model_selection(),
                        api_url=api_base,
                        timeout_sec=api_timeout,
                        query=E2E_SKIP_RESUME_QUERY,
                    ),
                    timeout=call_timeout + 5.0,
                )
            except asyncio.TimeoutError:
                last = _failed_resume(
                    "ResumeApiCallTimeout",
                    f"clarify resume fallback to_thread timeout after {call_timeout + 5.0:.0f}s",
                )
        if last.get("ok") is True:
            return last
        if is_hitl_already_resolved(last):
            return last
        if clarify_skip_resume_should_retry(last):
            heartbeat_once()
            await asyncio.sleep(pause)
            continue
        if _is_resume_retryable_transient_error(last) and attempt + 1 < max_attempts:
            heartbeat_once()
            await asyncio.sleep(pause)
            continue
        if _is_resume_progress_stall(last) and attempt + 1 < max_attempts:
            heartbeat_once()
            await asyncio.sleep(pause)
            continue
        return last
    return last
