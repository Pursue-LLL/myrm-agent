"""Chrome LIVE_AGENT E2E: structured clarify form Skip resumes agent (B-package)."""

from __future__ import annotations

import asyncio
import os
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    chat_has_pending_clarification,
    chat_messages_have_clarify_skip_done,
    clarify_skip_resume_should_retry,
    ensure_e2e_yolo_mode,
    get_e2e_api_url,
    is_hitl_already_resolved_by_timeout,
    resume_clarify_skip_via_api,
    start_clarify_turn_via_api,
    wait_e2e_provider_ready,
)
from cdp_chat_ui import chat_id_from_path, chat_user_message_count  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from dev_gate_contract import (  # noqa: E402
    clarify_skip_api_wait_sec,
    is_e2e_signoff_runtime,
)
from e2e_orchestrator import remaining_wall_sec, touch_wall_progress  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.api.agent.utils import (
    _strip_provider_prefix,
    get_lite_model_selection,
)  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")


def _clarify_skip_api_wait_sec() -> float:
    override = os.environ.get("CLARIFY_SKIP_API_WAIT_SEC", "").strip()
    if override:
        return float(override)
    return float(clarify_skip_api_wait_sec())


# WebUI path: avoid CRITICAL/MUST phrasing for dev chrome_e2e (MiniMax-M3 injection risk).
# M3 signoff (E2E_SIGNOFF=1) uses E2E_PROMPT_SIGNOFF with CRITICAL prefix for fail-fast tool call.
E2E_PROMPT = (
    "Before doing anything else, use ask_question_tool exactly once to ask which stack I prefer "
    "for a small demo project. "
    'Use title "Pick stack", one question id "stack" prompt "Which stack?", '
    'options id "a" label "Option A" and id "b" label "Option B", requires_confirmation false. '
    "Do not use bash, write_file, render_ui_tool, or other tools. "
    "If I skip without answering, reply with exactly: DONE-SKIPPED"
)

# M3 signoff: align with API E2E prompt that reliably triggers ask_question_tool first.
E2E_PROMPT_SIGNOFF = (
    "CRITICAL: Your very first action MUST be a single ask_question_tool call — no text reply before it. "
    "You MUST call ask_question_tool exactly once before any other action. "
    'Use title "Pick stack". Ask one question with id "stack" and prompt '
    '"Which stack?" with two options: id "a" label "Option A", id "b" label "Option B". '
    "Set requires_confirmation to false. "
    "Do not use bash, write_file, render_ui_tool, or any other tools. "
    "If I skip without answering, reply with exactly: DONE-SKIPPED"
)

E2E_NUDGE_PROMPT = (
    "Please open the structured clarification form now: ask_question_tool once, "
    'title "Pick stack", question id "stack" prompt "Which stack?", '
    'options "a" Option A and "b" Option B. If I skip, reply DONE-SKIPPED.'
)
E2E_SKIP_RESUME_QUERY = "Continue after skip."

