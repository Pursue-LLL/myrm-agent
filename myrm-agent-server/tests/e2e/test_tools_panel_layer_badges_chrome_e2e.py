"""Chrome LIVE E2E: ToolsPanel shows semantic ToolLayer badges after real agent-stream."""

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

from cdp_chat_support import (
    BRIDGE_TURN_SNAPSHOT_JS,
    E2E_API_BINDING_PROBE_JS,
    STREAM_API_BINDING_JS,
    WAIT_WORKSPACE_STREAM_JS,
    chat_user_message_count,
    e2e_runtime_bootstrap_apply_js,
    get_e2e_api_url,
    get_e2e_ui_url,
    require_e2e_api_binding_probe,
    shpoib_parallel_shell_timeout_sec,
    signoff_parallel_force_chat_timeout_sec,
    wait_e2e_provider_ready,
)  # noqa: E402
from dev_gate_contract import EvaluateIntent  # noqa: E402
from mcp_chat_ui import McpChatSession, is_mux_parallel_fail_fast  # noqa: E402

from tests.support.chrome_mcp_e2e import (
    OpenMcpPageSession,
    open_mcp_page_async,
    prepare_e2e_ui_session,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

_RECOVER_HITL_JS = """((chatId) => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.recoverHitlStream) {
    return { ok: false, err: 'missing-recoverHitlStream' };
  }
  return bridge.recoverHitlStream(String(chatId || ''));
})"""

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

_MAX_ATTEMPTS = 1
_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "MUX_RECLAIM_STALL",
    "MUX_TRANSPORT",
    "MUX_CONTEXT_RESET",
    "R96_MUX",
    "bridge-ready-timeout",
    "E2E_SHARED_UI_SESSION_BRIDGE",
    "open_mcp_page",
    "detached",
    "Execution context was destroyed",
    "transport unavailable",
    "reset_after_orphan",
)


def _is_transport_retryable(exc: BaseException) -> bool:
    if is_mux_parallel_fail_fast(exc):
        return False
    text = str(exc)
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


def _is_tools_panel_flow_retryable(exc: BaseException) -> bool:
    text = str(exc)
    # Evaluate orphan reclaim under parallel mux — outer heal+retry is required (run75).
    if "MUX_RECLAIM_STALL" in text and "evaluate orphaned" in text:
        return True
    if _is_transport_retryable(exc):
        return True
    if not isinstance(exc, AssertionError):
        return False
    text = str(exc)
    return "State not ready" in text and (
        "hasToolsSnapshotEvent': False" in text
        or 'hasToolsSnapshotEvent": False' in text
        or "'hasToolsSnapshotEvent': False" in text
    )


async def _force_mux_heal_before_retry() -> None:
    from mux_attach_force_restart import force_mux_attach_restart_scoped

    await asyncio.to_thread(
        force_mux_attach_restart_scoped,
        reason="tools_panel layer badges outer retry",
    )
    await asyncio.sleep(3.0)


def _touch_wall_progress(node: str) -> None:
    try:
        from e2e_session_runtime.lifecycle import touch_wall_progress

        touch_wall_progress(current_node=node)
    except ImportError:
        pass


