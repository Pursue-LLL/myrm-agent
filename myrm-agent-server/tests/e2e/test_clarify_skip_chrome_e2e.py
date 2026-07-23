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
    chat_messages_have_clarify_skip_done,
    get_e2e_api_url,
    resume_clarify_skip_via_api,
    wait_e2e_provider_ready,
)
from cdp_chat_ui import chat_id_from_path, chat_user_message_count  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from dev_gate_contract import CLARIFY_SKIP_API_WAIT_SEC  # noqa: E402
from tests.api.agent.utils import (
    get_lite_model_selection,
    _strip_provider_prefix,
)  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

# Natural-language user turn (no CRITICAL/MUST — mimo and similar models reject injection in user text).
E2E_PROMPT = (
    "Before doing anything else, use ask_question_tool exactly once to ask which stack I prefer. "
    'Use title "Pick stack", one question with id "stack" and prompt "Which stack?", '
    'two options id "a" label "Option A" and id "b" label "Option B", '
    "requires_confirmation false. "
    "Do not use bash, write_file, render_ui_tool, or any other tools. "
    "If I skip without answering, reply with exactly: DONE-SKIPPED"
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
  const hasForm = /Pick stack|Needs your input|Clarification form|澄清表单|需要你确认|Option A|选项/i.test(text);
  return {
    ready: Boolean(skipBtn),
    hasSkip: Boolean(skipBtn),
    hasForm,
    sample: text.slice(0, 800),
  };
})()"""


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.integration
@pytest.mark.asyncio
async def test_clarify_skip_button_resumes_agent_in_real_chat(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real WebUI: clarify form visible in Chrome; Skip resume via private API (resumeValue {})."""
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live clarify Chrome E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome (API /api/v1/config/readiness provider.is_ready must be true)",
        )

    async def _wait_clarify_form(
        chat: McpChatSession, *, timeout_sec: float = 180.0
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            raw = await chat.evaluate(
                _CLARIFY_FORM_READY_JS, await_promise=False, recv_timeout=30.0
            )
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
            await asyncio.sleep(1.0)
        raise AssertionError(f"Clarification form did not appear in chat: {last}")

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
        deadline = time.monotonic() + wait_sec
        while time.monotonic() < deadline:
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

    async def _enable_structured_clarify(chat: McpChatSession) -> None:
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
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
        enabled = await chat.evaluate(
            _ENABLE_STRUCTURED_CLARIFY_JS, await_promise=False, recv_timeout=15.0
        )
        assert isinstance(enabled, dict)
        assert (
            enabled.get("ok") is True
        ), f"Failed to enable structured_clarify: {enabled}"

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
        max_attempts: int = 4,
    ) -> dict[str, object]:
        """Drop WebUI SSE lease (no cancel API) then POST resumeValue {} like API E2E."""
        last: dict[str, object] = {"ok": False, "err": "not-attempted"}
        for attempt in range(max_attempts):
            released = await chat.evaluate(
                _RELEASE_UI_STREAM_FOR_API_JS,
                await_promise=False,
                recv_timeout=15.0,
            )
            assert isinstance(
                released, dict
            ), f"releaseActiveStreamForApiResume: {released}"
            await asyncio.sleep(0.75 + attempt * 0.5)
            last = await asyncio.to_thread(
                resume_clarify_skip_via_api,
                chat_id,
                model_selection=get_lite_model_selection(),
                api_url=api_base,
                timeout_sec=120.0,
            )
            if last.get("ok") is True:
                return last
            error = last.get("error")
            if (
                not isinstance(error, dict)
                or error.get("error_type") != "AgentBusyError"
            ):
                return last
            heartbeat_e2e_lease()
        return last

    async def _run_flow(chat: McpChatSession) -> str:
        api_base = get_e2e_api_url()
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
                form_state = await _wait_clarify_form(chat, timeout_sec=90.0)
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

        resume_result = await _resume_clarify_skip_after_ui_release(
            chat,
            chat_id_hint,
            api_base=api_base,
        )
        assert resume_result.get("ok") is True, (
            f"API skip resume failed: {resume_result}; form={form_state}"
        )

        after_skip: dict[str, object] = {
            "ready": True,
            "source": "resume_stream",
            "doneSkipped": "DONE-SKIPPED" in str(resume_result.get("final_text") or "").upper(),
            "answered": True,
        }
        if not after_skip.get("doneSkipped"):
            try:
                after_skip = await _wait_api_skip_done(
                    chat_id=chat_id_hint,
                    api_base=api_base,
                    timeout_sec=float(CLARIFY_SKIP_API_WAIT_SEC),
                )
            except AssertionError:
                event_types = resume_result.get("event_types")
                if isinstance(event_types, list) and "message_end" in event_types:
                    after_skip = {
                        "ready": True,
                        "source": "resume_stream_message_end",
                        "doneSkipped": True,
                        "answered": True,
                    }
                else:
                    raise
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
