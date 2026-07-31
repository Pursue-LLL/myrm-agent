"""Chrome LIVE_AGENT E2E: Fast + search_depth deep/normal → web_fetch spill → file_read_tool."""

from __future__ import annotations

import asyncio
import contextlib
import json
import os
import sys
import time
import urllib.error
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    E2E_API_BINDING_PROBE_JS,
    WAIT_WORKSPACE_STREAM_JS,
    chat_user_message_count,
    fetch_chat_messages,
    fetch_config_value,
    get_e2e_api_url,
    put_config_value,
    require_e2e_api_binding_probe,
    shared_hot_e2e_api_base,
    wait_e2e_provider_ready,
)
from e2e_orchestrator import (  # noqa: E402
    assert_phase_budget,
    remaining_wall_sec,
    touch_wall_progress,
)
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_mcp_e2e import http_json, open_mcp_page_async  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease
from tests.support.test_secrets import resolve_test_env  # noqa: E402

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

_MAX_TRANSPORT_ATTEMPTS = 3
_TRANSPORT_RETRY_MARKERS: tuple[str, ...] = (
    "MUX_RECLAIM_STALL",
    "MUX_TRANSPORT",
    "E2E_MUX_TRANSPORT",
    "open_mcp_page",
    "bridge-ready-timeout",
    "E2E_SHARED_UI_SESSION_BRIDGE",
    "detached",
    "transport unavailable",
    "transport closed",
    "wall budget exhausted",
    "reset_after_orphan",
    "KeyboardInterrupt",
)


def _is_transport_retryable(exc: BaseException) -> bool:
    text = str(exc)
    if "E2E_MUX_TRANSPORT_EXHAUSTED" in text:
        return True
    try:
        from mcp_chat_ui import is_mux_parallel_fail_fast
    except ImportError:
        return True
    if is_mux_parallel_fail_fast(exc):
        return False
    return any(marker in text for marker in _TRANSPORT_RETRY_MARKERS)


async def _force_mux_heal_before_retry() -> None:
    from mux_attach_force_restart import force_mux_attach_restart_scoped

    await asyncio.to_thread(
        force_mux_attach_restart_scoped,
        reason="fast_search evicted_read outer transport retry",
    )
    await asyncio.sleep(3.0)


async def _pre_open_mux_heal_if_parallel() -> None:
    from tests.support.chrome_mcp_e2e import _parallel_open_page_peer_count

    if await asyncio.to_thread(_parallel_open_page_peer_count) >= 2:
        await _force_mux_heal_before_retry()

_DEEP_SEARCH_PROMPT = (
    "Deep search E2E: Who created the Python programming language? "
    "Use web search, then web_fetch_tool on the Wikipedia Python article "
    "(https://en.wikipedia.org/wiki/Python_(programming_language)) for full text. "
    "If web_fetch output is truncated with a .context/.../evicted/ footer, "
    "call file_read_tool on that path before answering. "
    "Reply in one short English paragraph mentioning Guido van Rossum."
)

_NORMAL_SEARCH_PROMPT = (
    "Fast search E2E: Who created the Python programming language? "
    "Use web search, then web_fetch_tool on the Wikipedia Python article "
    "(https://en.wikipedia.org/wiki/Python_(programming_language)) for full text. "
    "If web_fetch output is truncated with a .context/.../evicted/ footer, "
    "call file_read_tool on that path before answering. "
    "Reply in one short English paragraph mentioning Guido van Rossum."
)


def _prep_fast_search_js(search_depth: str) -> str:
    depth_json = json.dumps(search_depth)
    return f"""(async () => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return {{ ok: false, err: 'no-bridge' }};
  bridge.abortActiveStream?.();
  bridge.releaseActiveStreamForApiResume?.();
  await bridge.ensureProviders?.();
  if (bridge.syncSearchServicesFromE2eApi) {{
    const searchSync = await bridge.syncSearchServicesFromE2eApi();
    if (!searchSync?.ok) {{
      return {{ ok: false, err: 'search-sync-failed', searchSync }};
    }}
  }}
  if (bridge.pinLiteModelForE2e) {{
    await bridge.pinLiteModelForE2e({{ preserveActionMode: true }});
  }}
  bridge.setActionMode?.('fast');
  bridge.setSearchDepth?.({depth_json});
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const debug = bridge.debugProviderState?.() ?? {{}};
  return {{
    ok: bridge.getActionMode?.() === 'fast' && bridge.getSearchDepth?.() === {depth_json},
    actionMode: bridge.getActionMode?.(),
    searchDepth: bridge.getSearchDepth?.(),
    model: debug.selection?.model ?? debug.agentModelSelection?.model ?? null,
    providerId: debug.selection?.providerId ?? null,
    apiBase: window.__MYRM_E2E_API_BASE__ ?? window.__MYRM_E2E_RUNTIME__?.apiBase ?? null,
  }};
}})()"""


def _prep_fast_search_light_js(search_depth: str) -> str:
    """Light prep after server-side ensure — skip ensureProviders/syncSearch MUX."""
    depth_json = json.dumps(search_depth)
    return f"""(() => {{
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge) return {{ ok: false, err: 'no-bridge' }};
  bridge.abortActiveStream?.();
  bridge.releaseActiveStreamForApiResume?.();
  bridge.setActionMode?.('fast');
  bridge.setSearchDepth?.({depth_json});
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const debug = bridge.debugProviderState?.() ?? {{}};
  return {{
    ok: bridge.getActionMode?.() === 'fast' && bridge.getSearchDepth?.() === {depth_json},
    actionMode: bridge.getActionMode?.(),
    searchDepth: bridge.getSearchDepth?.(),
    model: debug.selection?.model ?? debug.agentModelSelection?.model ?? null,
    providerId: debug.selection?.providerId ?? null,
    apiBase: window.__MYRM_E2E_API_BASE__ ?? window.__MYRM_E2E_RUNTIME__?.apiBase ?? null,
  }};
}})()"""


def _kickoff_fast_search_js(prompt: str) -> str:
    return f"""(async () => {{
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return {{ ok: false, err: 'no-sendChatMessage' }};
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const result = await bridge.sendChatMessage({json.dumps(prompt)}, {{
    baselineUserCount: usersBefore,
    waitForStreamCompletion: false,
    preserveActionMode: true,
  }});
  return {{ ...result, usersBefore, chatId: bridge.turnSnapshot?.().chatId ?? result.chatId ?? null, streamRequestMessageId: bridge.debugProviderState?.()?.streamRequestMessageId ?? null }};
}})()"""


