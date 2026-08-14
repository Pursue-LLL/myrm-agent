"""Chrome LIVE_AGENT E2E: inspector panel lifecycle through real frontend SSE handlers.

Covers the real end-to-end path of the turn-engagement teardown state machine:

1. `simulateBrowserToolStart` + `simulateBrowserViewUpdate` dispatch real SSE handler
   events (TOOL_START / BROWSER_VIEW_UPDATE) through the production frontend
   handlers, which engage the turn, open the browser inspector panel, set
   isBrowserActive and store the scoped view data (sourceChatId bound).
2. A real LLM turn is then sent; its MESSAGE_END terminal event triggers
   `releaseTurnInspectorControls(chatId)` → `releaseTurnEngagement(chatId)`,
   which reclaims the view data owned by this turn even though no real browser
   session was used.
3. A manually opened desktop panel (ensureComputerUseReady, no engagement) must
   survive the same turn end, proving unrelated panels are never force-closed.

The bridge's simulate helpers only inject SSE payloads into the production
handlers (fileDiffEvents / toolLifecycleEvents / completionEvents); they bypass
the LLM/backend only for the view-data fabrication step, keeping every assertion
on the real frontend store and DOM state.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import (  # noqa: E402
    e2e_runtime_bootstrap_apply_js,
    ensure_e2e_yolo_mode,
    get_e2e_api_url,
    get_e2e_ui_url,
    wait_e2e_provider_ready,
)
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.support.chrome_mcp_e2e import (  # noqa: E402
    http_json,
    open_mcp_page,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once  # noqa: E402

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
_MAX_CHAT_ATTEMPTS = 3

_REPLY_OK_PROMPT = "Reply with the single word OK. Do not call any tools."

_AGENT_READY_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const debug = bridge?.debugProviderState?.() ?? {};
  return {
    ready: !!bridge?.handleSubmit && !!debug.selection,
    selection: debug.selection ?? null,
  };
})()"""

_PIN_MODEL_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.pinLiteModelForE2e) {
    return { ok: false, err: 'no-pinLiteModelForE2e' };
  }
  return bridge.pinLiteModelForE2e().then((pinned) => ({ ok: true, pinned }));
})()"""

_ENSURE_CHAT_SESSION_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.ensureChatSession) return { ok: false, err: 'no ensureChatSession' };
  return bridge.ensureChatSession().then(() => ({ ok: true }));
})()"""

_SIMULATE_BROWSER_CONTROL_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.simulateBrowserToolStart || !bridge?.simulateBrowserViewUpdate) {
    return { ok: false, err: 'no-browser-simulate' };
  }
  const chatId = bridge?.turnSnapshot?.()?.chatId ?? '';
  if (!chatId) return { ok: false, err: 'no-chat-id' };
  return (async () => {
    const start = await bridge.simulateBrowserToolStart(chatId, 'browser_navigate_tool');
    const view = await bridge.simulateBrowserViewUpdate(chatId);
    return { ok: start?.ok === true && view?.ok === true, chatId };
  })();
})()"""

_BROWSER_ACTIVE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.getBrowserInspectorSnapshot?.() ?? null;
  return {
    ready: !!snap && snap.isOpen === true && snap.isBrowserActive === true && snap.hasScreenshot === true,
    snap,
  };
})()"""

_ENSURE_COMPUTER_USE_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.ensureComputerUseReady) return { ok: false, err: 'no ensureComputerUseReady' };
  bridge.ensureComputerUseReady();
  return { ok: true };
})()"""

_DESKTOP_OPEN_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.getDesktopInspectorSnapshot?.() ?? null;
  return { ready: !!snap && snap.isOpen === true && snap.isDesktopActive === false, snap };
})()"""

