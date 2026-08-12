"""Chrome LIVE_AGENT E2E: RewindDialog rewinds a real conversation in the Web UI.

Real-user flow: send two turns, open the Rewind dialog on the SECOND user
message, choose "Conversation only", confirm, and verify the conversation is
truncated back to the first turn with the second message pre-filled in the
composer and the success toast shown.

The prompts only ask the model to reply with a fixed marker text — no tool
calls — so the test is stable across providers (unlike tool-call-based E2Es).
"""

from __future__ import annotations

import asyncio
import os
import sys
import time
import urllib.error
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    chat_user_message_count,
    e2e_runtime_bootstrap_apply_js,
    get_e2e_api_url,
    shpoib_parallel_shell_timeout_sec,
    signoff_parallel_force_chat_timeout_sec,
    wait_e2e_backend_ready,
    wait_e2e_provider_ready,
)
from cdp_chat_ui import chat_id_from_path  # noqa: E402
from dev_gate_contract import EvaluateIntent  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_mcp_e2e import open_mcp_page  # noqa: E402
from tests.support.e2e_lite_model_pin import pin_lite_model_for_e2e  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once  # noqa: E402

try:
    from e2e_session_runtime.lifecycle import touch_wall_progress
except ImportError:  # pragma: no cover - lib on PYTHONPATH in e2e only

    def touch_wall_progress(*, current_node: str | None = None) -> None:
        del current_node


def _touch_rewind_progress(node: str) -> None:
    touch_wall_progress(current_node=node)
    heartbeat_once()


BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

TURN_A = "Reply with the exact text: REWIND_MARKER_A"
TURN_B = "Reply with the exact text: REWIND_MARKER_B"

_OPEN_REWIND_JS = """(() => {
  const btns = Array.from(
    document.querySelectorAll(
      '[aria-label="Rewind to here"], [aria-label="回退到这里"]',
    ),
  );
  // Rewind the SECOND user message: rewinding "to here" removes that message
  // and everything after it, keeping the first turn. Real-user scenario.
  const btn = btns[1] || btns[0];
  if (!btn) {
    const labels = Array.from(document.querySelectorAll('[aria-label]')).map(
      (b) => b.getAttribute('aria-label'),
    );
    return {
      ok: false,
      err: 'no-rewind-button',
      count: btns.length,
      labels: labels.slice(0, 25),
      sample: (document.body.innerText || '').slice(0, 400),
    };
  }
  if (btn.disabled) return { ok: false, err: 'rewind-disabled', count: btns.length };
  btn.click();
  return { ok: true, count: btns.length };
})()"""

_DIALOG_READY_JS = """(() => {
  const dlg = document.querySelector('[role="dialog"]');
  const scopeBtns = Array.from(dlg?.querySelectorAll('button') || []).map(
    (b) => (b.textContent || '').trim(),
  );
  return {
    ready: !!dlg,
    scopeBtns,
    hasScopeBoth: scopeBtns.some(
      (t) => t.includes('Conversation and files') || t.includes('对话和文件'),
    ),
  };
})()"""

_SELECT_SCOPE_JS = """(() => {
  const dlg = document.querySelector('[role="dialog"]');
  if (!dlg) return { ok: false, err: 'no-dialog' };
  const btns = Array.from(dlg.querySelectorAll('button'));
  const target = btns.find(
    (b) =>
      (b.textContent || '').includes('Conversation only') ||
      (b.textContent || '').includes('仅对话'),
  );
  if (!target) return { ok: false, err: 'no-scope-btn', btns: btns.map((b) => (b.textContent || '').trim()) };
  target.click();
  return { ok: true };
})()"""

_CONFIRM_REWIND_JS = """(() => {
  const dlg = document.querySelector('[role="dialog"]');
  if (!dlg) return { ok: false, err: 'no-dialog' };
  const btns = Array.from(dlg.querySelectorAll('button'));
  const target = btns.find((b) => {
    const t = (b.textContent || '').trim();
    return t === 'Rewind' || t === '回退';
  });
  if (!target) return { ok: false, err: 'no-confirm-btn', btns: btns.map((b) => (b.textContent || '').trim()) };
  target.click();
  return { ok: true };
})()"""