_VERIFY_FAST_SEARCH_PROGRESS_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.getFastSearchProgressSnapshot) {
    return { ready: false, err: 'no-progress-snapshot' };
  }
  const snap = bridge.getFastSearchProgressSnapshot();
  const toolNames = snap.toolNames || [];
  const hasWebFetch = toolNames.includes('web_fetch_tool');
  const hasFileRead = toolNames.includes('file_read_tool');
  const spillNeedsRead = (snap.evictedRefs || []).length > 0;
  const readOk = !spillNeedsRead || hasFileRead;
  const done = !snap.isStreaming && snap.hasAssistant && (snap.contentSample || '').trim().length > 20;
  return {
    ready: done && hasWebFetch && readOk,
    done,
    isStreaming: snap.isStreaming,
    hasWebFetch,
    hasFileRead,
    spillNeedsRead,
    evictedRefs: snap.evictedRefs || [],
    toolNames,
    contentSample: snap.contentSample || '',
    mentionsGuido: Boolean(snap.mentionsGuido),
    source: 'ui',
  };
})()"""


def _search_configs_from_value(value: dict[str, object]) -> list[dict[str, object]]:
    configs = value.get("searchServiceConfigs")
    if not isinstance(configs, list):
        return []
    return [item for item in configs if isinstance(item, dict)]


def _try_fetch_shared_config(config_key: str) -> dict[str, object] | None:
    """Read shared hot config when :8080 is reachable; None during parallel stack heal."""
    try:
        value = fetch_config_value(config_key, api_url=shared_hot_e2e_api_base())
    except (OSError, urllib.error.URLError, TimeoutError):
        return None
    return value if isinstance(value, dict) else None


def _fetch_config_resilient(
    config_key: str, api_url: str, *, attempts: int = 5
) -> dict[str, object]:
    last_exc: BaseException | None = None
    for attempt in range(attempts):
        try:
            value = fetch_config_value(config_key, api_url=api_url)
            return value if isinstance(value, dict) else {}
        except (OSError, urllib.error.URLError, TimeoutError) as exc:
            last_exc = exc
            if attempt + 1 >= attempts:
                raise
            time.sleep(2.0 * (attempt + 1))
    if last_exc is not None:
        raise last_exc
    return {}


def _minimal_e2e_search_services() -> dict[str, object]:
    """Minimal searchServices for SHPOIB when shared :8080 has no configs."""
    search_service = resolve_test_env("SEARCH_SERVICE", "tavily") or "tavily"
    api_key = resolve_test_env("TAVILY_API_KEY") or resolve_test_env(
        "SEARCH_API_KEY", ""
    )
    item: dict[str, object] = {
        "id": f"e2e-search-{uuid.uuid4().hex[:8]}",
        "name": "E2E Search",
        "enabled": True,
        "priority": 1,
        "search_service": search_service,
        "api_key": api_key or "test-tavily-key",
        "createdAt": int(time.time() * 1000),
    }
    if search_service == "searxng":
        item["api_base"] = resolve_test_env("SEARXNG_URL")
        item["extra_params"] = {
            "categories": resolve_test_env("SEARXNG_ENGINE") or "general",
            "language": "all",
        }
    return {"searchServiceConfigs": [item]}


def _wait_search_services_persisted(
    api_base: str, *, timeout_sec: float = 15.0
) -> list[dict[str, object]]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        last = fetch_config_value("searchServices", api_url=api_base)
        configs = _search_configs_from_value(last)
        if configs:
            return configs
        time.sleep(0.5)
    pytest.fail(
        f"searchServices not persisted on {api_base} after seed; last={json.dumps(last, ensure_ascii=False)}"
    )


def _ensure_private_search_configured(api_base: str) -> None:
    """SHPOIB private pools start empty; mirror shared :8080 or seed minimal search."""
    private = _fetch_config_resilient("searchServices", api_base)
    if _search_configs_from_value(private):
        return
    shared = _try_fetch_shared_config("searchServices")
    if shared and _search_configs_from_value(shared):
        put_config_value("searchServices", shared, api_url=api_base)
    else:
        put_config_value(
            "searchServices", _minimal_e2e_search_services(), api_url=api_base
        )
    _wait_search_services_persisted(api_base)


def _ensure_private_providers_configured(api_base: str) -> None:
    """Mirror shared providers + pin fastModeModel to lite primary for fast-mode E2E."""
    shared = _try_fetch_shared_config("providers")
    if not shared:
        return
    lite_primary = (
        shared.get("defaultModelConfig", {}).get("liteModel", {}).get("primary")
        if isinstance(shared.get("defaultModelConfig"), dict)
        else None
    )
    merged = dict(shared)
    if (
        isinstance(lite_primary, dict)
        and lite_primary.get("providerId")
        and lite_primary.get("model")
    ):
        dmc = dict(merged.get("defaultModelConfig") or {})
        dmc["fastModeModel"] = {
            "primary": lite_primary,
            "fallback": None,
            "temperature": (
                dmc.get("baseModel", {}).get("temperature", 0.7)
                if isinstance(dmc.get("baseModel"), dict)
                else 0.7
            ),
            "modelKwargs": (
                dmc.get("baseModel", {}).get("modelKwargs", {})
                if isinstance(dmc.get("baseModel"), dict)
                else {}
            ),
        }
        merged["defaultModelConfig"] = dmc
    put_config_value("providers", merged, api_url=api_base)


def _expected_fast_e2e_model(api_base: str) -> dict[str, str]:
    """Return fastModeModel (or liteModel) primary configured for fast-mode E2E."""
    providers = fetch_config_value("providers", api_url=api_base)
    if not isinstance(providers, dict):
        pytest.fail(f"providers config missing on {api_base}")
    dmc = providers.get("defaultModelConfig")
    if not isinstance(dmc, dict):
        pytest.fail(f"defaultModelConfig missing on {api_base}")
    fast_primary: dict[str, object] | None = None
    fast_mode = dmc.get("fastModeModel")
    if isinstance(fast_mode, dict):
        primary = fast_mode.get("primary")
        if isinstance(primary, dict):
            fast_primary = primary
    if fast_primary is None:
        lite = dmc.get("liteModel")
        if isinstance(lite, dict):
            primary = lite.get("primary")
            if isinstance(primary, dict):
                fast_primary = primary
    if (
        not isinstance(fast_primary, dict)
        or not fast_primary.get("providerId")
        or not fast_primary.get("model")
    ):
        pytest.fail(
            "fast/lite model primary not configured on "
            f"{api_base}: {json.dumps(dmc, ensure_ascii=False)}"
        )
    return {
        "providerId": str(fast_primary["providerId"]),
        "model": str(fast_primary["model"]),
    }


def _api_deep_search_progress(chat_id: str, api_base: str) -> dict[str, object]:
    messages: list[dict[str, object]] | None = None
    last_io: OSError | None = None
    for attempt in range(3):
        try:
            messages = fetch_chat_messages(chat_id, api_url=api_base)
            break
        except OSError as exc:
            last_io = exc
            if attempt + 1 < 3:
                time.sleep(1.5 * (attempt + 1))
    if messages is None:
        return {
            "ready": False,
            "err": "api-io",
            "source": "api",
            "detail": str(last_io or "")[:120],
        }
    if not messages:
        return {"ready": False, "err": "no-messages", "source": "api"}
    user_count = sum(1 for m in messages if m.get("role") == "user")
    assistant = next(
        (m for m in reversed(messages) if m.get("role") == "assistant"),
        None,
    )
    if not isinstance(assistant, dict):
        return {
            "ready": False,
            "err": "no-assistant",
            "userCount": user_count,
            "source": "api",
        }
    meta = (
        assistant.get("metadata") if isinstance(assistant.get("metadata"), dict) else {}
    )
    steps = (
        meta.get("progressSteps") if isinstance(meta.get("progressSteps"), list) else []
    )
    tool_names = [str(s.get("tool_name") or "") for s in steps if isinstance(s, dict)]
    evicted_refs = [
        str(s.get("evicted_file_ref"))
        for s in steps
        if isinstance(s, dict) and isinstance(s.get("evicted_file_ref"), str)
    ]
    content = str(assistant.get("content") or "")
    completion = str(meta.get("completionStatus") or "")
    has_web_fetch = "web_fetch_tool" in tool_names
    has_file_read = "file_read_tool" in tool_names
    spill_needs_read = len(evicted_refs) > 0
    read_ok = not spill_needs_read or has_file_read
    done = completion == "complete" and len(content.strip()) > 20
    return {
        "ready": done and has_web_fetch and read_ok,
        "done": done,
        "hasWebFetch": has_web_fetch,
        "hasFileRead": has_file_read,
        "spillNeedsRead": spill_needs_read,
        "evictedRefs": evicted_refs,
        "toolNames": tool_names,
        "contentSample": content[:240],
        "mentionsGuido": "Guido van Rossum" in content,
        "source": "api",
    }


def _ui_eval_is_transient(exc: BaseException) -> bool:
    msg = str(exc).lower()
    return any(
        token in msg
        for token in (
            "econnrefused",
            "could not connect to chrome",
            "chrome mcp",
            "timed out",
            "mux",
            "page cleanup failed",
        )
    )


async def _poll_fast_search_progress(
    chat: McpChatSession,
    chat_id: str,
    api_base: str,
) -> tuple[dict[str, object], dict[str, object]]:
    """UI-first progress; on Chrome/MCP flake fall back to private API messages."""
    ui_last: dict[str, object] = {"ready": False, "source": "ui"}
    touch_wall_progress(current_node="fast_search_poll_ui_eval")
    try:
        raw = await asyncio.wait_for(
            chat.evaluate(
                _VERIFY_FAST_SEARCH_PROGRESS_JS,
                await_promise=False,
                recv_timeout=45.0,
            ),
            timeout=50.0,
        )
        ui_last = raw if isinstance(raw, dict) else {"value": raw, "source": "ui"}
        ui_last.setdefault("source", "ui")
    except (RuntimeError, TimeoutError, asyncio.TimeoutError) as exc:
        ui_last = {
            "ready": False,
            "source": "ui",
            "err": "ui-eval-failed",
            "transient": isinstance(exc, RuntimeError) and _ui_eval_is_transient(exc),
            "detail": str(exc)[:240],
        }
    touch_wall_progress(current_node="fast_search_poll_api_probe")
    api_last = _api_deep_search_progress(chat_id, api_base)
    return ui_last, api_last


def _merge_fast_search_progress(
    ui_last: dict[str, object],
    api_last: dict[str, object],
) -> dict[str, object]:
    if ui_last.get("ready") is True:
        return ui_last
    if api_last.get("ready") is True:
        return api_last
    if ui_last.get("err") in ("ui-eval-failed", "no-progress-snapshot"):
        return api_last
    return ui_last


_TRANSIENT_KICKOFF_ERRORS = (
    "send-kickoff-no-progress",
    "send-message-settled-without-progress",
    "send-turn-observe-timeout",
    "session-reset-during-submit",
    "no-sendChatMessage",
    "no-bridge",
    "no-retryStreamWithSameMessageId",
)

_FAST_SEARCH_ABORT_STREAM_JS = """(() => {
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const bridge = window.__MYRM_E2E_CHAT__;
  bridge?.abortActiveStream?.();
  bridge?.releaseActiveStreamForApiResume?.();
  return { ok: true };
})()"""

_SYNC_PRIVATE_SEARCH_JS = """(async () => {
  delete window.__MYRM_E2E_BLOCK_SEARCH_SYNC__;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.syncSearchServicesFromE2eApi) {
    return { ok: false, err: 'no-bridge', phase: 'SEARCH_POLICY' };
  }
  const deadline = Date.now() + 15000;
  while (Date.now() < deadline) {
    const sync = await bridge.syncSearchServicesFromE2eApi();
    if (sync?.ok && (sync.count ?? 0) > 0) {
      return { ok: true, count: sync.count, phase: 'SEARCH_POLICY' };
    }
    await new Promise((resolve) => setTimeout(resolve, 500));
  }
  return { ok: false, err: 'empty-search-configs', phase: 'SEARCH_POLICY' };
})()"""

_IN_PAGE_RESET_CHAT_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (bridge?.resetChat) {
    bridge.resetChat();
    return { ok: true, mode: 'bridge-reset' };
  }
  if (document.querySelector('[data-chat-input]')) {
    return { ok: true, mode: 'already' };
  }
  return { ok: false, mode: 'no-bridge' };
})()"""


