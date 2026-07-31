"""Chrome LIVE E2E: ToolsPanel shows semantic ToolLayer badges after real agent-stream."""

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

from cdp_chat_support import get_e2e_api_url, get_e2e_ui_url, wait_e2e_provider_ready  # noqa: E402
from e2e_shared_ui_session import maybe_apply_shared_ui_session_contract  # noqa: E402
from mcp_chat_ui import McpChatSession, is_mux_parallel_fail_fast  # noqa: E402

from tests.support.chrome_mcp_e2e import OpenMcpPageSession, open_mcp_page_async, prepare_e2e_ui_session
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

_MAX_ATTEMPTS = 2
_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "MUX_RECLAIM_STALL",
    "MUX_TRANSPORT",
    "bridge-ready-timeout",
    "E2E_SHARED_UI_SESSION_BRIDGE",
    "open_mcp_page",
    "detached",
    "transport unavailable",
    "reset_after_orphan",
)


def _is_transport_retryable(exc: BaseException) -> bool:
    if is_mux_parallel_fail_fast(exc):
        return False
    text = str(exc)
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


async def _force_mux_heal_before_retry() -> None:
    from mux_attach_force_restart import force_mux_attach_restart_scoped

    await asyncio.to_thread(
        force_mux_attach_restart_scoped,
        reason="tools_panel layer badges outer retry",
    )
    await asyncio.sleep(3.0)

_PREP_AND_CHAT_READY_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ready: false, err: 'no-bridge' };
  if (typeof window.__MYRM_E2E_RUNTIME_READY__ !== 'undefined') {
    await window.__MYRM_E2E_RUNTIME_READY__;
  }
  await bridge.ensureProviders?.();
  if (bridge.pinLiteModelForE2e) {
    await bridge.pinLiteModelForE2e({ preserveActionMode: true });
  }
  bridge.setActionMode?.('agent');
  await bridge.ensureChatSession?.({ preserveActionMode: true });
  const debug = bridge.debugProviderState?.() ?? null;
  const runtimeApi = window.__MYRM_E2E_RUNTIME__?.apiBase ?? '';
  return {
    ready:
      !!document.querySelector('[data-chat-input]') &&
      bridge.isSendReady?.() === true &&
      !!debug?.selection,
    sendReady: bridge.isSendReady?.() === true,
    runtimeApi,
    debug,
  };
})()"""

_PREP_REAL_AGENT_TURN_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ok: false, err: 'no-bridge' };
  bridge.abortActiveStream?.();
  bridge.releaseActiveStreamForApiResume?.();
  bridge.setSseCaptureMessageId?.(null);
  const prev = bridge.getCurrentBuiltinTools?.() ?? [];
  bridge.setCurrentBuiltinTools?.(
    prev.filter((toolId) => toolId !== 'web_search' && toolId !== 'image_generation'),
  );
  window.__MYRM_E2E_BLOCK_SEARCH_SYNC__ = true;
  if (bridge.syncSearchServicesFromE2eApi) {
    await bridge.syncSearchServicesFromE2eApi();
  }
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  return {
    ok: bridge.isSendReady?.() === true,
    tools: bridge.getCurrentBuiltinTools?.() ?? [],
  };
})()"""