_FINAL_STATE_JS = """(() => {
  const input = document.querySelector('[data-chat-input]');
  const value = input?.value || input?.textContent || '';
  const body = document.body.innerText || '';
  const bridge = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null;
  const dialog = document.querySelector('[role="dialog"]');
  const toasts = Array.from(
    document.querySelectorAll('[data-sonner-toast], [role="status"], [role="alert"]'),
  )
    .map((t) => (t.textContent || '').trim())
    .filter(Boolean);
  const rewoundBtns = Array.from(
    document.querySelectorAll('[aria-label="Rewind to here"], [aria-label="回退到这里"]'),
  );
  return {
    ok: value.includes('REWIND_MARKER_B'),
    composerValue: value.slice(0, 300),
    hasToast:
      body.includes('Conversation rewound') || body.includes('对话已回退'),
    storeUserCount: bridge?.userCount ?? null,
    storeIsStreaming: bridge?.isStreaming ?? null,
    storeChatId: bridge?.chatId ?? null,
    dialogOpen: !!dialog,
    rewoundBtns: rewoundBtns.length,
    toasts,
    path: location.pathname,
    sample: body.slice(0, 3000),
  };
})()"""


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_rewind_conversation_via_webui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for rewind Chrome E2E — run via "
            "./myrm test -m chrome_e2e after ./myrm ready --chrome",
        )

    api_base = get_e2e_api_url()

    async def _apply_bootstrap(chat: McpChatSession) -> None:
        bootstrap_js = e2e_runtime_bootstrap_apply_js()
        if not bootstrap_js:
            await chat.ensure_e2e_api_base_binding()
            return
        result = await chat.evaluate(bootstrap_js, intent=EvaluateIntent.AGENT_SUBMIT)
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError(f"E2E runtime bootstrap failed: {result}")

    async def _wait_api_user_messages(
        chat_id: str,
        expected: int,
        *,
        timeout_sec: float,
        mode: str = "at_least",
    ) -> None:
        deadline = time.monotonic() + timeout_sec
        last = 0
        seen: list[int] = []
        while time.monotonic() < deadline:
            _touch_rewind_progress("rewind_wait_api_messages")
            try:
                last = chat_user_message_count(chat_id, api_url=api_base)
                seen.append(last)
                if mode == "exact" and last == expected:
                    return
                if mode == "at_least" and last >= expected:
                    return
            except (OSError, TimeoutError, urllib.error.URLError):
                wait_e2e_backend_ready(timeout_sec=15.0, api_url=api_base)
            await asyncio.sleep(1.0)
        raise AssertionError(
            f"Backend user messages did not reach {expected} (mode={mode}) "
            f"within {timeout_sec}s (last={last}, seen={seen[-12:]})"
        )

    async def _wait_store_user_count(
        chat: McpChatSession, expected: int, *, timeout_sec: float
    ) -> None:
        """Poll the frontend store (via E2E bridge) for the expected user count.

        Unlike the backend API poll, this reflects what the UI actually renders,
        which is what a rewind confirm must update.
        """
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            _touch_rewind_progress("rewind_wait_store_user_count")
            probe = await chat.evaluate(
                """(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? { err: 'no-bridge' })()""",
                intent=EvaluateIntent.BRIDGE_POLL,
            )
            if isinstance(probe, dict):
                last = probe
                if probe.get("userCount") == expected:
                    return
            await asyncio.sleep(1.0)
        raise TimeoutError(
            f"Store user count did not reach {expected} before/after rewind: {last}"
        )

    async def _wait_not_streaming(chat: McpChatSession, *, timeout_sec: float) -> None:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            _touch_rewind_progress("rewind_wait_not_streaming")
            probe = await chat.evaluate(
                """(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? { err: 'no-bridge' })()""",
                intent=EvaluateIntent.BRIDGE_POLL,
            )
            if isinstance(probe, dict):
                last = probe
                if probe.get("isStreaming") is False:
                    return
            await asyncio.sleep(1.0)
        raise TimeoutError(f"Chat still streaming before rewind: {last}")

    async def _wait_js(
        chat: McpChatSession, js: str, *, timeout_sec: float, error_label: str
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            _touch_rewind_progress("rewind_wait_js")
            raw = await chat.evaluate(js, intent=EvaluateIntent.BRIDGE_POLL)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True or last.get("ok") is True:
                return last
            await asyncio.sleep(1.0)
        raise AssertionError(f"{error_label}: {last}")

    async def _clear_composer(chat: McpChatSession, *, timeout_sec: float) -> None:
        """Empty the composer before opening the Rewind dialog.

        Under E2E send races the composer can retain the last sent text; clearing
        it first means the post-rewind prefill check reflects the rewind seed
        (the deleted message's text) rather than a leftover value.
        """
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            _touch_rewind_progress("rewind_clear_composer")
            result = await chat.evaluate(
                """(() => {
                  window.__MYRM_E2E_CHAT__?.setInputMessage?.('');
                  const input = document.querySelector('[data-chat-input]');
                  if (input && input.value) {
                    const proto = Object.getPrototypeOf(input);
                    const setter = Object.getOwnPropertyDescriptor(proto, 'value')?.set;
                    if (setter) setter.call(input, '');
                    input.dispatchEvent(new Event('input', { bubbles: true }));
                  }
                  const len = document.querySelector('[data-chat-input]')?.value?.length ?? 0;
                  return { ok: len === 0, inputLen: len };
                })()""",
                intent=EvaluateIntent.BRIDGE_POLL,
            )
            last = result if isinstance(result, dict) else {"value": result}
            if last.get("ok") is True:
                return
            await asyncio.sleep(1.0)
        raise AssertionError(f"Composer did not clear before rewind: {last}")

    async def _run_flow(chat: McpChatSession) -> str:
        await chat.dismiss_modals()
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL)
        await _apply_bootstrap(chat)
        await pin_lite_model_for_e2e(chat)

        send = await chat.send_message(TURN_A, TURN_A)
        _touch_rewind_progress("rewind_post_send_turn_a")
        chat_id_hint = str(
            send.get("started", {}).get("chatId")
            or send.get("submit", {}).get("chatId")
            or ""
        ).strip()
        if not chat_id_hint:
            chat_id_hint = str((await chat.bridge_chat_id()) or "").strip() or None

        started = await chat.wait_stream_started(
            TURN_A, timeout_sec=120.0, chat_id_hint=chat_id_hint
        )
        chat_id = chat_id_hint or str(started.get("chatId") or "").strip() or None
        if not chat_id:
            after_start = await chat.main_state(
                TURN_A, intent=EvaluateIntent.BRIDGE_POLL
            )
            chat_id = (
                chat_id_from_path(str(after_start.get("path") or ""))
                or str(after_start.get("bridgeChatId") or "").strip()
                or None
            )
        assert chat_id, f"Expected chat id after turn A: started={started}; send={send}"
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
        await chat._attach_chat_session(chat_id)
        await _wait_not_streaming(chat, timeout_sec=90.0)
        await _wait_api_user_messages(chat_id, 1, timeout_sec=90.0)

        await chat.send_message(TURN_B, TURN_B, chat_id_hint=chat_id, base_url=BASE_URL)
        _touch_rewind_progress("rewind_post_send_turn_b")
        await chat.wait_stream_started(
            TURN_B, timeout_sec=120.0, chat_id_hint=chat_id
        )
        await _wait_not_streaming(chat, timeout_sec=90.0)
        await _wait_api_user_messages(chat_id, 2, timeout_sec=90.0)

        # Rewind must prefill the composer with the rewinded message's text;
        # make sure the composer is empty first (E2E send races can leave the
        # last sent text behind, which would make the prefill check vacuous).
        await _clear_composer(chat, timeout_sec=30.0)

        _touch_rewind_progress("rewind_open_dialog")
        opened = await chat.evaluate(_OPEN_REWIND_JS, intent=EvaluateIntent.AGENT_SUBMIT)
        assert isinstance(opened, dict) and opened.get("ok") is True, f"Open rewind failed: {opened}"

        dialog = await _wait_js(
            chat, _DIALOG_READY_JS, timeout_sec=30.0, error_label="rewind dialog did not open"
        )
        assert dialog.get("hasScopeBoth") is True, f"Unexpected scope options: {dialog}"

        scoped = await chat.evaluate(_SELECT_SCOPE_JS, intent=EvaluateIntent.AGENT_SUBMIT)
        assert isinstance(scoped, dict) and scoped.get("ok") is True, f"Scope select failed: {scoped}"

        confirmed = await chat.evaluate(_CONFIRM_REWIND_JS, intent=EvaluateIntent.AGENT_SUBMIT)
        assert isinstance(confirmed, dict) and confirmed.get("ok") is True, f"Confirm failed: {confirmed}"

        _touch_rewind_progress("rewind_post_confirm")
        # Snapshot right after confirm: if the rewind did not take effect
        # (dialog still open, store unchanged, failure toast) fail fast with
        # the diagnostic instead of waiting out the 60s poll below.
        await asyncio.sleep(3.0)
        diag = await chat.evaluate(_FINAL_STATE_JS, intent=EvaluateIntent.BRIDGE_POLL)
        if not isinstance(diag, dict):
            raise AssertionError(f"Post-confirm diagnostic failed: {diag}")
        if diag.get("dialogOpen") is True or diag.get("storeUserCount") != 1:
            raise AssertionError(f"Rewind did not take effect after confirm: {diag}")

        # Rewind must (a) truncate the backend to a single user message AND
        # (b) update the frontend store that the UI actually renders.
        await _wait_api_user_messages(chat_id, 1, timeout_sec=60.0, mode="exact")
        await _wait_store_user_count(chat, 1, timeout_sec=60.0)

        final = await _wait_js(
            chat,
            _FINAL_STATE_JS,
            timeout_sec=60.0,
            error_label="rewind final state not reached",
        )
        assert final.get("ok") is True, f"Composer not pre-filled: {final}"
        assert final.get("hasToast") is True, f"Success toast missing: {final}"

        e2e_resource_ledger.register("chat", chat_id)
        return chat_id

    with open_mcp_page(BASE_URL, timeout_ms=90_000) as (client, page):
        chat = McpChatSession(client, page)
        bootstrap_timeout = signoff_parallel_force_chat_timeout_sec(
            shpoib_parallel_shell_timeout_sec(240.0)
        )
        await chat.bootstrap(BASE_URL, timeout_sec=bootstrap_timeout)
        chat_id = await _run_flow(chat)
        assert chat_id