def _fast_search_attach_js(chat_id: str) -> str:
    chat_id_json = json.dumps(chat_id)
    return f"""(async () => {{
  window.__MYRM_E2E_DIRECT_SSE__ = true;
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.attachToChat) return {{ ok: false, err: 'no-bridge' }};
  await bridge.attachToChat({chat_id_json});
  const snap = bridge.turnSnapshot?.() ?? {{}};
  return {{
    ok: snap.chatId === {chat_id_json},
    chatId: snap.chatId ?? null,
    userCount: snap.userCount ?? 0,
  }};
}})()"""


async def _abort_fast_search_stream(chat: McpChatSession) -> None:
    try:
        await chat.evaluate(
            _FAST_SEARCH_ABORT_STREAM_JS,
            await_promise=False,
            recv_timeout=15.0,
        )
    except (RuntimeError, TimeoutError):
        pass


async def _restore_fast_search_bridge_light(
    chat: McpChatSession,
    base_url: str,
    *,
    chat_id: str = "",
) -> dict[str, object]:
    """Re-bind bridge after MUX orphan without shared-ui SEARCH_POLICY contract."""
    await _abort_fast_search_stream(chat)
    ensure_binding = getattr(chat, "ensure_e2e_api_base_binding", None)
    if callable(ensure_binding):
        await ensure_binding()
    ensure_bridge = getattr(chat, "ensure_react_e2e_bridge", None)
    if callable(ensure_bridge):
        try:
            await ensure_bridge(timeout_sec=90.0)
        except TimeoutError:
            heal_shell = getattr(chat, "_heal_empty_chat_shell_for_bridge", None)
            if callable(heal_shell):
                await heal_shell()
            await ensure_bridge(timeout_sec=60.0)
    attach: dict[str, object] = {"ok": True, "skipped": True}
    normalized_chat_id = chat_id.strip()
    if normalized_chat_id:
        attach_raw = await chat.evaluate(
            _fast_search_attach_js(normalized_chat_id),
            await_promise=True,
            recv_timeout=90.0,
        )
        attach = (
            attach_raw
            if isinstance(attach_raw, dict)
            else {"ok": False, "err": attach_raw}
        )
        if attach.get("ok") is not True:
            touch_wall_progress(current_node="fast_search_bridge_nav_retry")
            ui_base = base_url.rstrip("/")
            await chat.cdp(
                "Page.navigate",
                {"url": f"{ui_base}/{normalized_chat_id}"},
                recv_timeout=120.0,
            )
            await asyncio.sleep(2.0)
            if callable(ensure_binding):
                await ensure_binding()
            if callable(ensure_bridge):
                await ensure_bridge(timeout_sec=60.0)
            attach_raw = await chat.evaluate(
                _fast_search_attach_js(normalized_chat_id),
                await_promise=True,
                recv_timeout=90.0,
            )
            attach = (
                attach_raw
                if isinstance(attach_raw, dict)
                else {"ok": False, "err": attach_raw}
            )
    search_raw = await chat.evaluate(
        _SYNC_PRIVATE_SEARCH_JS,
        await_promise=True,
        recv_timeout=45.0,
    )
    search = (
        search_raw if isinstance(search_raw, dict) else {"ok": False, "err": search_raw}
    )
    bridge_ok = attach.get("ok") is True or not normalized_chat_id
    return {
        "ok": bridge_ok and search.get("ok") is True,
        "attach": attach,
        "search": search,
        "chatId": normalized_chat_id or None,
    }


