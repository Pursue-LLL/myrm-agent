"""Chrome E2E: Tool-Call Instruction Lineage + 步骤级安全标签传播 (roadmap item#2).

Prerequisites:
  ./myrm ready --chrome
  WebUI default model configured (E2E Chrome profile DB)

Covers item#2 front-end chain end to end with a real LLM turn that invokes a
shell tool through the UI:

  T1 - A real chat turn triggers a shell tool call through the composer and completes.
  T2 - The execution-trace API returns tool_calls carrying the lineage identifiers
       (tool_call_id / message_id) that the harness now persists, plus the
       security_labels array when the session audit recorded decisions.
  T3 - The performance-diagnostics dialog renders the execution trace and the
       shell tool-call card.
  T4 - "Enter Replay" switches to the replay player; scrubbing to the end shows
       the tool chip attributed to the turn and the inspector renders tool detail.

Security-badge rendering itself (DENY/tainted styling) is covered by the
frontend unit tests; this test proves the real end-to-end lineage data path.
"""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.mcp_ui import McpChatSession  # noqa: E402
from cdp_chat.support import get_e2e_api_url, wait_e2e_provider_ready  # noqa: E402
from cdp_chat.ui import chat_id_from_path, chat_user_message_count  # noqa: E402
from chrome_mcp.client import ChromeMcpClient, McpPage  # noqa: E402
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.support.chrome_mcp_e2e import http_json
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

E2E_PROMPT = (
    "【E2E 血缘测试】只使用终端/命令执行工具（bash tool）执行 pwd 命令，"
    "你必须实际调用该工具获取当前工作目录，禁止跳过工具直接回答。"
    "调用完成后回答必须以 OK 开头，然后原样复述 pwd 的输出路径。"
)
# Real LLM turns are non-deterministic about invoking a tool; budget retries so a
# turn that only talks still yields the lineage data path in a later attempt.
MAX_TURNS = 3

# ── UI probe snippets ─────────────────────────────────────────────────────────

# Clicks the assistant message "performance diagnostics" button (any locale).
# On failure dumps the page URL, message-region state and full aria-label list so
# a not-yet-hydrated message list is distinguishable from a genuinely missing button.
_OPEN_DIAGNOSTICS_JS = """(() => {
  const candidates = Array.from(document.querySelectorAll('button[aria-label]'));
  const btn = candidates.find((b) =>
    /性能诊断|性能診斷|Performance Diagnostics|Diagnostics/i.test(
      b.getAttribute('aria-label') || '',
    ),
  );
  if (!btn) {
    const bodyText = document.body?.innerText || '';
    const hasMsgRegion = /搜索对话|新对话|发送|Send/.test(bodyText);
    const hasAssistantBlock = /助手|assistant|Assistant/.test(bodyText);
    return {
      ready: false,
      reason: 'no-diagnostics-button',
      path: location.pathname,
      hasMsgRegion,
      hasAssistantBlock,
      hasLoading: /加载中|Loading|加载/.test(bodyText),
      bodySnip: bodyText.slice(0, 150),
      ariaLabels: candidates.slice(0, 40).map((b) => b.getAttribute('aria-label')),
    };
  }
  btn.click();
  return { ready: true };
})()"""

# Waits for the session-analytics dialog with the execution trace section, and
# reports the shell tool-call card (matched by the injected tool name).
def _trace_dialog_probe_js(tool_names: list[str]) -> str:
    names_js = json.dumps(tool_names)
    return f"""(() => {{
      const dialogs = Array.from(document.querySelectorAll('.fixed.inset-0'));
      const dialog = dialogs.find((d) =>
        /执行回放|執行回放|Execution Trace|Execution Replay|执行轨迹/.test(d.innerText || ''),
      );
      if (!dialog) return {{ ready: false, reason: 'no-trace-dialog' }};
      const text = dialog.innerText || '';
      const names = {names_js};
      const visible = names.filter((n) => n && text.includes(n));
      const toolRows = Array.from(dialog.querySelectorAll('button')).filter((b) =>
        names.some((n) => n && (b.textContent || '').includes(n)),
      );
      return {{
        ready: visible.length > 0,
        visible,
        toolRows: toolRows.length,
        hasEnterReplay: /播放录像|播放錄像|Enter Replay|进入回放|進入回放/.test(text),
        textSnippet: text.slice(0, 300),
      }};
    }})()"""

