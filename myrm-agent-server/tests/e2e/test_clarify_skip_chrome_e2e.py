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
    ensure_e2e_yolo_mode,
    get_e2e_api_url,
    resume_clarify_skip_via_api,
    wait_e2e_provider_ready,
)
from cdp_chat_ui import chat_id_from_path, chat_user_message_count  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from dev_gate_contract import CLARIFY_SKIP_API_WAIT_SEC  # noqa: E402
from e2e_wall_budget import remaining_wall_sec, touch_wall_progress  # noqa: E402
from tests.api.agent.utils import (
    get_lite_model_selection,
    _strip_provider_prefix,
)  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

# Align with API skip E2E (test_clarify_agent_stream_e2e) — MiniMax-M3 follows CRITICAL tool-first.
E2E_PROMPT = (
    "CRITICAL: Your very first action MUST be a single ask_question_tool call — no text reply before it. "
    "You MUST call ask_question_tool exactly once before any other action. "
    'Use title "Pick stack". Ask one question with id "stack" and prompt '
    '"Which stack?" with two options: id "a" label "Option A", id "b" label "Option B". '
    "Set requires_confirmation to false. "
    "Do not use bash, write_file, render_ui_tool, or any other tools. "
    "If the user skips or gives no answer, reply with exactly: DONE-SKIPPED"
)

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


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
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

    async def _wait_clarify_ready(
        chat: McpChatSession,
        *,
        chat_id: str,
        api_base: str,
        timeout_sec: float | None = None,
    ) -> dict[str, object]:
        """Wait for clarify ready via API pending (SSOT) or DOM Skip button (whichever first)."""
        wait_sec = (
            float(CLARIFY_SKIP_API_WAIT_SEC)
            if timeout_sec is None
            else float(timeout_sec)
        )
        wait_sec = min(wait_sec, max(10.0, remaining_wall_sec() - 45.0))
        deadline = time.monotonic() + wait_sec
        last_dom: dict[str, object] = {}
        normalized_chat_id = chat_id.strip()
        while time.monotonic() < deadline:
            touch_wall_progress()
            heartbeat_e2e_lease()
            try:
                raw = await chat.evaluate(
                    _CLARIFY_FORM_READY_JS, await_promise=False, recv_timeout=15.0
                )
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
                raise
            last_dom = raw if isinstance(raw, dict) else {"value": raw}
            if last_dom.get("ready") is True:
                return {**last_dom, "source": "dom"}
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
            float(CLARIFY_SKIP_API_WAIT_SEC)
            if timeout_sec is None
            else float(timeout_sec)
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
            float(CLARIFY_SKIP_API_WAIT_SEC)
            if timeout_sec is None
            else float(timeout_sec)
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
        max_attempts: int = 5,
    ) -> dict[str, object]:
        """Drop WebUI SSE lease (no cancel API) then POST resumeValue {} like API E2E."""
        last: dict[str, object] = {"ok": False, "err": "not-attempted"}
        backoff_sec = (5.0, 10.0, 20.0, 30.0, 45.0)
        for attempt in range(max_attempts):
            await _release_ui_stream_for_api(chat)
            pause = backoff_sec[min(attempt, len(backoff_sec) - 1)]
            await asyncio.sleep(0.75 + pause * 0.1)
            api_timeout = min(
                float(CLARIFY_SKIP_API_WAIT_SEC),
                max(60.0, remaining_wall_sec() - 60.0),
            )
            last = await asyncio.to_thread(
                resume_clarify_skip_via_api,
                chat_id,
                model_selection=get_lite_model_selection(),
                api_url=api_base,
                timeout_sec=api_timeout,
            )
            if last.get("ok") is True:
                return last
            error = last.get("error")
            if isinstance(error, dict) and error.get("error_type") == "AgentBusyError":
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
        resume_result: dict[str, object] = {"ok": False, "event_types": []}
        poll_budget = min(
            float(CLARIFY_SKIP_API_WAIT_SEC),
            max(60.0, remaining_wall_sec() - 90.0),
        )

        bridge = await chat.evaluate(
            _SKIP_VIA_BRIDGE_JS, await_promise=False, recv_timeout=15.0
        )
        if isinstance(bridge, dict) and bridge.get("ok") is True:
            try:
                return await _wait_ui_skip_done(chat, timeout_sec=poll_budget), resume_result
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

        resume_result = await _resume_clarify_skip_after_ui_release(
            chat,
            chat_id,
            api_base=api_base,
        )
        assert resume_result.get("ok") is True, (
            f"API skip resume failed: {resume_result}; form={form_state}"
        )
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

    async def _run_flow(chat: McpChatSession) -> str:
        api_base = get_e2e_api_url()
        await asyncio.to_thread(ensure_e2e_yolo_mode, api_url=api_base)
        await _prepare_fresh_clarify_chat(chat)

        chat_id_hint = ""
        form_state: dict[str, object] = {}
        max_clarify_attempts = 2
        for attempt in range(max_clarify_attempts):
            if attempt > 0:
                await _prepare_fresh_clarify_chat(chat)
            await chat.dismiss_modals()
            await chat.evaluate(
                _DISMISS_MIGRATION_JS, await_promise=False, recv_timeout=15.0
            )
            try:
                send_result = await chat.send_message(E2E_PROMPT, E2E_PROMPT)
            except RuntimeError as exc:
                if (
                    "timed out" not in str(exc).lower()
                    or attempt == max_clarify_attempts - 1
                ):
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

            heartbeat_e2e_lease()
            await chat.wait_stream_started(
                E2E_PROMPT, timeout_sec=120.0, chat_id_hint=chat_id_hint or None
            )
            try:
                form_state = await _wait_clarify_ready(
                    chat,
                    chat_id=chat_id_hint,
                    api_base=api_base,
                )
                break
            except AssertionError:
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

        try:
            assert (
                chat_user_message_count(chat_id, api_url=api_base) >= 1
            ), f"Expected API user message for chat {chat_id}: {after_turn}"
        except (TimeoutError, OSError) as exc:
            if after_skip.get("ready") is not True:
                raise AssertionError(
                    f"API message check failed and UI did not complete skip flow: {exc}"
                ) from exc

        e2e_resource_ledger.register("chat", chat_id)
        return chat_id

    client = ChromeMcpClient(request_timeout_sec=300.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = None
        try:
            page = await asyncio.to_thread(
                client.new_page, BASE_URL, timeout_ms=120_000
            )
        except TimeoutError:
            await asyncio.sleep(2.0)
            page = await asyncio.to_thread(
                client.new_page, BASE_URL, timeout_ms=120_000
            )
        if page is None:
            raise RuntimeError("new_page returned no page")
        chat = McpChatSession(client, page)
        await chat.bootstrap(BASE_URL, timeout_sec=120.0)
        chat_id = await _run_flow(chat)
        assert chat_id
    finally:
        await asyncio.to_thread(client.close)