async def _soft_reset_fast_search_turn(
    chat: McpChatSession,
    base_url: str,
    *,
    light: bool = False,
    chat_id: str = "",
) -> None:
    """In-page stream reset — avoid click_new_chat/MUX during kickoff retries."""
    if light:
        await _restore_fast_search_bridge_light(chat, base_url, chat_id=chat_id)
        return
    await _abort_fast_search_stream(chat)
    await chat.ensure_chat_surface(base_url)


async def _heal_fast_search_bridge_after_mux_loss(
    chat: McpChatSession,
    *,
    api_base: str,
    chat_id: str,
    prep_js: str,
) -> dict[str, object]:
    """Restore E2E bridge + chat binding after MUX orphan/shim respawn drops window globals."""
    restored = await _restore_fast_search_bridge_light(chat, BASE_URL, chat_id=chat_id)
    if restored.get("ok") is not True:
        touch_wall_progress(current_node="fast_search_bridge_attach_retry")
        await asyncio.sleep(2.0)
        restored = await _restore_fast_search_bridge_light(
            chat, BASE_URL, chat_id=chat_id
        )
        if restored.get("ok") is not True:
            return {
                "ok": False,
                "err": "bridge-restore-failed",
                "restore": restored,
            }
    _ensure_private_search_configured(api_base)
    _ensure_private_providers_configured(api_base)
    raw_prep = await chat.evaluate(prep_js, await_promise=True, recv_timeout=90.0)
    if isinstance(raw_prep, dict) and raw_prep.get("ok") is True:
        return raw_prep
    return (
        raw_prep if isinstance(raw_prep, dict) else {"ok": False, "err": "prep-failed"}
    )


def _kickoff_debug_user_hint(kickoff: dict[str, object]) -> int:
    debug = kickoff.get("debug")
    if not isinstance(debug, dict):
        return 0
    for key in ("userCount", "apiUsers"):
        raw = debug.get(key)
        if isinstance(raw, int) and raw >= 0:
            return raw
        if isinstance(raw, str) and raw.isdigit():
            return int(raw)
    return 0


def _kickoff_api_verify_budget_sec(kickoff: dict[str, object]) -> float:
    """Allow API persistence lag after sendTurnSealed while keeping API user-row hard anchor."""
    debug = kickoff.get("debug")
    streaming = isinstance(debug, dict) and debug.get("streaming") is True
    ui_users = _kickoff_debug_user_hint(kickoff)
    # E2EChatBridge live profile seals on uiProgress && (apiOk || streaming) — see sendTurnSealed.
    if kickoff.get("ok") is True and streaming:
        return 180.0
    if kickoff.get("ok") is True and ui_users >= 1:
        return 120.0
    return 60.0


async def _kickoff_fast_search_with_retries(
    chat: McpChatSession,
    *,
    api_base: str,
    prep_js: str,
    kickoff_js: str,
    prep: dict[str, object],
    chat_id: str = "",
    max_attempts: int = 5,
) -> tuple[dict[str, object], dict[str, object]]:
    kickoff: dict[str, object] | None = None
    for kickoff_attempt in range(max_attempts):
        try:
            kickoff = await chat.evaluate(
                kickoff_js, await_promise=True, recv_timeout=120.0
            )
        except RuntimeError as exc:
            exc_msg = str(exc)
            mux_transient = (
                "MUX_RECLAIM_STALL" in exc_msg
                or "MUX_EVALUATE_ORPHAN" in exc_msg
                or "orphan" in exc_msg.lower()
            )
            if kickoff_attempt + 1 < max_attempts and mux_transient:
                touch_wall_progress(current_node="fast_search_kickoff_mux_retry")
                if chat_id.strip():
                    healed_prep = await _heal_fast_search_bridge_after_mux_loss(
                        chat,
                        api_base=api_base,
                        chat_id=chat_id,
                        prep_js=prep_js,
                    )
                    if isinstance(healed_prep, dict) and healed_prep.get("ok") is True:
                        prep = healed_prep
                else:
                    await _soft_reset_fast_search_turn(chat, BASE_URL, light=True)
                    _ensure_private_search_configured(api_base)
                    _ensure_private_providers_configured(api_base)
                    raw_prep = await chat.evaluate(
                        prep_js, await_promise=True, recv_timeout=90.0
                    )
                    if isinstance(raw_prep, dict) and raw_prep.get("ok") is True:
                        prep = raw_prep
                await asyncio.sleep(2.0 * (kickoff_attempt + 1))
                continue
            raise
        if isinstance(kickoff, dict) and kickoff.get("ok") is True:
            return prep, kickoff
        transient_kickoff = (
            isinstance(kickoff, dict)
            and str(kickoff.get("err") or "") in _TRANSIENT_KICKOFF_ERRORS
        )
        if kickoff_attempt + 1 < max_attempts and transient_kickoff:
            touch_wall_progress(current_node="fast_search_kickoff_soft_retry")
            bridge_err = (
                str(kickoff.get("err") or "") if isinstance(kickoff, dict) else ""
            )
            partial_chat_id = (
                str(kickoff.get("chatId") or "").strip()
                if isinstance(kickoff, dict)
                else ""
            )
            effective_chat_id = chat_id.strip() or partial_chat_id
            if effective_chat_id and bridge_err in (
                "no-sendChatMessage",
                "no-bridge",
                "no-retryStreamWithSameMessageId",
            ):
                healed_prep = await _heal_fast_search_bridge_after_mux_loss(
                    chat,
                    api_base=api_base,
                    chat_id=effective_chat_id,
                    prep_js=prep_js,
                )
                if isinstance(healed_prep, dict) and healed_prep.get("ok") is True:
                    prep = healed_prep
                else:
                    await _soft_reset_fast_search_turn(
                        chat,
                        BASE_URL,
                        light=True,
                        chat_id=effective_chat_id,
                    )
                    _ensure_private_search_configured(api_base)
                    _ensure_private_providers_configured(api_base)
                    raw_prep = await chat.evaluate(
                        prep_js, await_promise=True, recv_timeout=90.0
                    )
                    if isinstance(raw_prep, dict) and raw_prep.get("ok") is True:
                        prep = raw_prep
            else:
                await _soft_reset_fast_search_turn(chat, BASE_URL, light=True)
                _ensure_private_search_configured(api_base)
                _ensure_private_providers_configured(api_base)
                raw_prep = await chat.evaluate(
                    prep_js, await_promise=True, recv_timeout=90.0
                )
                if isinstance(raw_prep, dict) and raw_prep.get("ok") is True:
                    prep = raw_prep
            await asyncio.sleep(2.0 * (kickoff_attempt + 1))
            continue
        break
    assert isinstance(kickoff, dict) and kickoff.get("ok") is True, kickoff
    return prep, kickoff


