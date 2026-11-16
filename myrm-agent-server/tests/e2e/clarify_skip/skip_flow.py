"""Skip step of the clarify Skip live E2E: UI bridge skip, then DOM skip, then API resume.

[INPUT]
- cdp_chat.mcp_ui::McpChatSession (POS: Chat UI session backed by the Chrome DevTools MCP mux owner model)
- cdp_chat.support::is_hitl_already_resolved (POS: Stable import surface of the E2E chat helpers; it defines nothing itself)
- dev_gate.contract (POS: Dev Gate contract SSOT for Chrome MCP E2E orchestration: error tokens, parallel caps and timeout budgets)
- e2e_core.orchestrator::remaining_wall_sec (POS: single import path for E2E session orchestration)
- tests.e2e.clarify_skip.waits (POS: polling layer of the clarify Skip E2E)
- tests.e2e.clarify_skip.resume (POS: retry policy of the clarify Skip E2E's API path)
- tests.e2e.clarify_skip.chat_actions (POS: chat-page setup and stream hand-over steps)
- tests.e2e.clarify_skip.bridge_js (POS: page-side scripts of the clarify Skip E2E)
- tests.e2e.clarify_skip.constants (POS: page origin, prompts and wait budget of the clarify Skip E2E)

[OUTPUT]
- complete_clarify_skip(chat, chat_id, api_base=, form_state=): (skip evidence, resume result) — the first path that proves the
  skip reached the agent wins; the API resume is the last resort

[POS]
Escalation ladder that skips the open clarification card and proves the run continued.
"""

from __future__ import annotations

import asyncio

import pytest
from cdp_chat.mcp_ui import McpChatSession
from cdp_chat.support import is_hitl_already_resolved
from dev_gate.contract import EvaluateIntent, is_e2e_signoff_runtime
from e2e_core.orchestrator import remaining_wall_sec

from tests.e2e.clarify_skip.bridge_js import CLICK_SKIP_JS, SKIP_VIA_BRIDGE_JS
from tests.e2e.clarify_skip.chat_actions import release_ui_stream_for_api
from tests.e2e.clarify_skip.constants import skip_api_wait_sec
from tests.e2e.clarify_skip.resume import resume_clarify_skip_after_ui_release
from tests.e2e.clarify_skip.waits import wait_api_skip_done, wait_dom_skip_button, wait_ui_skip_done


async def complete_clarify_skip(
    chat: McpChatSession,
    chat_id: str,
    *,
    api_base: str,
    form_state: dict[str, object],
) -> tuple[dict[str, object], dict[str, object]]:
    """Primary UI bridge skip, then DOM skip, then API resume with stall retries."""
    if remaining_wall_sec() < 120.0:
        pytest.fail(f"Clarify skip budget exhausted before resume (remaining_wall={remaining_wall_sec():.0f}s)")
    resume_result: dict[str, object] = {"ok": False, "event_types": []}
    poll_budget = min(
        skip_api_wait_sec(),
        max(60.0, remaining_wall_sec() - 90.0),
    )
    form_visible = form_state.get("hasForm") is True
    skip_button_visible = form_state.get("hasSkip") is True
    api_stream_fallback = form_state.get("api_stream_fallback") is True

    async def _api_skip_evidence(cap_sec: float) -> dict[str, object] | None:
        """Skip evidence from the stored messages; None when none shows up within `cap_sec`."""
        try:
            return await wait_api_skip_done(chat_id=chat_id, api_base=api_base, timeout_sec=min(cap_sec, poll_budget))
        except AssertionError:
            return None

    async def _ui_then_api_skip_evidence() -> dict[str, object] | None:
        """Skip evidence from the UI bridge, else from the stored messages; hands the stream to the API when neither shows."""
        try:
            return await wait_ui_skip_done(chat, timeout_sec=poll_budget)
        except AssertionError:
            evidence = await _api_skip_evidence(90.0)
            if evidence is None:
                await release_ui_stream_for_api(chat)
            return evidence

    async def _finalize_api_skip_resume(
        resume_result: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        if is_hitl_already_resolved(resume_result):
            pytest.fail(f"Clarify HITL already resolved before skip completed (chat_id={chat_id!r}): {resume_result}")
        if resume_result.get("ok") is not True:
            evidence = await _api_skip_evidence(90.0)
            if evidence is not None:
                return evidence, resume_result
        assert resume_result.get("ok") is True, f"API skip resume failed: {resume_result}; form={form_state}"
        # `ok` is continuation evidence (text after the skip, no new card); whether the model also said
        # DONE-SKIPPED is only reported.
        after_skip: dict[str, object] = {
            "ready": True,
            "source": "resume_stream",
            "doneSkipped": "DONE-SKIPPED" in str(resume_result.get("final_text") or "").upper(),
            "answered": True,
        }
        return after_skip, resume_result

    if api_stream_fallback and is_e2e_signoff_runtime():
        print(
            "E2E_SIGNOFF_CLARIFY: API-only skip resume path",
            flush=True,
        )
        await release_ui_stream_for_api(chat)
        resume_result = await resume_clarify_skip_after_ui_release(
            chat,
            chat_id,
            api_base=api_base,
        )
        return await _finalize_api_skip_resume(resume_result)

    if api_stream_fallback and form_visible and not skip_button_visible:
        polled = await wait_dom_skip_button(
            chat,
            timeout_sec=min(45.0, poll_budget),
        )
        if polled.get("hasSkip") is True:
            skip_button_visible = True
            form_state = {**form_state, **polled}

    bridge = await chat.evaluate(SKIP_VIA_BRIDGE_JS, intent=EvaluateIntent.SYNC_PROBE)
    if isinstance(bridge, dict) and bridge.get("ok") is True:
        evidence = await _ui_then_api_skip_evidence()
        if evidence is not None:
            return evidence, resume_result

    if form_state.get("hasSkip") is True:
        clicked = await chat.evaluate(CLICK_SKIP_JS, intent=EvaluateIntent.SYNC_PROBE)
        if isinstance(clicked, dict) and clicked.get("ok") is True:
            evidence = await _ui_then_api_skip_evidence()
            if evidence is not None:
                return evidence, resume_result

    # Skip flow may already finish asynchronously after stream release.
    if api_stream_fallback:
        await asyncio.sleep(1.5)
    await release_ui_stream_for_api(chat)
    if not (form_visible and not skip_button_visible):
        evidence = await _api_skip_evidence(120.0)
        if evidence is not None:
            return evidence, resume_result

    resume_result = await resume_clarify_skip_after_ui_release(
        chat,
        chat_id,
        api_base=api_base,
    )
    return await _finalize_api_skip_resume(resume_result)