_TURN_DONE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const text = String(snap.lastAssistantSample || '');
  return {
    chatId: snap.chatId,
    isStreaming: Boolean(snap.isStreaming),
    userCount: snap.userCount ?? 0,
    hasDone: /\\bOK\\b/i.test(text),
    sample: text.slice(0, 600),
  };
})()"""

_BROWSER_RELEASED_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.getBrowserInspectorSnapshot?.() ?? null;
  return {
    ready:
      !!snap &&
      snap.isBrowserActive === false &&
      snap.isOpen === false &&
      snap.hasScreenshot === false &&
      snap.sourceChatId === '',
    snap,
  };
})()"""

_DESKTOP_PRESERVED_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.getDesktopInspectorSnapshot?.() ?? null;
  return { ready: !!snap && snap.isOpen === true, snap };
})()"""


def _create_inspector_live_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Inspector lifecycle LIVE {suffix}",
        "description": "Chrome LIVE E2E for inspector panel teardown state machine",
        "system_prompt": (
            "You answer short factual replies. When the user asks you to reply with a single "
            "word, reply with exactly that word and call no tools."
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "enabled_builtin_tools": [],
        "security_overrides": {
            "yoloModeEnabled": True,
            "yolo_mode_enabled_at": time.time(),
        },
    }
    created = http_json("POST", f"{api_url}/api/v1/user-agents", payload)
    assert isinstance(created, dict)
    agent_id = (
        created.get("data", {}).get("id")
        if isinstance(created.get("data"), dict)
        else created.get("id")
    )
    assert isinstance(agent_id, str) and agent_id
    return agent_id


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_inspector_panel_lifecycle_turn_end_releases_engaged_view(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live inspector E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome"
        )

    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url()
    ensure_e2e_yolo_mode(api_url=api_base)
    agent_id = _create_inspector_live_agent(api_base)
    e2e_resource_ledger.register("agent", agent_id)

    async def _wait_agent_applied(chat: McpChatSession, *, timeout_sec: float = 90.0) -> None:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            raw = await chat.evaluate(_AGENT_READY_JS, intent=EvaluateIntent.BRIDGE_POLL)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return
            await asyncio.sleep(1.0)
        raise AssertionError(f"E2E chat bridge not ready after loading agent: {last}")

    async def _wait_browser_engaged(chat: McpChatSession, *, timeout_sec: float = 60.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            raw = await chat.evaluate(_BROWSER_ACTIVE_JS, intent=EvaluateIntent.BRIDGE_POLL)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
            await asyncio.sleep(0.5)
        raise AssertionError(f"Browser inspector panel did not engage: {json.dumps(last, ensure_ascii=False)}")

    async def _wait_desktop_open(chat: McpChatSession, *, timeout_sec: float = 30.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            raw = await chat.evaluate(_DESKTOP_OPEN_JS, intent=EvaluateIntent.BRIDGE_POLL)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
            await asyncio.sleep(0.5)
        raise AssertionError(f"Desktop panel did not open manually: {json.dumps(last, ensure_ascii=False)}")

    async def _wait_turn_done(chat: McpChatSession, *, timeout_sec: float = 300.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            raw = await chat.evaluate(_TURN_DONE_JS, intent=EvaluateIntent.BRIDGE_POLL)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if (
                last.get("hasDone") is True
                and last.get("isStreaming") is False
                and int(last.get("userCount") or 0) >= 1
            ):
                return last
            await asyncio.sleep(1.5)
        raise AssertionError(f"Live OK turn did not complete: {json.dumps(last, ensure_ascii=False)}")

    async def _wait_browser_released(chat: McpChatSession, *, timeout_sec: float = 60.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            raw = await chat.evaluate(_BROWSER_RELEASED_JS, intent=EvaluateIntent.BRIDGE_POLL)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
            await asyncio.sleep(0.5)
        raise AssertionError(
            f"Browser inspector was not released on turn end: {json.dumps(last, ensure_ascii=False)}"
        )

    async def _wait_desktop_preserved(chat: McpChatSession, *, timeout_sec: float = 30.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            raw = await chat.evaluate(_DESKTOP_PRESERVED_JS, intent=EvaluateIntent.BRIDGE_POLL)
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
            await asyncio.sleep(0.5)
        raise AssertionError(
            f"Manually opened desktop panel was force-closed: {json.dumps(last, ensure_ascii=False)}"
        )

    async def _run_flow(chat: McpChatSession) -> str:
        await chat.dismiss_modals()
        await _wait_agent_applied(chat)

        pinned = await chat.evaluate(_PIN_MODEL_JS, intent=EvaluateIntent.AGENT_SUBMIT)
        assert isinstance(pinned, dict) and pinned.get("ok") is True, pinned
        assert isinstance(pinned.get("pinned"), dict), pinned

        ensured = await chat.evaluate(_ENSURE_CHAT_SESSION_JS, intent=EvaluateIntent.ROUTE_ATTACH)
        assert isinstance(ensured, dict) and ensured.get("ok") is True, ensured

        chat_id = str((await chat.bridge_chat_id()) or "").strip()
        assert chat_id, "Expected client chat id after ensureChatSession"

        # --- Phase 1: real frontend handlers engage the browser inspector panel ---
        simulated = await chat.evaluate(
            _SIMULATE_BROWSER_CONTROL_JS, intent=EvaluateIntent.AGENT_SUBMIT
        )
        assert isinstance(simulated, dict) and simulated.get("ok") is True, simulated

        engaged = await _wait_browser_engaged(chat)
        assert engaged.get("ready") is True, engaged

        # --- Phase 2: manually opened desktop panel (no engagement) ---
        computer_use = await chat.evaluate(_ENSURE_COMPUTER_USE_JS, intent=EvaluateIntent.AGENT_SUBMIT)
        assert isinstance(computer_use, dict) and computer_use.get("ok") is True, computer_use
        desktop = await _wait_desktop_open(chat)
        assert desktop.get("ready") is True, desktop

        # --- Phase 3: real LLM turn ends; MESSAGE_END must release the engaged browser view ---
        send_result = await chat.send_message(_REPLY_OK_PROMPT, _REPLY_OK_PROMPT)
        chat_id_hint = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or chat_id
        ).strip()
        started = await chat.wait_stream_started(
            _REPLY_OK_PROMPT, timeout_sec=120.0, chat_id_hint=chat_id_hint or None
        )
        resolved_chat_id = chat_id_hint or str(started.get("chatId") or "").strip()
        assert resolved_chat_id, f"Expected chat id after stream start: started={started}; send={send_result}"

        done = await _wait_turn_done(chat, timeout_sec=300.0)
        assert done.get("hasDone") is True, done

        released = await _wait_browser_released(chat)
        assert released.get("ready") is True, released

        preserved = await _wait_desktop_preserved(chat)
        assert preserved.get("ready") is True, preserved

        e2e_resource_ledger.register("chat", resolved_chat_id)
        return resolved_chat_id

    async def _apply_bootstrap(chat: McpChatSession) -> None:
        bootstrap_js = e2e_runtime_bootstrap_apply_js()
        if not bootstrap_js:
            await chat.ensure_e2e_api_base_binding()
            return
        result = await chat.evaluate(bootstrap_js, intent=EvaluateIntent.AGENT_SUBMIT)
        if not isinstance(result, dict) or result.get("ok") is not True:
            raise RuntimeError(f"E2E runtime bootstrap failed: {result}")

    last_error = ""
    agent_url = f"{ui_base}/?agentId={agent_id}"
    for attempt in range(_MAX_CHAT_ATTEMPTS):
        heartbeat_once()
        try:
            with open_mcp_page(agent_url, timeout_ms=120_000) as (client, page):
                chat = McpChatSession(client, page)
                await chat.bootstrap(agent_url, timeout_sec=180.0)
                await _apply_bootstrap(chat)
                resolved_chat_id = await _run_flow(chat)
            assert resolved_chat_id
            break
        except (AssertionError, RuntimeError, TimeoutError) as exc:
            last_error = str(exc)
            if attempt >= _MAX_CHAT_ATTEMPTS - 1:
                raise
            await asyncio.sleep(2.0)
    else:
        pytest.fail(last_error or "inspector lifecycle WebUI flow failed")