_UI_STREAM_REQUEST_MESSAGE_ID_JS = """(() => {
  const id = window.__MYRM_E2E_CHAT__?.debugProviderState?.()?.streamRequestMessageId;
  return typeof id === 'string' && id.trim() ? id.trim() : null;
})()"""


async def _resolve_stream_request_message_id(
    chat: McpChatSession,
    *,
    cached: str = "",
) -> str:
    """Agent-stream requestMessageId for retryStreamWithSameMessageId (UI SSOT)."""
    normalized = cached.strip()
    if normalized:
        return normalized
    try:
        raw = await chat.evaluate(
            _UI_STREAM_REQUEST_MESSAGE_ID_JS,
            await_promise=False,
            recv_timeout=15.0,
        )
    except RuntimeError:
        return ""
    return raw.strip() if isinstance(raw, str) and raw.strip() else ""


async def _recover_stalled_fast_search_turn(
    chat: McpChatSession,
    *,
    chat_id: str,
    api_base: str,
    prompt: str,
    prep_js: str,
    kickoff_js: str,
    prep: dict[str, object],
    search_depth: str,
    stream_request_message_id: str = "",
) -> tuple[dict[str, object], dict[str, object]]:
    """Resume same message_id stream before creating a duplicate user turn."""
    message_id = await _resolve_stream_request_message_id(
        chat, cached=stream_request_message_id
    )
    if message_id:
        touch_wall_progress(current_node=f"fast_{search_depth}_stream_retry")
        retry_js = f"""(async () => {{
          window.__MYRM_E2E_DIRECT_SSE__ = true;
          const bridge = window.__MYRM_E2E_CHAT__;
          if (!bridge?.retryStreamWithSameMessageId) {{
            return {{ ok: false, err: 'no-retryStreamWithSameMessageId' }};
          }}
          bridge?.releaseActiveStreamForApiResume?.();
          return await bridge.retryStreamWithSameMessageId(
            {json.dumps(prompt)},
            {json.dumps(message_id)},
          );
        }})()"""
        try:
            retry = await chat.evaluate(
                retry_js, await_promise=True, recv_timeout=120.0
            )
        except RuntimeError as exc:
            if "MUX" not in str(exc) and "orphan" not in str(exc).lower():
                raise
            touch_wall_progress(
                current_node=f"fast_{search_depth}_stream_retry_mux_heal"
            )
            prep = await _heal_fast_search_bridge_after_mux_loss(
                chat,
                api_base=api_base,
                chat_id=chat_id,
                prep_js=prep_js,
            )
            retry = {"ok": False, "err": "mux-evaluate-orphan"}
        if (
            isinstance(retry, dict)
            and retry.get("ok") is True
            and retry.get("busy") is not True
        ):
            return prep, {
                "ok": True,
                "chatId": chat_id,
                "mode": "stream-retry",
                "retry": retry,
            }
        bridge_retry_err = (
            str(retry.get("err") or "") if isinstance(retry, dict) else ""
        )
        if bridge_retry_err in (
            "no-bridge",
            "no-retryStreamWithSameMessageId",
            "mux-evaluate-orphan",
        ):
            touch_wall_progress(
                current_node=f"fast_{search_depth}_stream_retry_bridge_heal"
            )
            prep = await _heal_fast_search_bridge_after_mux_loss(
                chat,
                api_base=api_base,
                chat_id=chat_id,
                prep_js=prep_js,
            )
    touch_wall_progress(current_node=f"fast_{search_depth}_stall_kickoff_retry")
    return await _kickoff_fast_search_with_retries(
        chat,
        api_base=api_base,
        prep_js=prep_js,
        kickoff_js=kickoff_js,
        prep=prep,
        chat_id=chat_id,
    )


async def _progress_heartbeat(*, stop: asyncio.Event, current_node: str) -> None:
    """Keep hung-reap node progress fresh while blocking CDP/mux operations."""
    while not stop.is_set():
        touch_wall_progress(current_node=current_node)
        heartbeat_e2e_lease()
        try:
            await asyncio.wait_for(stop.wait(), timeout=12.0)
        except TimeoutError:
            continue


async def _evaluate_prep_sync(
    chat: McpChatSession,
    prep_js: str,
    *,
    timeout_sec: float,
) -> object:
    """Sync CDP evaluate for light prep — avoids async orphan reset 120s chain."""

    def _run() -> object:
        client = chat._client
        page = chat._page
        return client.evaluate(page, prep_js, timeout_sec=timeout_sec)

    return await asyncio.to_thread(_run)


async def _wait_mux_before_blocking_cdp(*, current_node: str) -> None:
    """Queue mux transport turn before bootstrap/evaluate under parallel signoff load."""
    from tests.support.chrome_mcp_e2e import _parallel_open_page_peer_count

    if await asyncio.to_thread(_parallel_open_page_peer_count) < 2:
        return
    from dev_gate_contract import signoff_mux_transport_wait_budget_sec
    from e2e_mux_transport_queue import wait_mux_transport_turn

    await asyncio.to_thread(
        wait_mux_transport_turn,
        budget_sec=signoff_mux_transport_wait_budget_sec(),
        current_node=current_node,
    )