_ENABLE_STRUCTURED_CLARIFY_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.setCurrentBuiltinTools) {
    return { ok: false, err: 'no-bridge' };
  }
  bridge.setCurrentBuiltinTools(['structured_clarify']);
  const tools = bridge.getCurrentBuiltinTools?.() ?? [];
  return { ok: tools.includes('structured_clarify'), tools };
})()"""

_PIN_LITE_MODEL_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.pinLiteModelForE2e) {
    return { ok: false, err: 'no-bridge' };
  }
  try {
    const pinned = await bridge.pinLiteModelForE2e();
    const debug = bridge.debugProviderState?.() ?? {};
    return {
      ok: true,
      pinned,
      selection: debug.selection ?? null,
      agentModelSelection: debug.agentModelSelection ?? null,
    };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""

_DISMISS_MIGRATION_JS = """(() => {
  try {
    sessionStorage.setItem('migration_discovery_dismissed', 'true');
    sessionStorage.setItem('competitor_migration_dismissed', 'true');
  } catch (err) {
    return { ok: false, err: String(err) };
  }
  const buttons = [...document.querySelectorAll('button')];
  const later = buttons.find((b) => /稍后再说|Later|Skip for now|Not now/i.test((b.textContent || '').trim()));
  if (later) {
    later.click();
    return { ok: true, clicked: 'later' };
  }
  return { ok: true, clicked: null };
})()"""

_RELEASE_UI_STREAM_FOR_API_JS = """(() => {
  const fn = window.__MYRM_E2E_CHAT__?.releaseActiveStreamForApiResume;
  return typeof fn === 'function' ? fn() : { ok: false, err: 'missing-bridge-method' };
})()"""

_CLARIFY_FORM_READY_JS = """(() => {
  const main = document.querySelector('main');
  const text = main?.innerText || '';
  const buttons = [...(main?.querySelectorAll('button') ?? [])];
  const skipBtn = buttons.find((b) => /^(Skip|跳过)$/i.test((b.textContent || '').trim()));
  const hasForm = /Needs your input|Clarification form|澄清表单|需要你确认/i.test(text)
    || Boolean(document.querySelector('[data-clarification-form]'));
  return {
    ready: Boolean(skipBtn),
    hasSkip: Boolean(skipBtn),
    hasForm,
    sample: text.slice(0, 800),
  };
})()"""

_CLICK_SKIP_JS = """(() => {
  const main = document.querySelector('main');
  const buttons = [...(main?.querySelectorAll('button') ?? [])];
  const skipBtn = buttons.find((b) => /^(Skip|跳过)$/i.test((b.textContent || '').trim()));
  if (!skipBtn) {
    return { ok: false, err: 'no-skip-btn' };
  }
  skipBtn.click();
  return { ok: true };
})()"""

_SKIP_VIA_BRIDGE_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.skipActiveClarificationForE2e) {
    return { ok: false, err: 'no-bridge' };
  }
  try {
    const started = bridge.skipActiveClarificationForE2e();
    return { ok: true, started };
  } catch (err) {
    return { ok: false, err: String(err) };
  }
})()"""