_KICKOFF_TURN_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.kickoffChatMessage) return { ok: false, err: 'no-kickoff' };
  bridge.setSseCaptureMessageId?.(null);
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const kick = await bridge.kickoffChatMessage('Reply OK.', {
    baselineUserCount: usersBefore,
    preserveActionMode: true,
    profile: 'read',
  });
  const resolvedMessageId =
    kick?.debug?.streamRequestMessageId
    ?? bridge.debugProviderState?.()?.streamRequestMessageId
    ?? null;
  if (resolvedMessageId) {
    bridge.setSseCaptureMessageId?.(resolvedMessageId);
  }
  const allSse = bridge.sseSnapshot?.() ?? [];
  const filteredSse = resolvedMessageId
    ? (bridge.sseSnapshot?.(resolvedMessageId) ?? [])
    : allSse;
  return {
    ...kick,
    streamMessageId: resolvedMessageId,
    sseTypes: filteredSse.length > 0 ? filteredSse : allSse,
  };
})()"""

_TOOLS_PANEL_READY_JS = """(() => {
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
  if (!sseTypes.includes('tools_snapshot') && allSse.includes('tools_snapshot')) {
    sseTypes = allSse;
  }
  return {
    ready: !!trigger && sseTypes.includes('tools_snapshot'),
    hasTrigger: !!trigger,
    hasToolsSnapshotEvent: sseTypes.includes('tools_snapshot'),
    sseTypes: sseTypes.slice(0, 12),
    allSseTypes: allSse.slice(0, 12),
    streamMessageId,
    lastSubmit: bridge?.lastSubmitResult ?? null,
    turn: bridge?.turnSnapshot?.() ?? null,
  };
})()"""

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
    recv_timeout: float = 30.0,
    poll_sec: float = 1.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        raw = await chat.evaluate(
            expression,
            await_promise=True,
            recv_timeout=recv_timeout,
        )
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ready") is True:
            return last
        await asyncio.sleep(poll_sec)
    raise AssertionError(f"State not ready within {timeout_sec:.0f}s: {last}")


async def _run_tools_panel_layer_badges_flow(
    chat: McpChatSession,
    *,
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    heartbeat_e2e_lease()
    await chat.dismiss_modals()
    await chat.click_new_chat()
    await chat.ensure_chat_surface(BASE_URL)
    await chat.ensure_react_e2e_bridge(timeout_sec=90.0)

    chat_ready = await _wait_for_eval_ready(
        chat,
        _PREP_AND_CHAT_READY_JS,
        timeout_sec=90.0,
        recv_timeout=45.0,
    )
    assert chat_ready.get("sendReady") is True, chat_ready

    heartbeat_e2e_lease()
    prep = await chat.evaluate(
        _PREP_REAL_AGENT_TURN_JS,
        await_promise=True,
        recv_timeout=60.0,
    )
    assert isinstance(prep, dict) and prep.get("ok") is True, prep

    heartbeat_e2e_lease()
    kickoff = await chat.evaluate(
        _KICKOFF_TURN_JS,
        await_promise=True,
        recv_timeout=120.0,
    )
    assert isinstance(kickoff, dict) and kickoff.get("ok") is True, kickoff

    chat_id = str(kickoff.get("chatId") or "").strip()
    if chat_id:
        e2e_resource_ledger.register("chat", chat_id)

    heartbeat_e2e_lease()
    panel = await _wait_for_eval_ready(
        chat,
        _TOOLS_PANEL_READY_JS,
        timeout_sec=120.0,
        recv_timeout=30.0,
    )
    assert panel.get("hasTrigger") is True, panel
    assert panel.get("hasToolsSnapshotEvent") is True, panel

    opened = await chat.evaluate(
        _OPEN_TOOLS_PANEL_JS,
        await_promise=False,
        recv_timeout=15.0,
    )
    assert isinstance(opened, dict) and opened.get("ok") is True, opened

    badges = await _wait_for_eval_ready(
        chat,
        _LAYER_BADGES_READY_JS,
        timeout_sec=30.0,
        recv_timeout=15.0,
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
        timeout_ms=120_000,
        request_timeout_sec=120.0,
    )
    try:
        chat = McpChatSession(session.client, session.page)
        chat._base_url = BASE_URL
        # open_mcp_page_async already navigates + waits for app-layout; skip duplicate
        # bootstrap_shell (R215 test path — avoids mux stall under parallel peers).
        await maybe_apply_shared_ui_session_contract(chat, timeout_sec=90.0)
        await _run_tools_panel_layer_badges_flow(
            chat,
            e2e_resource_ledger=e2e_resource_ledger,
        )
    finally:
        await session.aclose()


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
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
            if attempt >= _MAX_ATTEMPTS or not _is_transport_retryable(exc):
                raise
            await _force_mux_heal_before_retry()

    if last_error is not None:
        raise last_error