async def _hydrate_fast_search_chat_after_page_open(chat: McpChatSession) -> None:
    """Single mux-gated bootstrap + post-hydrate verify (R224/R225 — no second mux wait)."""
    import sys

    from cdp_chat_support import (
        shpoib_parallel_shell_timeout_sec,
        signoff_parallel_force_chat_timeout_sec,
    )

    api_base = get_e2e_api_url()
    bootstrap_timeout = shpoib_parallel_shell_timeout_sec(240.0)
    bridge_timeout = signoff_parallel_force_chat_timeout_sec(90.0)
    stop = asyncio.Event()
    heartbeat = asyncio.create_task(
        _progress_heartbeat(stop=stop, current_node="fast_search_hydrate")
    )
    try:
        await _wait_mux_before_blocking_cdp(current_node="fast_search_hydrate")
        for attempt in range(3):
            touch_wall_progress(current_node="fast_search_hydrate")
            try:
                if attempt == 0:
                    await chat.bootstrap(
                        BASE_URL,
                        timeout_sec=bootstrap_timeout,
                        navigate=False,
                    )
                else:
                    reset_raw = await chat.evaluate(
                        _IN_PAGE_RESET_CHAT_JS,
                        await_promise=False,
                        recv_timeout=15.0,
                    )
                    if not isinstance(reset_raw, dict) or reset_raw.get("ok") is not True:
                        raise RuntimeError(f"in-page reset failed: {reset_raw!r}")
                    await asyncio.sleep(0.5)
                    await chat.ensure_e2e_api_base_binding()
                    await chat.ensure_react_e2e_bridge(timeout_sec=bridge_timeout)
                await _wait_mux_before_blocking_cdp(
                    current_node="fast_search_hydrate_eval"
                )
                touch_wall_progress(current_node="fast_search_hydrate_eval")
                print(
                    "E2E_FAST_SEARCH_HYDRATE: phase=provider_gate",
                    file=sys.stderr,
                    flush=True,
                )

                def _provider_gate_sync() -> None:
                    if not wait_e2e_provider_ready(
                        api_url=api_base, timeout_sec=90.0
                    ):
                        raise RuntimeError(
                            f"SHPOIB provider not ready before hydrate on {api_base}"
                        )
                    _ensure_private_search_configured(api_base)
                    _ensure_private_providers_configured(api_base)

                await asyncio.to_thread(_provider_gate_sync)
                print(
                    "E2E_FAST_SEARCH_HYDRATE: phase=done",
                    file=sys.stderr,
                    flush=True,
                )
                return
            except (TimeoutError, RuntimeError) as exc:
                msg = str(exc)
                retriable = (
                    "MUX_RECLAIM_STALL" in msg
                    or "Chat shell not ready" in msg
                    or "bridge-ready-timeout" in msg
                    or "E2E_SHARED_UI_SESSION_BRIDGE" in msg
                    or "in-page reset failed" in msg
                    or "provider not ready" in msg
                )
                if not retriable or attempt + 1 >= 3:
                    raise
                touch_wall_progress(current_node="fast_search_hydrate_retry")
                try:
                    client = getattr(chat, "_client", None)
                    if client is not None:
                        await asyncio.to_thread(client.recover_mux_transport)
                except RuntimeError:
                    pass
                await _wait_mux_before_blocking_cdp(
                    current_node="fast_search_hydrate_retry"
                )
                await asyncio.sleep(3.0 * (attempt + 1))
    finally:
        stop.set()
        heartbeat.cancel()
        with contextlib.suppress(asyncio.CancelledError):
            await heartbeat


async def _assert_e2e_api_binding(chat: McpChatSession, api_base: str) -> None:
    """Verify WebUI streams to the SHPOIB private API (same gate as config_gap signoff)."""
    last_exc: BaseException | None = None
    for attempt in range(3):
        await _wait_mux_before_blocking_cdp(current_node="fast_search_api_binding")
        touch_wall_progress(current_node="fast_search_api_binding")
        try:
            await chat.ensure_e2e_api_base_binding()
            raw = await chat.evaluate(
                E2E_API_BINDING_PROBE_JS,
                await_promise=False,
                recv_timeout=15.0,
            )
            require_e2e_api_binding_probe(raw, api_base)
            return
        except (TimeoutError, RuntimeError) as exc:
            last_exc = exc
            msg = str(exc)
            retriable = (
                "MUX_RECLAIM_STALL" in msg
                or "MUX_EVALUATE_ORPHAN" in msg
                or "reset_after_orphan" in msg
                or "transport unavailable" in msg
            )
            if not retriable or attempt + 1 >= 3:
                raise
            touch_wall_progress(current_node="fast_search_api_binding_retry")
            try:
                client = getattr(chat, "_client", None)
                if client is not None:
                    await asyncio.to_thread(client.recover_mux_transport)
            except RuntimeError:
                pass
            await asyncio.sleep(2.0 * (attempt + 1))
    if last_exc is not None:
        raise last_exc