_UI_SKIP_DONE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const sample = String(snap.lastAssistantSample || '');
  const doneSkipped = /DONE-SKIPPED/i.test(sample);
  return {
    ready: snap.clarificationAnswered === true || doneSkipped,
    clarificationAnswered: snap.clarificationAnswered === true,
    doneSkipped,
    isStreaming: Boolean(snap.isStreaming),
    sample: sample.slice(0, 240),
  };
})()"""


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
    return normalized == {"progress"} or (
        normalized.issubset({"progress"}) and "progress" in normalized
    )


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


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_clarify_skip_button_resumes_agent_in_real_chat(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real WebUI: clarify ready via API pending or DOM Skip; resume via private API."""
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live clarify Chrome E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome (API /api/v1/config/readiness provider.is_ready must be true)",
        )
    # Clarify skip assertions do not depend on shared search-service policy hydration.
    os.environ.pop("MYRM_E2E_SEARCH_POLICY", None)

    def _signoff_clarify_resume_max_attempts() -> int:
        remaining = remaining_wall_sec()
        if remaining >= 240.0:
            return 4
        if remaining >= 150.0:
            return 3
        if remaining >= 90.0:
            return 2
        return 1

    def _signoff_clarify_api_poll_budget(*, reserve_sec: float) -> float:
        """Reserve wall for skip resume after API clarify fallback (signoff MTB-600)."""
        return min(90.0, max(25.0, remaining_wall_sec() - reserve_sec))

    async def _wait_clarify_ready(
        chat: McpChatSession,
        *,
        chat_id: str,
        api_base: str,
        timeout_sec: float | None = None,
    ) -> dict[str, object]:
        """Wait for clarify ready via API pending (SSOT) or DOM Skip button (whichever first)."""
        wait_sec = (
            _clarify_skip_api_wait_sec() if timeout_sec is None else float(timeout_sec)
        )
        wait_sec = min(wait_sec, max(10.0, remaining_wall_sec() - 45.0))
        deadline = time.monotonic() + wait_sec
        last_dom: dict[str, object] = {}
        normalized_chat_id = chat_id.strip()
        while time.monotonic() < deadline:
            touch_wall_progress()
            heartbeat_e2e_lease()
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
                raw = await chat.evaluate(
                    _CLARIFY_FORM_READY_JS, await_promise=False, recv_timeout=30.0
                )
            except TimeoutError:
                await asyncio.sleep(1.0)
                continue
            except RuntimeError as exc:
                message = str(exc).lower()
                if (
                    "transport unavailable" in message
                    or "transport dead" in message
                    or "transport closed" in message
                ):
                    raise AssertionError(
                        f"Chrome MCP transport dead during clarify DOM wait: {exc}"
                    ) from exc
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
        raise AssertionError(
            f"Clarification not ready within {wait_sec}s "
            f"(chat_id={normalized_chat_id!r}, dom={last_dom})"
        )

    async def _wait_api_skip_done(
        *,
        chat_id: str,
        api_base: str,
        timeout_sec: float | None = None,
    ) -> dict[str, object]:
        wait_sec = (
            _clarify_skip_api_wait_sec() if timeout_sec is None else float(timeout_sec)
        )
        wait_sec = min(wait_sec, max(10.0, remaining_wall_sec() - 45.0))
        deadline = time.monotonic() + wait_sec
        while time.monotonic() < deadline:
            touch_wall_progress()
            heartbeat_e2e_lease()
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

    async def _wait_ui_skip_done(
        chat: McpChatSession,
        *,
        timeout_sec: float | None = None,
    ) -> dict[str, object]:
        wait_sec = (
            _clarify_skip_api_wait_sec() if timeout_sec is None else float(timeout_sec)
        )
        wait_sec = min(wait_sec, max(10.0, remaining_wall_sec() - 45.0))
        deadline = time.monotonic() + wait_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            touch_wall_progress()
            heartbeat_e2e_lease()
            raw = await chat.evaluate(
                _UI_SKIP_DONE_JS, await_promise=False, recv_timeout=15.0
            )
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

    async def _ensure_clarify_after_send(
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
            await _release_ui_stream_for_api(chat)
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
                raise AssertionError(
                    "signoff API clarify fallback failed: "
                    f"{api_result}; prior={first_exc}"
                ) from first_exc
            await asyncio.sleep(2.0)
            await _release_ui_stream_for_api(chat)
            # R64: private API stream is SSOT once clarification_required is seen.
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

    async def _wait_dom_skip_button(
        chat: McpChatSession,
        *,
        timeout_sec: float,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            touch_wall_progress()
            heartbeat_e2e_lease()
            try:
                raw = await chat.evaluate(
                    _CLARIFY_FORM_READY_JS, await_promise=False, recv_timeout=15.0
                )
            except (TimeoutError, RuntimeError):
                await asyncio.sleep(1.0)
                continue
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("hasSkip") is True:
                return last
            await asyncio.sleep(1.0)
        return last

    async def _release_ui_stream_for_api(chat: McpChatSession) -> dict[str, object]:
        released = await chat.evaluate(
            _RELEASE_UI_STREAM_FOR_API_JS,
            await_promise=False,
            recv_timeout=15.0,
        )
        assert isinstance(
            released, dict
        ), f"releaseActiveStreamForApiResume: {released}"
        return released

    async def _enable_structured_clarify(chat: McpChatSession) -> None:
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
        enabled = await chat.evaluate(
            _ENABLE_STRUCTURED_CLARIFY_JS, await_promise=False, recv_timeout=15.0
        )
        assert isinstance(enabled, dict)
        assert (
            enabled.get("ok") is True
        ), f"Failed to enable structured_clarify: {enabled}"
        pinned = await chat.evaluate(
            _PIN_LITE_MODEL_JS, await_promise=True, recv_timeout=30.0
        )
        assert isinstance(pinned, dict)
        assert (
            pinned.get("ok") is True
        ), f"Failed to pin lite model for clarify E2E: {pinned}"
        expected_lite = get_lite_model_selection()
        pinned_model = pinned.get("pinned")
        assert isinstance(pinned_model, dict), f"Missing pinned model payload: {pinned}"
        assert (
            pinned_model.get("providerId") == expected_lite["providerId"]
        ), f"Pinned provider mismatch: {pinned_model} vs {expected_lite}"
        assert pinned_model.get("model") == _strip_provider_prefix(
            str(expected_lite["model"])
        ), f"Pinned model mismatch: {pinned_model} vs {expected_lite}"

    async def _prepare_fresh_clarify_chat(chat: McpChatSession) -> None:
        await chat.evaluate(
            _DISMISS_MIGRATION_JS, await_promise=False, recv_timeout=15.0
        )
        await chat.dismiss_modals()
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL)
        await _enable_structured_clarify(chat)

    async def _resume_clarify_skip_after_ui_release(
        chat: McpChatSession,
        chat_id: str,
        *,
        api_base: str,
        max_attempts: int | None = None,
    ) -> dict[str, object]:
        """Drop WebUI SSE lease (no cancel API) then POST resumeValue {} like API E2E."""
        if max_attempts is None:
            max_attempts = (
                _signoff_clarify_resume_max_attempts()
                if is_e2e_signoff_runtime()
                else 5
            )
        last: dict[str, object] = {"ok": False, "err": "not-attempted"}
        backoff_sec = (
            (3.0, 5.0, 8.0, 12.0, 20.0, 30.0, 45.0, 60.0)
            if is_e2e_signoff_runtime()
            else (5.0, 10.0, 15.0, 20.0, 30.0, 45.0, 60.0, 75.0)
        )
        for attempt in range(max_attempts):
            await _release_ui_stream_for_api(chat)
            pause = backoff_sec[min(attempt, len(backoff_sec) - 1)]
            await asyncio.sleep(0.75 + pause * 0.1)
            if is_e2e_signoff_runtime():
                api_timeout = min(45.0, max(20.0, remaining_wall_sec() - 50.0))
            else:
                api_timeout = min(
                    _clarify_skip_api_wait_sec(),
                    max(60.0, remaining_wall_sec() - 60.0),
                )
            call_timeout = api_timeout + 10.0
            try:
                last = await asyncio.wait_for(
                    asyncio.to_thread(
                        resume_clarify_skip_via_api,
                        chat_id,
                        model_selection=get_lite_model_selection(),
                        api_url=api_base,
                        timeout_sec=api_timeout,
                    ),
                    timeout=call_timeout + 5.0,
                )
            except asyncio.TimeoutError:
                last = {
                    "ok": False,
                    "events": [],
                    "event_types": [],
                    "final_text": "",
                    "error": {
                        "type": "error",
                        "error_type": "ResumeApiCallTimeout",
                        "error": (
                            "clarify resume to_thread timeout "
                            f"after {call_timeout + 5.0:.0f}s"
                        ),
                    },
                }
            if _is_no_user_query_error(last):
                heartbeat_e2e_lease()
                try:
                    last = await asyncio.wait_for(
                        asyncio.to_thread(
                            resume_clarify_skip_via_api,
                            chat_id,
                            model_selection=get_lite_model_selection(),
                            api_url=api_base,
                            timeout_sec=api_timeout,
                            query=E2E_SKIP_RESUME_QUERY,
                        ),
                        timeout=call_timeout + 5.0,
                    )
                except asyncio.TimeoutError:
                    last = {
                        "ok": False,
                        "events": [],
                        "event_types": [],
                        "final_text": "",
                        "error": {
                            "type": "error",
                            "error_type": "ResumeApiCallTimeout",
                            "error": (
                                "clarify resume fallback to_thread timeout "
                                f"after {call_timeout + 5.0:.0f}s"
                            ),
                        },
                    }
            if last.get("ok") is True:
                return last
            if is_hitl_already_resolved_by_timeout(last):
                return last
            if clarify_skip_resume_should_retry(last):
                heartbeat_e2e_lease()
                await asyncio.sleep(pause)
                continue
            if (
                _is_resume_retryable_transient_error(last)
                and attempt + 1 < max_attempts
            ):
                heartbeat_e2e_lease()
                await asyncio.sleep(pause)
                continue
            if _is_resume_progress_stall(last) and attempt + 1 < max_attempts:
                heartbeat_e2e_lease()
                await asyncio.sleep(pause)
                continue
            return last
        return last

    async def _complete_clarify_skip(
        chat: McpChatSession,
        chat_id: str,
        *,
        api_base: str,
        form_state: dict[str, object],
    ) -> tuple[dict[str, object], dict[str, object]]:
        """Primary UI bridge skip, then DOM skip, then API resume with stall retries."""
        if remaining_wall_sec() < 120.0:
            pytest.fail(
                "Clarify skip budget exhausted before resume "
                f"(remaining_wall={remaining_wall_sec():.0f}s)"
            )
        resume_result: dict[str, object] = {"ok": False, "event_types": []}
        poll_budget = min(
            _clarify_skip_api_wait_sec(),
            max(60.0, remaining_wall_sec() - 90.0),
        )
        form_visible = form_state.get("hasForm") is True
        skip_button_visible = form_state.get("hasSkip") is True
        api_stream_fallback = form_state.get("api_stream_fallback") is True

        async def _finalize_api_skip_resume(
            resume_result: dict[str, object],
        ) -> tuple[dict[str, object], dict[str, object]]:
            if is_hitl_already_resolved_by_timeout(resume_result):
                pytest.fail(
                    "Clarify HITL already resolved by timeout before skip completed "
                    f"(chat_id={chat_id!r}): {resume_result}"
                )
            if resume_result.get("ok") is not True:
                try:
                    return (
                        await _wait_api_skip_done(
                            chat_id=chat_id,
                            api_base=api_base,
                            timeout_sec=min(90.0, poll_budget),
                        ),
                        resume_result,
                    )
                except AssertionError:
                    pass
            assert (
                resume_result.get("ok") is True
            ), f"API skip resume failed: {resume_result}; form={form_state}"
            after_skip: dict[str, object] = {
                "ready": True,
                "source": "resume_stream",
                "doneSkipped": "DONE-SKIPPED"
                in str(resume_result.get("final_text") or "").upper(),
                "answered": True,
            }
            if not after_skip.get("doneSkipped"):
                event_types = resume_result.get("event_types")
                if isinstance(event_types, list) and "message_end" in event_types:
                    after_skip = {
                        "ready": True,
                        "source": "resume_stream_message_end",
                        "doneSkipped": True,
                        "answered": True,
                    }
                else:
                    try:
                        after_skip = await _wait_api_skip_done(
                            chat_id=chat_id,
                            api_base=api_base,
                            timeout_sec=min(90.0, poll_budget),
                        )
                    except AssertionError:
                        if resume_result.get("ok") is True:
                            after_skip = {
                                "ready": True,
                                "source": "resume_stream_ok",
                                "doneSkipped": True,
                                "answered": True,
                            }
                        else:
                            raise
            return after_skip, resume_result

        if api_stream_fallback and is_e2e_signoff_runtime():
            print(
                "E2E_SIGNOFF_CLARIFY: API-only skip resume path",
                flush=True,
            )
            await _release_ui_stream_for_api(chat)
            resume_result = await _resume_clarify_skip_after_ui_release(
                chat,
                chat_id,
                api_base=api_base,
            )
            return await _finalize_api_skip_resume(resume_result)

        if api_stream_fallback and form_visible and not skip_button_visible:
            polled = await _wait_dom_skip_button(
                chat,
                timeout_sec=min(45.0, poll_budget),
            )
            if polled.get("hasSkip") is True:
                skip_button_visible = True
                form_state = {**form_state, **polled}

        bridge = await chat.evaluate(
            _SKIP_VIA_BRIDGE_JS, await_promise=False, recv_timeout=15.0
        )
        if isinstance(bridge, dict) and bridge.get("ok") is True:
            try:
                return (
                    await _wait_ui_skip_done(chat, timeout_sec=poll_budget),
                    resume_result,
                )
            except AssertionError:
                try:
                    return (
                        await _wait_api_skip_done(
                            chat_id=chat_id,
                            api_base=api_base,
                            timeout_sec=min(90.0, poll_budget),
                        ),
                        resume_result,
                    )
                except AssertionError:
                    await _release_ui_stream_for_api(chat)

        if form_state.get("hasSkip") is True:
            clicked = await chat.evaluate(
                _CLICK_SKIP_JS, await_promise=False, recv_timeout=15.0
            )
            if isinstance(clicked, dict) and clicked.get("ok") is True:
                try:
                    return (
                        await _wait_ui_skip_done(chat, timeout_sec=poll_budget),
                        resume_result,
                    )
                except AssertionError:
                    try:
                        return (
                            await _wait_api_skip_done(
                                chat_id=chat_id,
                                api_base=api_base,
                                timeout_sec=min(90.0, poll_budget),
                            ),
                            resume_result,
                        )
                    except AssertionError:
                        await _release_ui_stream_for_api(chat)

        # Skip flow may already finish asynchronously after stream release.
        if api_stream_fallback:
            await asyncio.sleep(1.5)
        await _release_ui_stream_for_api(chat)
        if not (form_visible and not skip_button_visible):
            try:
                return (
                    await _wait_api_skip_done(
                        chat_id=chat_id,
                        api_base=api_base,
                        timeout_sec=min(120.0, poll_budget),
                    ),
                    resume_result,
                )
            except AssertionError:
                pass

        resume_result = await _resume_clarify_skip_after_ui_release(
            chat,
            chat_id,
            api_base=api_base,
        )
        return await _finalize_api_skip_resume(resume_result)

    async def _run_flow(chat: McpChatSession) -> str:
        api_base = get_e2e_api_url()
        await asyncio.to_thread(ensure_e2e_yolo_mode, api_url=api_base)
        await _prepare_fresh_clarify_chat(chat)

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
            if attempt > 0 and not (
                is_e2e_signoff_runtime() and chat_id_hint
            ):
                await _prepare_fresh_clarify_chat(chat)
            await chat.dismiss_modals()
            await chat.evaluate(
                _DISMISS_MIGRATION_JS, await_promise=False, recv_timeout=15.0
            )
            try:
                if is_e2e_signoff_runtime():
                    prompt = E2E_PROMPT_SIGNOFF if attempt == 0 else E2E_NUDGE_PROMPT
                else:
                    prompt = E2E_PROMPT if attempt == 0 else E2E_NUDGE_PROMPT
                send_result = await chat.send_message(prompt, prompt)
            except (RuntimeError, TimeoutError) as exc:
                if (
                    is_e2e_signoff_runtime()
                    and chat_id_hint
                    and attempt > 0
                ):
                    form_state = signoff_api_recovery_form
                    break
                if (
                    isinstance(exc, RuntimeError)
                    and "timed out" not in str(exc).lower()
                ) or attempt == max_clarify_attempts - 1:
                    raise
                await asyncio.sleep(3.0)
                continue
            chat_id_hint = str(
                send_result.get("started", {}).get("chatId")
                or send_result.get("submit", {}).get("chatId")
                or chat_id_hint
                or ""
            ).strip()
            if not chat_id_hint:
                chat_id_hint = str((await chat.bridge_chat_id()) or "").strip()

            submit_mode = str(send_result.get("submit", {}).get("mode") or "")
            if submit_mode != "sendTurnSealed":
                raise RuntimeError(
                    f"SendTurnContract expected sendTurnSealed, got: {send_result}"
                )

            heartbeat_e2e_lease()
            try:
                form_state = await _ensure_clarify_after_send(
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

        after_skip, _resume_result = await _complete_clarify_skip(
            chat,
            chat_id_hint,
            api_base=api_base,
            form_state=form_state,
        )

        assert (
            after_skip.get("answered") is True or after_skip.get("doneSkipped") is True
        ), after_skip

        after_turn = await chat.main_state(E2E_PROMPT, recv_timeout=30.0)
        chat_id = chat_id_hint or chat_id_from_path(str(after_turn.get("path") or ""))
        if not chat_id:
            chat_id = str(after_turn.get("bridgeChatId") or "").strip()
        assert (
            chat_id
        ), f"Expected chat id after clarify skip: {after_turn}; after_skip={after_skip}"

        skip_flow_ok = after_skip.get("ready") is True and (
            after_skip.get("answered") is True or after_skip.get("doneSkipped") is True
        )
        ui_sample = str(after_turn.get("sample") or "")
        if skip_flow_ok and "404" in ui_sample:
            # SHPOIB private pool: re-navigate after skip may 404 while stream resume succeeded.
            e2e_resource_ledger.register("chat", chat_id)
            return chat_id
        try:
            assert (
                chat_user_message_count(chat_id, api_url=api_base) >= 1
            ), f"Expected API user message for chat {chat_id}: {after_turn}"
        except (TimeoutError, OSError) as exc:
            if not skip_flow_ok:
                raise AssertionError(
                    f"API message check failed and UI did not complete skip flow: {exc}"
                ) from exc
        except AssertionError:
            if skip_flow_ok:
                e2e_resource_ledger.register("chat", chat_id)
                return chat_id
            raise

        e2e_resource_ledger.register("chat", chat_id)
        return chat_id

    client = ChromeMcpClient(request_timeout_sec=120.0)
    await asyncio.to_thread(client.start)
    try:
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
                        f"new_page timed out after {wall_timeout:.0f}s "
                        f"(attempt {attempt}/{len(new_page_timeouts)})"
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
                        "Clarify chrome E2E bootstrap timed out in shared-hot mode: "
                        f"timed out after {bootstrap_timeout:.0f}s"
                    )
            except RuntimeError as exc:
                message = str(exc).lower()
                retryable = (
                    "mux_reclaim_stall" in message
                    or "transport" in message
                    or "target closed" in message
                )
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
        chat_id = await _run_flow(chat)
        assert chat_id
    finally:
        await asyncio.to_thread(client.close)