# Clicks the "Enter Replay" button inside the trace dialog (any locale).
# Reports the exact button text that was clicked so a wrong-target click is visible.
# On failure it dumps the dialog inventory + button list + page error state so a
# disappearing Enter-Replay button (dialog closed / page crashed / trace loading)
# is diagnosable instead of an opaque timeout.
_ENTER_REPLAY_JS = """(() => {
  const dialogs = Array.from(document.querySelectorAll('.fixed.inset-0'));
  const dialog = dialogs.find((d) =>
    /执行回放|執行回放|Execution Trace|Execution Replay|执行轨迹/.test(d.innerText || ''),
  );
  const scope = dialog || document.body;
  const btn = Array.from(scope.querySelectorAll('button')).find((b) =>
    /播放录像|播放錄像|Enter Replay|进入回放|進入回放/.test((b.textContent || '').trim()),
  );
  if (!btn) {
    const bodyText = document.body?.innerText || '';
    return {
      ready: false,
      reason: 'no-replay-button',
      hasDialog: Boolean(dialog),
      dialogCount: dialogs.length,
      dialogText: dialogs
        .map((d) => (d.innerText || '').slice(0, 150))
        .slice(0, 3),
      buttons: Array.from(scope.querySelectorAll('button'))
        .map((b) => (b.textContent || '').trim().slice(0, 40))
        .slice(0, 25),
      hasLoadingText: /加载中|Loading|加载/.test(bodyText),
      bodyErr: /应用出错了/.test(bodyText),
      bodyText: bodyText.slice(0, 200),
    };
  }
  btn.click();
  return {
    ready: true,
    clickedText: (btn.textContent || '').trim().slice(0, 60),
    inDialog: Boolean(dialog),
  };
})()"""

# Probes the replay player: drags the scrubber to the end, then reports the tool
# chips visible in the "mind view" column plus whether the inspector painted.
# Mind/chat/inspector labels differ per locale ("Mind Window" / "UI State" in en,
# "脑电波" / "界面" in zh), so the regexes accept every shipped translation.
_REPLAY_END_STATE_JS = """(() => {
  const root = document.querySelector('[role="application"]');
  if (!root) {
    const dialogs = Array.from(document.querySelectorAll('.fixed.inset-0'));
    const bodyText = document.body?.innerText || '';
    // Track whether the E2E fetch router's readiness promise is settled. If the
    // private backend half-dies (accepts TCP but never answers), the proxy keeps
    // every /api/v1 fetch pending forever and the replay player's message load
    // never settles -> no [role="application"]. Sampling the marker across the
    // probe loop tells "pending" (half-dead backend) from "rejected" (backend
    // down) from "resolved" (backend fine, so the issue is elsewhere).
    const rp = window.__MYRM_E2E_RUNTIME_READY__;
    if (rp && !window.__E2E_RP_MARK__) {
      window.__E2E_RP_MARK__ = 'pending';
      rp.then(
        () => { window.__E2E_RP_MARK__ = 'resolved'; },
        () => { window.__E2E_RP_MARK__ = 'rejected'; },
      );
    }
    // Decide whether the trace dialog actually switched into replay mode: if it
    // still shows the Enter Replay button and no Session Replay title, the click
    // never flipped replayMode (wrong button target / state not committed).
    const traceDialog = dialogs.find((d) =>
      /Execution Replay|执行回放|執行回放|Execution Trace|执行轨迹/.test(d.innerText || ''),
    );
    const traceText = traceDialog ? traceDialog.innerText : '';
    return {
      ready: false,
      reason: 'no-replay-root',
      dialogCount: dialogs.length,
      dialogText: dialogs
        .map((d) => (d.innerText || '').slice(0, 120))
        .slice(0, 3),
      traceDialogFound: Boolean(traceDialog),
      traceDialogStillHasEnterReplay: /Enter Replay|播放录像|播放錄像|进入回放|進入回放/.test(traceText),
      traceDialogHasReplayTitle: /Session Replay|录像回放|錄像回放/.test(traceText),
      traceDialogText: traceText.slice(0, 600),
      hasLoadingText: /加载中|Loading|加载/.test(bodyText),
      bodyErr: /应用出错了|Application error|page error/i.test(bodyText),
      runtimeReady: window.__E2E_RP_MARK__ || (rp ? 'probing' : 'absent'),
      apiBase: String(window.__MYRM_E2E_API_BASE__ || ''),
      readyState: document.readyState,
      bodyText: bodyText.slice(0, 250),
    };
  }
  const text = root.innerText || '';
  if (!/录像回放|Session Replay|Replay|回放/.test(text)) {
    return { ready: false, reason: 'no-replay-title', text: text.slice(0, 200) };
  }
  // BRIDGE_POLL evaluates synchronously (no awaitPromise), so this probe must
  // never return a Promise. Scrub once on the first poll, then let _wait_ui_state
  // re-poll after React has flushed the scrubbed frame.
  const range = root.querySelector('input[type="range"]');
  if (range && !window.__MYRM_SCRUBBED__) {
    window.__MYRM_SCRUBBED__ = true;
    const setter = Object.getOwnPropertyDescriptor(Object.getPrototypeOf(range), 'value');
    setter.set.call(range, String(range.max));
    range.dispatchEvent(new Event('input', { bubbles: true }));
    range.dispatchEvent(new MouseEvent('mouseup', { bubbles: true }));
    return { ready: false, reason: 'scrubbing' };
  }
  const text2 = root.innerText || '';
  const hasMindView = /脑电波|Mind View|Mind Window|Brain/.test(text2);
  const hasChatView = /界面|Chat View|UI State|Chat/.test(text2);
  const hasInspector = /原始参数|Inspector/.test(text2);
  const chips = Array.from(root.querySelectorAll('.rounded-full')).filter((el) =>
    /bash|terminal|shell|exec|command/i.test((el.textContent || '').trim()),
  );
  return {
    ready: hasMindView && hasChatView && hasInspector,
    hasMindView,
    hasChatView,
    hasInspector,
    toolChips: chips.length,
    text: text2.slice(0, 500),
  };
})()"""