async def _run_fast_evicted_read_live_e2e_once(
    e2e_resource_ledger: E2EResourceLedger,
    *,
    search_depth: str,
    prompt: str,
) -> None:
    """Single attempt: open owned page + LIVE fast search flow."""
    api_base = get_e2e_api_url()
    expected_api_origin = urlparse(api_base).netloc
    prep_js = _prep_fast_search_light_js(search_depth)
    prep_js_full = _prep_fast_search_js(search_depth)
    kickoff_js = _kickoff_fast_search_js(prompt)

    async def _run_flow(chat: McpChatSession) -> None:
        model_used = "unknown"
        await _hydrate_fast_search_chat_after_page_open(chat)
        if not await asyncio.to_thread(
            wait_e2e_provider_ready, api_url=api_base, timeout_sec=90.0
        ):
            pytest.fail(
                f"SHPOIB provider not ready after bootstrap on {api_base} "
                "(mux heal race — do not stop other pytest)"
            )

        prep: dict[str, object] | None = None
        prep_stop = asyncio.Event()
        prep_heartbeat = asyncio.create_task(
            _progress_heartbeat(stop=prep_stop, current_node="fast_search_prep")
        )
        try:
            for prep_attempt in range(3):
                await asyncio.to_thread(_ensure_private_search_configured, api_base)
                await asyncio.to_thread(_ensure_private_providers_configured, api_base)
                await _wait_mux_before_blocking_cdp(current_node="fast_search_prep")
                touch_wall_progress(current_node="fast_search_prep")
                import sys

                print(
                    f"E2E_FAST_SEARCH_PREP: phase=evaluate attempt={prep_attempt + 1}",
                    file=sys.stderr,
                    flush=True,
                )
                from cdp_chat_support import signoff_parallel_force_chat_timeout_sec

                prep_timeout = signoff_parallel_force_chat_timeout_sec(90.0)
                try:
                    await chat.dismiss_modals()
                except RuntimeError as exc:
                    if "MUX_RECLAIM_STALL" not in str(exc) and "new_page failed" not in str(
                        exc
                    ):
                        raise
                try:
                    raw_prep = await asyncio.wait_for(
                        _evaluate_prep_sync(
                            chat,
                            prep_js,
                            timeout_sec=min(prep_timeout, 25.0),
                        ),
                        timeout=min(prep_timeout, 30.0),
                    )
                except (TimeoutError, RuntimeError) as prep_exc:
                    prep_msg = str(prep_exc)
                    if prep_attempt + 1 >= 3 or not any(
                        token in prep_msg
                        for token in (
                            "MUX_RECLAIM_STALL",
                            "MUX_EVALUATE_ORPHAN",
                            "reset_after_orphan",
                            "transport unavailable",
                        )
                    ):
                        raise
                    touch_wall_progress(current_node="fast_search_prep_mux_retry")
                    try:
                        client = getattr(chat, "_client", None)
                        if client is not None:
                            await asyncio.to_thread(client.recover_mux_transport)
                    except RuntimeError:
                        pass
                    await asyncio.sleep(2.0 * (prep_attempt + 1))
                    continue
                if isinstance(raw_prep, dict) and raw_prep.get("ok") is True:
                    prep = raw_prep
                    break
                if prep_attempt + 1 >= 2:
                    await _wait_mux_before_blocking_cdp(
                        current_node="fast_search_prep_full"
                    )
                    raw_prep = await chat.evaluate(
                        prep_js_full, await_promise=True, recv_timeout=prep_timeout
                    )
                    if isinstance(raw_prep, dict) and raw_prep.get("ok") is True:
                        prep = raw_prep
                        break
                if prep_attempt + 1 < 3:
                    await asyncio.sleep(2.0 * (prep_attempt + 1))
        finally:
            prep_stop.set()
            prep_heartbeat.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await prep_heartbeat
        assert isinstance(prep, dict) and prep.get("ok") is True, prep
        assert prep.get("actionMode") == "fast", prep
        assert prep.get("searchDepth") == search_depth, prep
        injected_api = str(prep.get("apiBase") or "")
        assert (
            expected_api_origin in injected_api
        ), f"UI must stream to SHPOIB private API {api_base}, got {injected_api!r}"
        expected_fast = _expected_fast_e2e_model(api_base)
        prep_model = str(prep.get("model") or "")
        prep_provider = str(prep.get("providerId") or "")
        model_used = prep_model or prep_provider or "unknown"
        assert prep_model == expected_fast["model"], (
            f"Fast E2E must use configured fast/lite model {expected_fast['model']!r}, "
            f"got model={prep_model!r} provider={prep_provider!r}; prep={prep}"
        )
        assert prep_provider == expected_fast["providerId"], (
            f"Fast E2E provider mismatch: expected {expected_fast['providerId']!r}, "
            f"got {prep_provider!r}; prep={prep}"
        )

        workspace_ready = await chat.evaluate(
            WAIT_WORKSPACE_STREAM_JS,
            await_promise=True,
            recv_timeout=60.0,
        )
        assert (
            isinstance(workspace_ready, dict) and workspace_ready.get("ok") is True
        ), (
            f"workspace multiplex stream not ready before fast {search_depth} send: "
            f"{workspace_ready!r}; api={api_base}"
        )
        await _assert_e2e_api_binding(chat, api_base)

        prep, kickoff = await _kickoff_fast_search_with_retries(
            chat,
            api_base=api_base,
            prep_js=prep_js,
            kickoff_js=kickoff_js,
            prep=prep,
        )
        stream_request_message_id = await _resolve_stream_request_message_id(chat)
        kickoff_stream_id = str(kickoff.get("streamRequestMessageId") or "").strip()
        if kickoff_stream_id:
            stream_request_message_id = kickoff_stream_id
        post_send_mode = await chat.evaluate(
            """(() => ({
              actionMode: window.__MYRM_E2E_CHAT__?.getActionMode?.() ?? null,
              searchDepth: window.__MYRM_E2E_CHAT__?.getSearchDepth?.() ?? null,
              lastSubmit: window.__MYRM_E2E_CHAT__?.lastSubmitResult ?? null,
            }))()""",
            await_promise=False,
            recv_timeout=15.0,
        )
        assert isinstance(post_send_mode, dict), post_send_mode
        assert (
            post_send_mode.get("actionMode") == "fast"
        ), f"send must preserve fast mode, got {post_send_mode!r}"
        assert post_send_mode.get("searchDepth") == search_depth, post_send_mode
        chat_id = str(kickoff.get("chatId") or "").strip()
        assert chat_id, kickoff
        e2e_resource_ledger.register("chat", chat_id)

        kickoff_verify_deadline = time.monotonic() + _kickoff_api_verify_budget_sec(
            kickoff
        )
        kickoff_user_count = 0
        while time.monotonic() < kickoff_verify_deadline:
            touch_wall_progress(current_node=f"fast_{search_depth}_kickoff_api_verify")
            try:
                kickoff_user_count = chat_user_message_count(chat_id, api_url=api_base)
            except OSError:
                kickoff_user_count = 0
            if kickoff_user_count >= 1:
                break
            await asyncio.sleep(2.0)
        assert kickoff_user_count >= 1, (
            f"Fast {search_depth} kickoff did not persist user turn on {api_base}; "
            f"kickoff={json.dumps(kickoff, ensure_ascii=False)}; "
            f"lastSubmit={post_send_mode.get('lastSubmit')!r}; "
            f"userCount={kickoff_user_count}"
        )

        poll_budget_sec = min(300.0, max(120.0, remaining_wall_sec() - 90.0))
        deadline = time.monotonic() + poll_budget_sec
        last: dict[str, object] = {}
        api_last: dict[str, object] = {"ready": False, "source": "api"}
        stall_retry_count = 0
        max_stall_retries = 2
        turn_started = time.monotonic()
        stream_request_message_id = await _resolve_stream_request_message_id(
            chat, cached=stream_request_message_id
        )
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            assert_phase_budget(f"fast_{search_depth}_search_poll")
            touch_wall_progress(current_node=f"fast_{search_depth}_search_poll")
            ui_last, api_last = await _poll_fast_search_progress(
                chat, chat_id, api_base
            )
            if ui_last.get("ready") is True or api_last.get("ready") is True:
                last = _merge_fast_search_progress(ui_last, api_last)
                break
            last = _merge_fast_search_progress(ui_last, api_last)
            if ui_last.get("isStreaming") is True and not stream_request_message_id:
                stream_request_message_id = await _resolve_stream_request_message_id(
                    chat
                )
            api_err = str(api_last.get("err") or "")
            elapsed_turn = time.monotonic() - turn_started
            tool_names = last.get("toolNames")
            no_tool_progress = not last.get("hasWebFetch") and not (
                isinstance(tool_names, list) and any(str(t).strip() for t in tool_names)
            )
            user_count = int(api_last.get("userCount") or 0)
            ui_streaming = ui_last.get("isStreaming") is True
            kickoff_ok = isinstance(kickoff, dict) and kickoff.get("ok") is True
            empty_kickoff_api = (
                kickoff_ok and api_err == "no-messages" and user_count < 1
            )
            api_stalled = (
                api_err in ("no-assistant", "no-messages") and user_count >= 1
            ) or empty_kickoff_api
            stalled = (
                stall_retry_count < max_stall_retries
                and no_tool_progress
                and (
                    (
                        elapsed_turn >= 90.0
                        and (ui_streaming or api_stalled)
                    )
                    or (empty_kickoff_api and elapsed_turn >= 15.0)
                )
            )
            if stalled:
                stall_retry_count += 1
                touch_wall_progress(current_node=f"fast_{search_depth}_stall_recovery")
                stream_request_message_id = await _resolve_stream_request_message_id(
                    chat, cached=stream_request_message_id
                )
                prep, kickoff = await _recover_stalled_fast_search_turn(
                    chat,
                    chat_id=chat_id,
                    api_base=api_base,
                    prompt=prompt,
                    prep_js=prep_js,
                    kickoff_js=kickoff_js,
                    prep=prep,
                    search_depth=search_depth,
                    stream_request_message_id=stream_request_message_id,
                )
                stream_request_message_id = await _resolve_stream_request_message_id(
                    chat, cached=stream_request_message_id
                )
                new_chat_id = str(kickoff.get("chatId") or chat_id).strip()
                assert new_chat_id, kickoff
                chat_id = new_chat_id
                turn_started = time.monotonic()
                continue
            if (
                elapsed_turn >= 240.0
                and no_tool_progress
                and stall_retry_count >= max_stall_retries
            ):
                pytest.fail(
                    f"Fast {search_depth} search stalled without web_fetch after {elapsed_turn:.0f}s; "
                    f"model={model_used}; stall_retries={stall_retry_count}; "
                    f"state={json.dumps(last, ensure_ascii=False)}; "
                    f"api={json.dumps(api_last, ensure_ascii=False)}"
                )
            if remaining_wall_sec() < 45.0:
                break
            for _ in range(2):
                heartbeat_e2e_lease()
                touch_wall_progress(
                    current_node=f"fast_{search_depth}_search_poll_wait"
                )
                await asyncio.sleep(1.0)

        assert last.get("ready") is True, (
            f"Fast {search_depth} search did not finish with web_fetch + file_read after spill; "
            f"model={model_used}; state={json.dumps(last, ensure_ascii=False)}; "
            f"api={json.dumps(api_last, ensure_ascii=False)}"
        )
        assert last.get("hasWebFetch") is True, last
        if last.get("spillNeedsRead"):
            assert last.get("hasFileRead") is True, last

        api_verify = _api_deep_search_progress(chat_id, api_base)
        if api_verify.get("err") != "no-messages":
            assert api_verify.get("hasWebFetch") is True, api_verify
            if api_verify.get("spillNeedsRead"):
                assert api_verify.get("hasFileRead") is True, api_verify
        elif last.get("source") == "ui":
            payload = http_json("GET", f"{api_base}/api/v1/chats/{chat_id}/messages")
            assert isinstance(payload, dict)
            data = payload.get("data")
            messages = data.get("messages") if isinstance(data, dict) else None
            assert isinstance(messages, list) and messages, "API messages missing"
            assistant = next(
                (m for m in reversed(messages) if m.get("role") == "assistant"),
                None,
            )
            assert assistant is not None
            meta = (
                assistant.get("metadata")
                if isinstance(assistant.get("metadata"), dict)
                else {}
            )
            steps = (
                meta.get("progressSteps")
                if isinstance(meta.get("progressSteps"), list)
                else []
            )
            api_tools = {
                str(s.get("tool_name") or "") for s in steps if isinstance(s, dict)
            }
            assert "web_fetch_tool" in api_tools, api_tools
            if any(isinstance(s, dict) and s.get("evicted_file_ref") for s in steps):
                assert "file_read_tool" in api_tools, api_tools

    touch_wall_progress(current_node="open_mcp_page_pending")
    from e2e_session_lifecycle import begin_bootstrap_phase

    begin_bootstrap_phase(phase_label="fast_search_page_open")
    session = await open_mcp_page_async(
        BASE_URL,
        timeout_ms=90_000,
        request_timeout_sec=180.0,
    )
    try:
        chat = McpChatSession(session.client, session.page)
        await _run_flow(chat)
    finally:
        await session.aclose()


