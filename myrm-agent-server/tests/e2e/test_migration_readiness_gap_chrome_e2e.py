"""Chrome E2E: migration post-import readiness SSE toast on first chat."""

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

from cdp_chat_support import (  # noqa: E402
    WAIT_WORKSPACE_STREAM_JS,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)
from chrome_mcp_client import ChromeMcpClient  # noqa: E402
from dev_gate_contract import EvaluateIntent  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_mcp_e2e import (
    get_e2e_ui_url,
    prepare_e2e_ui_session,
    warm_ui_route,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

_AGENT_PROMPT = "Hello after migration import"
_E2E_GAP_TEST_WALL_SEC = 480.0

_MIGRATION_GAP_TOAST_PATTERN = (
    r"MCP servers were imported|MCP 已导入|Open MCP Settings|"
    r"migration follow-ups|待完成项|not enabled yet|/settings/mcp"
)

_MIGRATION_CRITICAL_GAP_TOAST_PATTERN = (
    r"Configure model providers|模型提供商|/settings/models|"
    r"not ready to chat|尚未就绪|migration_readiness_critical|"
    r"diagnostics|诊断|/settings/memory|Memory Center"
)

_ENSURE_DIRECT_SSE_OFF_JS = """(() => {
  window.__MYRM_E2E_DIRECT_SSE__ = false;
  return { ok: true, directSse: !!window.__MYRM_E2E_DIRECT_SSE__ };
})()"""


def _wait_assistant_message_via_api(
    api_base: str,
    chat_id: str,
    *,
    timeout_sec: float = 150.0,
) -> str:
    import httpx

    url = f"{api_base.rstrip('/')}/api/v1/chats/{chat_id}/messages"
    deadline = time.monotonic() + timeout_sec
    last_payload: object = None
    while time.monotonic() < deadline:
        try:
            response = httpx.get(url, timeout=15.0)
            response.raise_for_status()
            last_payload = response.json()
        except httpx.HTTPError:
            time.sleep(2.0)
            continue
        messages: list[object] = []
        if isinstance(last_payload, dict):
            data_block = last_payload.get("data")
            raw_messages: object = None
            if isinstance(data_block, dict):
                raw_messages = data_block.get("messages")
            elif isinstance(data_block, list):
                raw_messages = data_block
            else:
                raw_messages = last_payload.get("messages")
            if isinstance(raw_messages, list):
                messages = raw_messages
        for item in reversed(messages):
            if not isinstance(item, dict) or item.get("role") != "assistant":
                continue
            content = str(item.get("content") or "").strip()
            if len(content) > 5:
                return content[:400]
        time.sleep(2.0)
    raise AssertionError(
        f"assistant message not ready via API for chat {chat_id} after {timeout_sec}s; "
        f"last_payload={last_payload!r}"
    )


_WAIT_CHAT_IDLE_BEFORE_SEND_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ok: false, err: 'no-bridge' };
  const deadline = Date.now() + 30000;
  while (Date.now() < deadline) {
    const snap = bridge.turnSnapshot?.() ?? {};
    if (!snap.isStreaming) {
      return { ok: true, turn: snap };
    }
    await new Promise((resolve) => setTimeout(resolve, 200));
  }
  return { ok: false, err: 'chat-still-streaming', turn: bridge.turnSnapshot?.() ?? null };
})()"""

_WAIT_ASSISTANT_AFTER_SEND_JS = """(async () => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return { ok: false, err: 'no-bridge' };
  const deadline = Date.now() + 180000;
  while (Date.now() < deadline) {
    const snap = bridge.turnSnapshot?.() ?? {};
    const sample = String(snap.lastAssistantSample || '').trim();
    if (!snap.isStreaming && sample.length > 5) {
      return { ok: true, turn: snap, assistantSample: sample.slice(0, 400) };
    }
    await new Promise((resolve) => setTimeout(resolve, 400));
  }
  return { ok: false, err: 'chat-still-streaming', turn: bridge.turnSnapshot?.() ?? null };
})()"""


def _ensure_shared_ui_base() -> None:
    if os.environ.get("MYRM_E2E_ISOLATED", "").strip() == "1":
        return
    ui_base = os.environ.get("E2E_UI_BASE", "http://127.0.0.1:3000").strip()
    if ui_base != "http://127.0.0.1:3000":
        os.environ["E2E_UI_BASE"] = "http://127.0.0.1:3000"


def _httpx_retry_delay_seconds(response: object | None, attempt: int) -> float:
    import httpx

    if isinstance(response, httpx.Response):
        retry_after = response.headers.get("Retry-After")
        if retry_after is not None:
            try:
                return min(60.0, max(2.0, float(retry_after)))
            except ValueError:
                pass
    return min(12.0, 2.0 * (attempt + 1))


def _seed_migration_readiness(*, variant: str = "mcp_warning") -> dict[str, str]:
    import httpx

    api_base = get_e2e_api_url()
    url = (
        f"{api_base.rstrip('/')}/api/v1/memory/test/seed-migration-readiness-fixture"
        f"?variant={variant}"
    )
    last_error: BaseException | None = None
    last_response: httpx.Response | None = None
    for attempt in range(12):
        try:
            response = httpx.post(
                url,
                timeout=httpx.Timeout(25.0, connect=10.0),
            )
            last_response = response
            if response.status_code == 503:
                last_error = httpx.HTTPStatusError(
                    f"503 seed on {url}",
                    request=response.request,
                    response=response,
                )
                time.sleep(_httpx_retry_delay_seconds(response, attempt))
                continue
            response.raise_for_status()
            payload = response.json()
            assert isinstance(payload, dict)
            return {str(key): str(value) for key, value in payload.items()}
        except (httpx.HTTPError, TimeoutError, AssertionError) as exc:
            last_error = exc
            time.sleep(_httpx_retry_delay_seconds(last_response, attempt))
    raise AssertionError(
        f"seed-migration-readiness-fixture failed after retries on {url}; last_error={last_error!r}"
    ) from last_error


def _prepare_migration_chat_js(seed: dict[str, str]) -> str:
    seed_json = json.dumps(seed)
    return f"""(async () => {{
      const seed = {seed_json};
      const bridge = window.__MYRM_E2E_CHAT__;
      const chat = window.__myrmChatStore?.getState?.();
      if (!bridge || !chat) return {{ ok: false, err: 'no-bridge-or-store' }};
      bridge.abortActiveStream?.();
      bridge.releaseActiveStreamForApiResume?.();
      window.__MYRM_E2E_DIRECT_SSE__ = false;
      if (typeof bridge.ensureProviders === 'function') {{
        await bridge.ensureProviders();
      }}
      const apiBase = String(
        window.__MYRM_E2E_API_BASE__ || window.__MYRM_E2E_RUNTIME__?.apiBase || '',
      ).replace(/\\/+$/, '');
      if (!apiBase) return {{ ok: false, err: 'no-api-base' }};
      const agentResp = await fetch(
        `${{apiBase}}/api/v1/user-agents/${{encodeURIComponent(seed.target_agent_id)}}`,
        {{ cache: 'no-store' }},
      );
      if (!agentResp.ok) {{
        return {{ ok: false, err: 'agent-fetch-failed', status: agentResp.status, apiBase }};
      }}
      const agentPayload = await agentResp.json();
      const agent = agentPayload?.data ?? agentPayload;
      if (!agent?.id) return {{ ok: false, err: 'agent-payload-invalid', apiBase }};
      chat.setActionMode('agent');
      chat.setAgentConfig({{
        selectedSkillIds: agent.skill_ids || [],
        skillConfigs: agent.skill_configs || {{}},
        selectedMcpNames: agent.mcp_ids || [],
        systemPrompt: agent.system_prompt || '',
        useGlobalInstruction: true,
        autoRestoreDomains: agent.auto_restore_domains || [],
        agentId: agent.id,
        agentName: agent.name,
        agentDescription: agent.description || '',
        avatarUrl: agent.avatar_url,
        suggestionPrompts: agent.suggestion_prompts || undefined,
        memoryDecayProfile: agent.memory_decay_profile || 'normal',
        browserSource: agent.browser_source || undefined,
      }});
      if (typeof bridge.ensureChatSession === 'function') {{
        await bridge.ensureChatSession({{ preserveActionMode: true }});
      }}
      if (typeof bridge.pinBasicModelForE2e === 'function') {{
        await bridge.pinBasicModelForE2e();
      }} else if (typeof bridge.pinLiteModelForE2e === 'function') {{
        await bridge.pinLiteModelForE2e({{ preserveActionMode: true }});
      }}
      const state = window.__myrmChatStore?.getState?.();
      return {{
        ok: state?.actionMode === 'agent'
          && state?.agentConfig?.agentId === seed.target_agent_id
          && !!bridge.isSendReady?.(),
        agentId: state?.agentConfig?.agentId ?? null,
        apiBase,
        sendReady: !!bridge.isSendReady?.(),
      }};
    }})()"""


def _set_anchor_js(seed: dict[str, str]) -> str:
    seed_json = json.dumps(seed)
    return f"""(() => {{
      const seed = {seed_json};
      localStorage.setItem(
        'myrm:migration-readiness-anchor',
        JSON.stringify({{
          importBatchId: seed.import_batch_id,
          readinessStatus: seed.readiness_status,
          targetAgentId: seed.target_agent_id,
          queuedAt: new Date().toISOString(),
        }}),
      );
      return {{ ok: true }};
    }})()"""


def _pre_send_assert_js(seed: dict[str, str], expected_api: str) -> str:
    seed_json = json.dumps(seed)
    expected_json = json.dumps(expected_api.rstrip("/"))
    return f"""(() => {{
      const seed = {seed_json};
      const expectedApi = {expected_json};
      const state = window.__myrmChatStore?.getState?.();
      let anchor = null;
      try {{
        const raw = localStorage.getItem('myrm:migration-readiness-anchor');
        anchor = raw ? JSON.parse(raw) : null;
      }} catch {{
        anchor = null;
      }}
      const apiBase = String(
        window.__MYRM_E2E_API_BASE__ || window.__MYRM_E2E_RUNTIME__?.apiBase || '',
      ).replace(/\\/+$/, '');
      const agentId = state?.agentConfig?.agentId?.trim() || '';
      const ok =
        apiBase === expectedApi &&
        agentId === seed.target_agent_id &&
        anchor?.targetAgentId === seed.target_agent_id &&
        anchor?.importBatchId === seed.import_batch_id &&
        state?.actionMode === 'agent' &&
        !!window.__MYRM_E2E_CHAT__?.isSendReady?.();
      return {{ ok, apiBase, expectedApi, agentId, anchor, actionMode: state?.actionMode }};
    }})()"""


def _gap_poll_snapshot_js(
    message_id: str | None,
    *,
    gap_pattern: str = _MIGRATION_GAP_TOAST_PATTERN,
) -> str:
    filter_json = json.dumps(message_id)
    gap_pattern_json = json.dumps(gap_pattern)
    return f"""(() => {{
      const gapPattern = new RegExp({gap_pattern_json}, 'i');
      const toastNodes = Array.from(
        document.querySelectorAll('[data-sonner-toast], [data-sonner-toaster] [data-sonner-toast]'),
      );
      const texts = toastNodes.map((node) => (node.textContent || '').trim()).filter(Boolean);
      let streamMessageId = {filter_json};
      if (!streamMessageId) {{
        const probe = window.__MYRM_E2E_CHAT__?.debugProviderState?.()?.streamRequestMessageId;
        if (typeof probe === 'string' && probe.trim()) streamMessageId = probe.trim();
      }}
      const muxMessageId = window.__MYRM_MULTIPLEX_STATS__?.()?.lastMessageId ?? null;
      const allSseEvents = window.__MYRM_E2E_CHAT__?.sseSnapshot?.() ?? [];
      let sseEvents = streamMessageId
        ? (window.__MYRM_E2E_CHAT__?.sseSnapshot?.(streamMessageId) ?? [])
        : allSseEvents;
      if (!sseEvents.includes('capability_gap') && typeof muxMessageId === 'string' && muxMessageId.trim()) {{
        const muxSse = window.__MYRM_E2E_CHAT__?.sseSnapshot?.(muxMessageId.trim()) ?? [];
        if (muxSse.includes('capability_gap')) {{
          sseEvents = muxSse;
          streamMessageId = muxMessageId.trim();
        }}
      }}
      if (!sseEvents.includes('capability_gap') && allSseEvents.includes('capability_gap')) {{
        sseEvents = allSseEvents;
      }}
      if (streamMessageId) {{
        window.__MYRM_E2E_CHAT__?.setSseCaptureMessageId?.(streamMessageId);
      }}
      return {{
        toast: {{
          count: toastNodes.length,
          migrationCount: texts.filter((t) => gapPattern.test(t)).length,
          texts,
        }},
        sseEvents,
        allSseEvents,
        streamMessageId: streamMessageId ?? null,
      }};
    }})()"""


def _assert_gap_wall_budget(wall_deadline: float) -> None:
    if time.monotonic() > wall_deadline:
        pytest.fail(
            f"migration gap E2E exceeded {_E2E_GAP_TEST_WALL_SEC}s body wall budget"
        )


async def _evaluate_gap_snapshot(
    chat: McpChatSession,
    *,
    message_id: str | None,
    wall_deadline: float,
    gap_pattern: str = _MIGRATION_GAP_TOAST_PATTERN,
) -> dict[str, object]:
    _assert_gap_wall_budget(wall_deadline)
    js = _gap_poll_snapshot_js(message_id, gap_pattern=gap_pattern)
    raw = await chat.evaluate(js, intent=EvaluateIntent.SYNC_PROBE)
    return raw if isinstance(raw, dict) else {"value": raw}


async def _send_and_collect_migration_gap(
    chat: McpChatSession,
    *,
    api_base: str,
    seed: dict[str, str],
    wall_deadline: float,
    gap_pattern: str = _MIGRATION_GAP_TOAST_PATTERN,
    gap_timeout_sec: float = 90.0,
    require_assistant_reply: bool = False,
) -> tuple[dict[str, object], list[str], dict[str, object], dict[str, object]]:
    _assert_gap_wall_budget(wall_deadline)
    await chat.ensure_react_e2e_bridge(timeout_sec=60.0)

    idle = await chat.evaluate(
        _WAIT_CHAT_IDLE_BEFORE_SEND_JS, intent=EvaluateIntent.AGENT_SUBMIT
    )
    assert isinstance(idle, dict) and idle.get("ok") is True, idle

    pre_send = await chat.evaluate(
        _pre_send_assert_js(seed, api_base),
        intent=EvaluateIntent.SYNC_PROBE,
    )
    assert isinstance(pre_send, dict) and pre_send.get("ok") is True, pre_send

    await chat.evaluate(
        "() => { window.__MYRM_E2E_CHAT__?.clearSseSnapshot?.(); return { ok: true }; }",
        intent=EvaluateIntent.SYNC_PROBE,
    )

    direct_off = await chat.evaluate(
        _ENSURE_DIRECT_SSE_OFF_JS,
        intent=EvaluateIntent.SYNC_PROBE,
    )
    assert (
        isinstance(direct_off, dict) and direct_off.get("directSse") is False
    ), direct_off

    send_task = asyncio.create_task(
        chat.send_chat_message_atomic(_AGENT_PROMPT, baseline_user_msgs=0),
    )

    gap_deadline = time.monotonic() + gap_timeout_sec
    best_toast: dict[str, object] = {"migrationCount": 0}
    best_sse: list[str] = []
    stream_message_id: str | None = None
    saw_gap = False

    while time.monotonic() < gap_deadline:
        _assert_gap_wall_budget(wall_deadline)
        heartbeat_e2e_lease()
        snapshot = await _evaluate_gap_snapshot(
            chat,
            message_id=stream_message_id,
            wall_deadline=wall_deadline,
            gap_pattern=gap_pattern,
        )
        if (
            isinstance(snapshot.get("streamMessageId"), str)
            and snapshot["streamMessageId"].strip()
        ):
            stream_message_id = snapshot["streamMessageId"].strip()
        toast_state = (
            snapshot.get("toast") if isinstance(snapshot.get("toast"), dict) else {}
        )
        sse_events = (
            snapshot.get("sseEvents")
            if isinstance(snapshot.get("sseEvents"), list)
            else []
        )
        best_toast = toast_state
        best_sse = [str(item) for item in sse_events]
        if "capability_gap" in best_sse:
            saw_gap = True
        if int(toast_state.get("migrationCount") or 0) >= 1:
            saw_gap = True
        if saw_gap and send_task.done():
            break
        await asyncio.sleep(0.4)

    if send_task.done():
        raw_send = send_task.result()
        send_result = raw_send if isinstance(raw_send, dict) else {"value": raw_send}
    else:
        raw_send = await asyncio.wait_for(send_task, timeout=180.0)
        send_result = raw_send if isinstance(raw_send, dict) else {"value": raw_send}

    diag_raw = await chat.evaluate(
        f"""(() => ({{
          sse: window.__MYRM_E2E_CHAT__?.sseSnapshot?.({json.dumps(stream_message_id)}) ?? [],
          allSse: window.__MYRM_E2E_CHAT__?.sseSnapshot?.() ?? [],
          directSse: !!window.__MYRM_E2E_DIRECT_SSE__,
          apiBase: window.__MYRM_E2E_API_BASE__ ?? null,
          turn: window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? null,
        }}))()""",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    diag = diag_raw if isinstance(diag_raw, dict) else {"value": diag_raw}
    diag["sawGap"] = saw_gap
    diag["requireAssistantReply"] = require_assistant_reply
    return best_toast, best_sse, send_result, diag


async def _open_migration_chat_page(
    client: ChromeMcpClient,
    chat_url: str,
) -> object:
    """Open chat page with mux-flake retries (parallel SHPOIB)."""
    from chrome_mcp_errors import is_transient_mux_error

    last_error: RuntimeError | None = None
    for attempt in range(3):
        try:
            return await asyncio.to_thread(
                client.new_page, chat_url, timeout_ms=120_000
            )
        except RuntimeError as exc:
            last_error = exc
            message = str(exc)
            lowered = message.lower()
            from transport_supervisor import MUX_TRANSPORT_EXHAUSTED_TOKEN

            retriable = (
                "new_page failed" in message
                or "E2E_MUX_DAEMONS_FAIL_CLOSED" in message
                or MUX_TRANSPORT_EXHAUSTED_TOKEN in message
                or "could not connect to chrome" in lowered
                or "unexpected server response: 404" in lowered
                or is_transient_mux_error(message)
            )
            if not retriable or attempt >= 2:
                raise
            from transport_supervisor import reset_session_recovery_budget

            reset_session_recovery_budget()
            if (
                "unexpected server response: 404" in lowered
                or "could not connect to chrome" in lowered
            ):
                from mux_attach_force_restart import force_mux_attach_restart_scoped

                await asyncio.to_thread(
                    force_mux_attach_restart_scoped,
                    reason=f"migration new_page retry attempt={attempt + 1}",
                )
            else:
                await asyncio.to_thread(client.recover_mux_transport)
            await asyncio.sleep(5.0 * (attempt + 1))
    if last_error is not None:
        raise last_error
    raise RuntimeError("Chrome MCP new_page failed without error detail")


async def _run_migration_readiness_gap_e2e(
    *,
    variant: str,
    expected_readiness: str,
    gap_pattern: str,
    e2e_resource_ledger: E2EResourceLedger,
    client: ChromeMcpClient | None = None,
    skip_warm_ui: bool = False,
    provider_preverified: bool = False,
    api_base_hint: str | None = None,
) -> None:
    from app.services.agent.stream_session.entitlement_gap_preflight import (
        reset_capability_gap_emission_tracker,
    )

    _ensure_shared_ui_base()
    reset_capability_gap_emission_tracker()

    api_base = (api_base_hint or get_e2e_api_url()).rstrip("/")
    initial_provider_wait_sec = 180.0 if skip_warm_ui else 120.0
    if not provider_preverified:
        if not wait_e2e_provider_ready(
            api_url=api_base,
            timeout_sec=initial_provider_wait_sec,
        ):
            pytest.fail(
                f"E2E provider not ready on {api_base} "
                f"(wait={initial_provider_wait_sec}s variant={variant})"
            )

    seed = _seed_migration_readiness(variant=variant)
    assert (
        seed.get("readiness_status") == expected_readiness
    ), f"seed fixture must report {expected_readiness} readiness; seed={seed!r}"
    await asyncio.sleep(1.0)
    api_base = get_e2e_api_url()
    provider_wait_sec = 180.0 if skip_warm_ui else 120.0
    if not wait_e2e_provider_ready(api_url=api_base, timeout_sec=provider_wait_sec):
        pytest.fail(
            f"E2E provider not ready after seed on {api_base} variant={variant}"
        )

    prepare_e2e_ui_session(api_base)
    if skip_warm_ui:
        from e2e_orchestrator import touch_wall_progress

        touch_wall_progress(current_node="warm_ui_route_skipped_batch_reuse")
    else:
        warm_ui_route(seed["chat_ui_path"])
    from transport_supervisor import reset_session_recovery_budget

    reset_session_recovery_budget()

    ui_url = get_e2e_ui_url()
    chat_url = f"{ui_url}{seed['chat_ui_path']}"
    wall_deadline = time.monotonic() + _E2E_GAP_TEST_WALL_SEC

    owns_client = client is None
    if owns_client:
        client = ChromeMcpClient(request_timeout_sec=180.0)
        await asyncio.to_thread(client.start)
    assert client is not None
    page: object | None = None
    try:
        page = await _open_migration_chat_page(client, chat_url)
        chat = McpChatSession(client, page)
        await chat.bootstrap(chat_url, timeout_sec=120.0)

        prepared = await chat.evaluate(
            _prepare_migration_chat_js(seed),
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        assert isinstance(prepared, dict) and prepared.get("ok") is True, prepared

        anchor_set = await chat.evaluate(
            _set_anchor_js(seed),
            intent=EvaluateIntent.SYNC_PROBE,
        )
        assert isinstance(anchor_set, dict) and anchor_set.get("ok") is True, anchor_set

        binding = await chat.evaluate(
            """(() => ({
              apiBase: window.__MYRM_E2E_API_BASE__ ?? null,
              runtimeApi: window.__MYRM_E2E_RUNTIME__?.apiBase ?? null,
              directSse: !!window.__MYRM_E2E_DIRECT_SSE__,
            }))()""",
            intent=EvaluateIntent.SYNC_PROBE,
        )
        assert isinstance(binding, dict), binding
        bound_api = str(
            binding.get("apiBase") or binding.get("runtimeApi") or ""
        ).rstrip("/")
        assert bound_api == api_base.rstrip(
            "/"
        ), f"SHPOIB API binding mismatch: expected {api_base}, got {binding!r}"

        workspace_ready = await chat.evaluate(
            WAIT_WORKSPACE_STREAM_JS,
            intent=EvaluateIntent.AGENT_SUBMIT,
        )
        assert (
            isinstance(workspace_ready, dict) and workspace_ready.get("ok") is True
        ), f"workspace stream not ready: {workspace_ready!r}; api={api_base}"

        toast_state, sse_events, send_result, diag = (
            await _send_and_collect_migration_gap(
                chat,
                api_base=api_base,
                seed=seed,
                wall_deadline=wall_deadline,
                gap_pattern=gap_pattern,
                gap_timeout_sec=90.0,
                require_assistant_reply=False,
            )
        )

        recorded_sse = list(sse_events)
        if "capability_gap" not in recorded_sse:
            all_sse = diag.get("allSse")
            if isinstance(all_sse, list):
                recorded_sse = [str(item) for item in all_sse]

        migration_toast = int(toast_state.get("migrationCount") or 0)
        if migration_toast < 1 and "capability_gap" not in recorded_sse:
            pytest.fail(
                "expected migration readiness toast or capability_gap SSE in browser; "
                f"send={send_result!r}; sse={recorded_sse!r}; toast={toast_state!r}; "
                f"diag={diag!r}; seed={seed!r}"
            )

        chat_id = str(send_result.get("chatId") or "").strip()
        if not chat_id:
            turn = diag.get("turn") if isinstance(diag.get("turn"), dict) else {}
            chat_id = str(turn.get("chatId") or "").strip()
        assert (
            chat_id
        ), f"missing chat id after send; send={send_result!r}; diag={diag!r}"
        assert (
            send_result.get("ok") is True
        ), f"send turn failed: {send_result!r}; diag={diag!r}"

        if chat_id:
            e2e_resource_ledger.register("chat", chat_id)
    finally:
        if page is not None:
            try:
                await asyncio.to_thread(client.close_page, page, ignore_errors=True)
            except RuntimeError:
                pass
        if owns_client:
            await asyncio.to_thread(client.close)


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(600)
async def test_migration_readiness_gap_chrome_e2e_mcp_warning(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Post-import mcp_warning readiness: toast + capability_gap SSE on first chat."""
    await _run_migration_readiness_gap_e2e(
        variant="mcp_warning",
        expected_readiness="warning",
        gap_pattern=_MIGRATION_GAP_TOAST_PATTERN,
        e2e_resource_ledger=e2e_resource_ledger,
    )


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(600)
async def test_migration_readiness_gap_chrome_e2e_provider_critical(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Post-import provider_critical readiness: critical toast + capability_gap SSE."""
    await _run_migration_readiness_gap_e2e(
        variant="provider_critical",
        expected_readiness="critical",
        gap_pattern=_MIGRATION_CRITICAL_GAP_TOAST_PATTERN,
        e2e_resource_ledger=e2e_resource_ledger,
    )


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.asyncio
@pytest.mark.timeout(600)
async def test_migration_readiness_gap_chrome_e2e_diagnostic_critical(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Post-import diagnostic_critical readiness: critical toast + capability_gap SSE."""
    await _run_migration_readiness_gap_e2e(
        variant="diagnostic_critical",
        expected_readiness="critical",
        gap_pattern=_MIGRATION_CRITICAL_GAP_TOAST_PATTERN,
        e2e_resource_ledger=e2e_resource_ledger,
    )