_PREP_AGENT_TURN_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ready: false, err: 'no-bridge' };
  await bridge.ensureProviders?.();
  if (bridge.pinLiteModelForE2e) {
    await bridge.pinLiteModelForE2e({ preserveActionMode: true });
  }
  bridge.setActionMode?.('agent');
  await bridge.ensureChatSession?.({ preserveActionMode: true });
  bridge.setSseCaptureMessageId?.(null);
  const prev = bridge.getCurrentBuiltinTools?.() ?? [];
  bridge.setCurrentBuiltinTools?.(
    prev.filter((toolId) => toolId !== 'web_search' && toolId !== 'image_generation'),
  );
  window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
  if (bridge.syncSearchServicesFromE2eApi) {
    await bridge.syncSearchServicesFromE2eApi();
  }
  const debug = bridge.debugProviderState?.() ?? null;
  const sendReady = bridge.isSendReady?.() === true;
  const hasInput = !!document.querySelector('[data-chat-input]');
  const hasSelection = !!debug?.selection;
  return {
    ready: hasInput && sendReady && hasSelection,
    ok: hasInput && sendReady && hasSelection,
    sendReady,
    hasInput,
    hasSelection,
    debug,
    tools: bridge.getCurrentBuiltinTools?.() ?? [],
  };
})()"""


_WAIT_TOOLS_PANEL_READY_JS = """(async () => {
  const sleep = (ms) => new Promise((resolve) => setTimeout(resolve, ms));
  const deadline = Date.now() + 30000;
  let last = {};
  while (Date.now() < deadline) {
    const bridge = window.__MYRM_E2E_CHAT__;
    const trigger = document.querySelector('[data-testid="tools-panel-trigger"]');
    const streamMessageId = bridge?.debugProviderState?.()?.streamRequestMessageId ?? null;
    const allSse = bridge?.sseSnapshot?.() ?? [];
    let sseTypes = allSse;
    if (streamMessageId) {
      const filtered = bridge?.sseSnapshot?.(streamMessageId) ?? [];
      if (filtered.length > 0) {
        sseTypes = filtered;
      }
    }
    const muxMessageId = window.__MYRM_MULTIPLEX_STATS__?.()?.lastMessageId ?? null;
    if (!sseTypes.includes('tools_snapshot') && typeof muxMessageId === 'string' && muxMessageId.trim()) {
      const muxSse = bridge?.sseSnapshot?.(muxMessageId.trim()) ?? [];
      if (muxSse.includes('tools_snapshot')) {
        sseTypes = muxSse;
      }
    }
    if (!sseTypes.includes('tools_snapshot') && allSse.includes('tools_snapshot')) {
      sseTypes = allSse;
    }
    let toolsCount = 0;
    let layerSlugs = [];
    try {
      const mod = await import('/src/store/useToolsSnapshotStore');
      const tools = mod.default.getState().tools ?? [];
      toolsCount = tools.length;
      layerSlugs = tools.map((row) => String(row.layer ?? '').trim().toLowerCase()).filter(Boolean);
    } catch (_) {}
    const hasToolsSnapshotEvent = sseTypes.includes('tools_snapshot') || toolsCount > 0;
    last = {
      ready: hasToolsSnapshotEvent && (!!trigger || toolsCount > 0),
      hasTrigger: !!trigger,
      hasToolsSnapshotEvent,
      toolsCount,
      layerSlugs: layerSlugs.slice(0, 16),
      sseTypes: sseTypes.slice(0, 12),
      allSseTypes: allSse.slice(0, 12),
      streamMessageId,
      muxMessageId: typeof muxMessageId === 'string' ? muxMessageId : null,
      directSse: !!window.__MYRM_E2E_DIRECT_SSE__,
      turn: bridge?.turnSnapshot?.() ?? null,
    };
    if (last.ready) {
      return last;
    }
    await sleep(500);
  }
  return last;
})()"""


async def _wait_for_tools_panel_ready(
    chat: McpChatSession,
    *,
    api_url: str,
    chat_id: str,
    timeout_sec: float = 130.0,
) -> dict[str, object]:
    del api_url, chat_id
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        _touch_wall_progress("tools_panel_wait_snapshot")
        raw = await chat.evaluate(
            _WAIT_TOOLS_PANEL_READY_JS,
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ready") is True:
            return last
        await asyncio.sleep(0.5)
    raise AssertionError(f"ToolsPanel not ready within {timeout_sec:.0f}s: {last}")


_OPEN_TOOLS_PANEL_JS = """(() => {
  const trigger = document.querySelector('[data-testid="tools-panel-trigger"]');
  if (!trigger) return { ok: false, err: 'no-trigger' };
  trigger.click();
  return { ok: true };
})()"""

_LAYER_BADGES_READY_JS = """(() => {
  const panel = document.querySelector('[data-testid="tools-panel-content"]');
  if (!panel) return { ready: false, reason: 'no-panel' };
  const text = panel.innerText || '';
  const badges = Array.from(panel.querySelectorAll('span'))
    .map((el) => (el.textContent || '').trim())
    .filter(Boolean);
  const hasCore = /(?:^|\\s)(核心|Core)(?:\\s|$)/.test(text);
  const hasCommon = /(?:^|\\s)(通用|Common)(?:\\s|$)/.test(text);
  const hasExtended = /(?:^|\\s)(扩展|Extended)(?:\\s|$)/.test(text);
  const hasDigitLayer = badges.some((label) => /^[1-4]$/.test(label));
  return {
    ready: hasCore && hasCommon && hasExtended && !hasDigitLayer,
    hasCore,
    hasCommon,
    hasExtended,
    hasDigitLayer,
    badges: badges.slice(0, 40),
    sample: text.slice(0, 400),
  };
})()"""


async def _wait_for_eval_ready(
    chat: McpChatSession,
    expression: str,
    *,
    timeout_sec: float,
    intent: EvaluateIntent = EvaluateIntent.BRIDGE_POLL,
    poll_sec: float = 1.0,
    progress_node: str = "tools_panel_eval_wait",
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        _touch_wall_progress(progress_node)
        raw = await chat.evaluate(
            expression,
            intent=intent,
        )
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ready") is True or last.get("ok") is True:
            return last
        await asyncio.sleep(poll_sec)
    raise AssertionError(f"State not ready within {timeout_sec:.0f}s: {last}")


async def _apply_e2e_runtime_bootstrap(chat: McpChatSession) -> None:
    bootstrap_js = e2e_runtime_bootstrap_apply_js()
    if not bootstrap_js:
        await chat.ensure_e2e_api_base_binding()
        return
    result = await chat.evaluate(
        bootstrap_js,
        intent=EvaluateIntent.AGENT_SUBMIT,
    )
    if not isinstance(result, dict) or result.get("ok") is not True:
        raise RuntimeError(f"E2E runtime bootstrap failed: {result}")


async def _wait_api_user_messages(
    chat_id: str,
    *,
    api_url: str,
    min_count: int,
    timeout_sec: float,
) -> None:
    deadline = time.monotonic() + timeout_sec
    last = 0
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        _touch_wall_progress("tools_panel_api_user_gate")
        try:
            last = await asyncio.wait_for(
                asyncio.to_thread(
                    chat_user_message_count,
                    chat_id,
                    api_url=api_url,
                    timeout_sec=8.0,
                    max_attempts=1,
                ),
                timeout=12.0,
            )
        except (TimeoutError, OSError):
            last = 0
        if last >= min_count:
            return
        await asyncio.sleep(1.0)
    raise AssertionError(
        f"Backend did not persist user message within {timeout_sec:.0f}s "
        f"(chat_id={chat_id!r} last={last} api={api_url})"
    )


async def _assert_private_api_binding(chat: McpChatSession, *, api_url: str) -> None:
    probe = await chat.evaluate(
        E2E_API_BINDING_PROBE_JS,
        intent=EvaluateIntent.SYNC_PROBE,
    )
    require_e2e_api_binding_probe(probe, api_url)
    stream_binding = await chat.evaluate(
        STREAM_API_BINDING_JS,
        intent=EvaluateIntent.SYNC_PROBE,
    )
    binding = stream_binding if isinstance(stream_binding, dict) else {}
    if binding.get("usesRelativeProxy") is True or binding.get("hasPrivateBinding") is not True:
        raise AssertionError(
            "SHPOIB stream binding missing — agent-stream may hit shared :8080; "
            f"binding={binding!r}; expected={api_url!r}"
        )


async def _run_tools_panel_layer_badges_flow(
    chat: McpChatSession,
    *,
    api_url: str,
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    _USER_PROMPT = "Reply OK."
    heartbeat_e2e_lease()
    _touch_wall_progress("tools_panel_flow_start")
    chat._client.set_tool_wall_deadline(None)

    await chat.dismiss_modals()
    await chat.click_new_chat()
    await chat.ensure_chat_surface(BASE_URL)
    await _apply_e2e_runtime_bootstrap(chat)
    await _assert_private_api_binding(chat, api_url=api_url)

    chat_ready = await _wait_for_eval_ready(
        chat,
        _PREP_AGENT_TURN_JS,
        timeout_sec=90.0,
        intent=EvaluateIntent.AGENT_SUBMIT,
        progress_node="tools_panel_prep_agent_turn",
    )
    assert chat_ready.get("sendReady") is True, chat_ready

    heartbeat_e2e_lease()
    workspace = await chat.evaluate(
        WAIT_WORKSPACE_STREAM_JS,
        intent=EvaluateIntent.AGENT_SUBMIT,
    )
    assert isinstance(workspace, dict) and workspace.get("ok") is True, workspace

    heartbeat_e2e_lease()
    _touch_wall_progress("tools_panel_kickoff")
    send_result = await chat.send_message(_USER_PROMPT, _USER_PROMPT)
    assert isinstance(send_result, dict), send_result
    submit = send_result.get("submit")
    assert isinstance(submit, dict) and submit.get("ok") is True, send_result

    chat_id = str(
        submit.get("chatId")
        or (
            send_result.get("started", {}).get("chatId")
            if isinstance(send_result.get("started"), dict)
            else None
        )
        or (await chat.bridge_chat_id())
        or ""
    ).strip()
    assert chat_id, f"SendTurnContract missing chatId: {send_result}"

    submit_debug = submit.get("debug") if isinstance(submit.get("debug"), dict) else {}
    baseline_users = int(submit_debug.get("baselineUsers") or 0)
    seal_api_users = int(submit_debug.get("apiUsers") or 0)
    seal_streaming = submit_debug.get("streaming") is True
    _touch_wall_progress(
        f"tools_panel_seal apiUsers={seal_api_users} "
        f"streaming={seal_streaming} baseline={baseline_users}"
    )

    if seal_api_users <= baseline_users and not (
        seal_streaming and submit.get("ok") is True
    ):
        # LIVE sendTurnSealed may seal on uiProgress+streaming before API row persists (parallel SHPOIB).
        api_gate_sec = (
            signoff_parallel_force_chat_timeout_sec(180.0)
            if seal_streaming
            else signoff_parallel_force_chat_timeout_sec(45.0)
        )
        await _wait_api_user_messages(
            chat_id,
            api_url=api_url,
            min_count=1,
            timeout_sec=api_gate_sec,
        )
    elif seal_api_users <= baseline_users:
        _touch_wall_progress(
            "tools_panel_api_gate_skipped sendTurnSealed streaming=true"
        )

    # SSOT: stay on the streaming tab — post-SEAL attachToChat can force-reload while
    # loading=true and drop direct SSE (run54605: userCount=0, sseTypes=[]).
    started = await chat.wait_stream_started(
        _USER_PROMPT,
        timeout_sec=signoff_parallel_force_chat_timeout_sec(180.0),
        chat_id_hint=chat_id,
    )
    chat_id = chat_id or str(started.get("chatId") or "").strip()
    assert chat_id, f"Expected chat id after stream start: started={started}; send={send_result}"

    turn_probe = await chat.evaluate(
        BRIDGE_TURN_SNAPSHOT_JS,
        intent=EvaluateIntent.BRIDGE_POLL,
    )
    turn = turn_probe if isinstance(turn_probe, dict) else {}
    if int(turn.get("userCount") or 0) < 1 and turn.get("isStreaming") is not True:
        await chat.evaluate(
            f"({_RECOVER_HITL_JS})({json.dumps(chat_id)})",
            intent=EvaluateIntent.AGENT_SUBMIT,
        )

    await _wait_for_eval_ready(
        chat,
        """(() => {
          const turn = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
          const sse = window.__MYRM_E2E_CHAT__?.sseSnapshot?.() ?? [];
          return {
            ready:
              (turn.userCount ?? 0) >= 1 ||
              turn.isStreaming === true ||
              sse.includes('tools_snapshot'),
            turn,
            sseTypes: sse.slice(0, 12),
          };
        })()""",
        timeout_sec=signoff_parallel_force_chat_timeout_sec(120.0),
        intent=EvaluateIntent.BRIDGE_POLL,
        progress_node="tools_panel_live_ui_hydrate",
    )

    path_probe = await chat.evaluate(
        "(() => ({ path: location.pathname }))()",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    current_path = (
        str(path_probe.get("path") or "") if isinstance(path_probe, dict) else ""
    )
    if current_path != f"/{chat_id}":
        await chat.navigate_to_chat(chat_id, BASE_URL, timeout_sec=90.0)
    await _assert_private_api_binding(chat, api_url=api_url)

    e2e_resource_ledger.register("chat", chat_id)

    heartbeat_e2e_lease()
    panel = await _wait_for_tools_panel_ready(
        chat,
        api_url=api_url,
        chat_id=chat_id,
        timeout_sec=signoff_parallel_force_chat_timeout_sec(180.0),
    )
    assert panel.get("hasTrigger") is True, panel
    assert panel.get("hasToolsSnapshotEvent") is True, panel

    opened = await chat.evaluate(
        _OPEN_TOOLS_PANEL_JS,
        intent=EvaluateIntent.SYNC_PROBE,
    )
    assert isinstance(opened, dict) and opened.get("ok") is True, opened

    badges = await _wait_for_eval_ready(
        chat,
        _LAYER_BADGES_READY_JS,
        timeout_sec=30.0,
        intent=EvaluateIntent.BRIDGE_POLL,
        poll_sec=0.5,
    )
    assert badges.get("hasCore") is True, badges
    assert badges.get("hasCommon") is True, badges
    assert badges.get("hasExtended") is True, badges
    assert badges.get("hasDigitLayer") is False, badges


async def _run_tools_panel_e2e_once(
    api_url: str,
    ui_url: str,
    *,
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    session: OpenMcpPageSession = await open_mcp_page_async(
        f"{ui_url}/",
        timeout_ms=90_000,
        request_timeout_sec=120.0,
    )
    try:
        chat = McpChatSession(session.client, session.page)
        chat._base_url = BASE_URL
        session.client.set_tool_wall_deadline(None)
        bootstrap_timeout = signoff_parallel_force_chat_timeout_sec(
            shpoib_parallel_shell_timeout_sec(240.0)
        )
        _touch_wall_progress("tools_panel_bootstrap")
        await chat.bootstrap(BASE_URL, timeout_sec=bootstrap_timeout)
        _touch_wall_progress("tools_panel_page_ready")
        await _run_tools_panel_layer_badges_flow(
            chat,
            api_url=api_url,
            e2e_resource_ledger=e2e_resource_ledger,
        )
    finally:
        await session.aclose()


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE"
, private_reason="live_shpoib")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.asyncio
async def test_tools_panel_shows_semantic_layer_badges_after_tools_snapshot(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real chat kickoff → tools_snapshot SSE → ToolsPanel i18n layer badges (no digit layers)."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    if not wait_e2e_provider_ready(api_url=api_url, timeout_sec=90.0):
        pytest.fail(
            "Provider config not ready for tools_panel Chrome LIVE E2E — "
            "run via ./myrm test -m chrome_e2e after ./myrm ready --chrome",
        )

    prepare_e2e_ui_session(api_url)

    last_error: BaseException | None = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            await _run_tools_panel_e2e_once(
                api_url,
                ui_url,
                e2e_resource_ledger=e2e_resource_ledger,
            )
            return
        except Exception as exc:
            last_error = exc
            if attempt >= _MAX_ATTEMPTS or not _is_tools_panel_flow_retryable(exc):
                raise
            await _force_mux_heal_before_retry()

    if last_error is not None:
        raise last_error