def _wait_py(predicate, *, timeout_sec: float, what: str):
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        result = predicate()
        if result:
            return result
        time.sleep(1.0)
    raise AssertionError(f"Timed out waiting for {what}")


def _fetch_trace(api_url: str, chat_id: str) -> dict[str, object]:
    resp = http_json(
        "GET", f"{api_url}/api/v1/statistics/session/{chat_id}/trace"
    )
    data = resp.get("data")
    assert isinstance(data, dict), resp
    return data


async def _run_session(chat: McpChatSession, ledger: E2EResourceLedger) -> tuple[str, str, dict[str, object]]:
    await chat.dismiss_modals()
    path_probe = await chat.evaluate(
        "(() => location.pathname)()",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    if isinstance(path_probe, str) and (
        path_probe.startswith("/settings") or path_probe.startswith("/login")
    ):
        await chat.cdp("Page.navigate", {"url": f"{BASE_URL}/"})
        await asyncio.sleep(3.0)
        await chat.bootstrap(BASE_URL, timeout_sec=120.0)

    api_url = get_e2e_api_url()

    # T1/T2: real LLM turns may decide not to invoke a tool, so retry the turn
    # until the trace exposes a lineaged tool call or the attempt budget is spent.
    last_trace: dict[str, object] = {}
    for attempt in range(1, MAX_TURNS + 1):
        if attempt > 1:
            await chat.click_new_chat()
            await chat.ensure_chat_surface(BASE_URL)
        send_result = await chat.send_message(E2E_PROMPT, E2E_PROMPT)
        chat_id_hint = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or ""
        ).strip()
        if not chat_id_hint:
            chat_id_hint = str((await chat.bridge_chat_id()) or "").strip() or None
        heartbeat_once()
        after_turn = await chat.wait_turn_done(
            E2E_PROMPT,
            timeout_sec=240,
            chat_id_hint=chat_id_hint,
        )
        chat_id = chat_id_from_path(str(after_turn.get("path") or "")) or chat_id_hint
        assert chat_id, f"Expected chat id after lineage turn: {after_turn}"
        assert chat_user_message_count(chat_id, api_url=api_url) >= 1
        trace = _wait_py(
            lambda cid=chat_id: _fetch_trace(api_url, cid),
            timeout_sec=30.0,
            what=f"execution trace for {chat_id}",
        )
        last_trace = trace
        tool_calls = trace.get("tool_calls")
        if isinstance(tool_calls, list) and tool_calls:
            lineaged = [
                tc
                for tc in tool_calls
                if isinstance(tc, dict) and tc.get("tool_call_id")
            ]
            if lineaged:
                ledger.register("chat", chat_id)
                tool_names = [
                    tc.get("tool_name")
                    for tc in tool_calls
                    if isinstance(tc, dict)
                ]
                for tc in tool_calls:
                    if isinstance(tc, dict):
                        labels = tc.get("security_labels")
                        assert labels is None or isinstance(labels, list), (
                            f"security_labels must be a list when present: {tc}"
                        )
                with_message_id = [
                    tc.get("tool_name")
                    for tc in tool_calls
                    if isinstance(tc, dict) and tc.get("message_id")
                ]
                return chat_id, api_url, {
                    "tool_names": tool_names,
                    "lineaged": [tc.get("tool_name") for tc in lineaged],
                    "with_message_id": with_message_id,
                }

    raise AssertionError(
        f"No lineaged tool call after {MAX_TURNS} real turns: "
        f"{json.dumps(last_trace, ensure_ascii=False)[:600]}"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="exclusive_backend",
)
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_chrome_ui_lineage_trace_replay(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real UI chat turn → lineage trace API → trace dialog → replay player."""
    api_url = get_e2e_api_url()
    wait_e2e_provider_ready(api_url=api_url, timeout_sec=120.0)

    client = ChromeMcpClient(request_timeout_sec=120.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = None
        try:
            page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
        except TimeoutError:
            await asyncio.sleep(2.0)
            page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
        assert page is not None, "new_page returned no page"
        chat = McpChatSession(client, page)
        await chat.bootstrap(BASE_URL, timeout_sec=120.0)
        chat_id, api_url, lineage = await _run_session(chat, e2e_resource_ledger)
        assert lineage["lineaged"], f"no lineaged tool calls: {lineage}"
    finally:
        await asyncio.to_thread(client.close)

    # T3/T4 happen against a freshly attached UI session (same backend) so the
    # trace dialog is exercised as a user would open it from the chat.
    client2 = ChromeMcpClient(request_timeout_sec=120.0)
    await asyncio.to_thread(client2.start)
    try:
        page2: McpPage | None = None
        try:
            page2 = await asyncio.to_thread(client2.new_page, BASE_URL, timeout_ms=120_000)
        except TimeoutError:
            await asyncio.sleep(2.0)
            page2 = await asyncio.to_thread(client2.new_page, BASE_URL, timeout_ms=120_000)
        assert page2 is not None, "new_page returned no page (second session)"
        chat2 = McpChatSession(client2, page2)
        await chat2.bootstrap(BASE_URL, timeout_sec=120.0)
        await chat2.navigate_to_chat(chat_id, BASE_URL, timeout_sec=90.0)
        await chat2.wait_shell_ready(timeout_sec=90.0, require_bridge=True)

        # Open the performance-diagnostics dialog from the assistant message bar.
        # Message hydration over the E2E private runtime can be slow under
        # parallel load, so budget generously for the button to appear.
        probe = await _wait_ui_state(chat2, _OPEN_DIAGNOSTICS_JS, timeout_sec=90.0)
        assert probe.get("ready") is True, json.dumps(probe, ensure_ascii=False)

        # T3: the trace dialog shows the shell tool-call card.
        trace_probe = await _wait_ui_state(
            chat2,
            _trace_dialog_probe_js(lineage["tool_names"]),
            timeout_sec=90.0,
        )
        assert trace_probe.get("ready") is True, json.dumps(
            trace_probe, ensure_ascii=False
        )
        assert trace_probe.get("toolRows", 0) >= 1, json.dumps(
            trace_probe, ensure_ascii=False
        )
        assert trace_probe.get("hasEnterReplay") is True, json.dumps(
            trace_probe, ensure_ascii=False
        )

        # T4: enter replay, scrub to the end and expect the tool chip in the mind view.
        replay_click = await _wait_ui_state(chat2, _ENTER_REPLAY_JS, timeout_sec=60.0)
        assert replay_click.get("ready") is True, json.dumps(
            replay_click, ensure_ascii=False
        )
        replay_probe = await _wait_ui_state(
            chat2,
            _REPLAY_END_STATE_JS,
            timeout_sec=60.0,
        )
        assert replay_probe.get("ready") is True, (
            f"replay_click={json.dumps(replay_click, ensure_ascii=False)} "
            f"replay_probe={json.dumps(replay_probe, ensure_ascii=False)}"
        )
        assert replay_probe.get("toolChips", 0) >= 1, json.dumps(
            replay_probe, ensure_ascii=False
        )
    finally:
        await asyncio.to_thread(client2.close)


async def _wait_ui_state(
    chat: McpChatSession,
    expression: str,
    *,
    timeout_sec: float,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_once()
        try:
            result = await chat.evaluate(
                expression,
                intent=EvaluateIntent.BRIDGE_POLL,
            )
        except (RuntimeError, TimeoutError):
            await asyncio.sleep(1.5)
            continue
        if isinstance(result, dict) and result.get("ready") is True:
            return result
        last = result if isinstance(result, dict) else {"raw": str(result)[:200]}
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"UI state not ready within {timeout_sec}s: {json.dumps(last, ensure_ascii=False)}"
    )