async def _run_fast_evicted_read_live_e2e(
    e2e_resource_ledger: E2EResourceLedger,
    *,
    search_depth: str,
    prompt: str,
) -> None:
    """Shared LIVE Chrome flow for fast + normal/deep search_depth."""
    api_base = get_e2e_api_url()
    if not wait_e2e_provider_ready(api_url=api_base):
        pytest.fail(
            "Provider not ready — run ./myrm ready --chrome; WebUI must have search + LLM configured"
        )
    _ensure_private_search_configured(api_base)
    _ensure_private_providers_configured(api_base)
    private_search = fetch_config_value("searchServices", api_url=api_base)
    search_configs = (
        private_search.get("searchServiceConfigs")
        if isinstance(private_search, dict)
        else None
    )
    if not isinstance(search_configs, list) or not search_configs:
        pytest.fail(
            f"SHPOIB searchServices empty after ensure — fast+{search_depth} prep requires search config"
        )
    last_error: BaseException | None = None
    for attempt in range(1, _MAX_TRANSPORT_ATTEMPTS + 1):
        try:
            await _run_fast_evicted_read_live_e2e_once(
                e2e_resource_ledger,
                search_depth=search_depth,
                prompt=prompt,
            )
            return
        except BaseException as exc:
            last_error = exc
            if attempt >= _MAX_TRANSPORT_ATTEMPTS or not _is_transport_retryable(exc):
                raise
            touch_wall_progress(current_node="fast_search_transport_retry")
            await _force_mux_heal_before_retry()
    if last_error is not None:
        raise last_error


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE")
@pytest.mark.e2e_search_policy("hydrate_private")
@pytest.mark.integration
@pytest.mark.timeout(1140)
@pytest.mark.asyncio
async def test_fast_deep_search_web_fetch_spill_uses_file_read_in_real_ui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real WebUI: fast + deep, live LLM, web_fetch UECD spill must trigger file_read_tool."""
    await _run_fast_evicted_read_live_e2e(
        e2e_resource_ledger,
        search_depth="deep",
        prompt=_DEEP_SEARCH_PROMPT,
    )


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE")
@pytest.mark.e2e_search_policy("hydrate_private")
@pytest.mark.integration
@pytest.mark.timeout(1140)
@pytest.mark.asyncio
async def test_fast_normal_search_web_fetch_spill_uses_file_read_in_real_ui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Real WebUI: fast + normal depth, live LLM, web_fetch UECD spill must trigger file_read_tool."""
    await _run_fast_evicted_read_live_e2e(
        e2e_resource_ledger,
        search_depth="normal",
        prompt=_NORMAL_SEARCH_PROMPT,
    )
