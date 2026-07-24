"""Chrome LIVE_AGENT E2E: Fast + search_depth deep/normal → web_fetch spill → file_read_tool."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid
from pathlib import Path
from urllib.parse import urlparse

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    fetch_chat_messages,
    fetch_config_value,
    get_e2e_api_url,
    put_config_value,
    shared_hot_e2e_api_base,
    wait_e2e_provider_ready,
    WAIT_WORKSPACE_STREAM_JS,
)
from tests.support.chrome_mcp_e2e import http_json  # noqa: E402
from chrome_mcp_client import ChromeMcpClient  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402
from tests.support.test_secrets import resolve_test_env  # noqa: E402

from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

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
    await bridge.pinLiteModelForE2e();
  }}
  bridge.setActionMode?.('fast');
  bridge.setSearchDepth?.({depth_json});
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
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.sendChatMessage) return {{ ok: false, err: 'no-sendChatMessage' }};
  const usersBefore = bridge.turnSnapshot?.().userCount ?? 0;
  const result = await bridge.sendChatMessage({json.dumps(prompt)}, {{
    baselineUserCount: usersBefore,
    waitForStreamCompletion: false,
    preserveActionMode: true,
  }});
  return {{ ...result, usersBefore, chatId: bridge.turnSnapshot?.().chatId ?? result.chatId ?? null }};
}})()"""


_BRIDGE_READY_JS = """(() => ({
  hasProgressSnap: typeof window.__MYRM_E2E_CHAT__?.getFastSearchProgressSnapshot === 'function',
  hasSetSearchDepth: typeof window.__MYRM_E2E_CHAT__?.setSearchDepth === 'function',
  hasSendChatMessage: typeof window.__MYRM_E2E_CHAT__?.sendChatMessage === 'function',
}))()"""

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
        "role": "primary",
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
    private = fetch_config_value("searchServices", api_url=api_base)
    if _search_configs_from_value(private):
        return
    shared = fetch_config_value("searchServices", api_url=shared_hot_e2e_api_base())
    if _search_configs_from_value(shared):
        put_config_value("searchServices", shared, api_url=api_base)
    else:
        put_config_value(
            "searchServices", _minimal_e2e_search_services(), api_url=api_base
        )
    _wait_search_services_persisted(api_base)


def _ensure_private_providers_configured(api_base: str) -> None:
    """Mirror shared providers + pin fastModeModel to lite primary for fast-mode E2E."""
    shared = fetch_config_value("providers", api_url=shared_hot_e2e_api_base())
    if not isinstance(shared, dict):
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


def _api_deep_search_progress(chat_id: str, api_base: str) -> dict[str, object]:
    try:
        messages = fetch_chat_messages(chat_id, api_url=api_base)
    except OSError:
        return {"ready": False, "err": "api-io", "source": "api"}
    if not messages:
        return {"ready": False, "err": "no-messages", "source": "api"}
    assistant = next(
        (m for m in reversed(messages) if m.get("role") == "assistant"),
        None,
    )
    if not isinstance(assistant, dict):
        return {"ready": False, "err": "no-assistant", "source": "api"}
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
    try:
        raw = await chat.evaluate(
            _VERIFY_FAST_SEARCH_PROGRESS_JS,
            await_promise=False,
            recv_timeout=45.0,
        )
        ui_last = raw if isinstance(raw, dict) else {"value": raw, "source": "ui"}
        ui_last.setdefault("source", "ui")
    except RuntimeError as exc:
        ui_last = {
            "ready": False,
            "source": "ui",
            "err": "ui-eval-failed",
            "transient": _ui_eval_is_transient(exc),
            "detail": str(exc)[:240],
        }
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
    if ui_last.get("err") == "ui-eval-failed":
        return api_last
    return ui_last


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
    expected_api_origin = urlparse(api_base).netloc
    prep_js = _prep_fast_search_js(search_depth)
    kickoff_js = _kickoff_fast_search_js(prompt)

    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    model_used = "unknown"
    try:
        page = await asyncio.to_thread(client.new_page, BASE_URL, timeout_ms=120_000)
        chat = McpChatSession(client, page)
        await chat.bootstrap(BASE_URL, timeout_sec=120.0)
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
        await chat.ensure_e2e_api_base_binding()

        bridge_caps = await chat.evaluate(
            _BRIDGE_READY_JS, await_promise=False, recv_timeout=15.0
        )
        if not isinstance(bridge_caps, dict) or not bridge_caps.get("hasProgressSnap"):
            await chat.evaluate(
                "(() => { location.reload(); return { ok: true }; })()",
                await_promise=False,
                recv_timeout=30.0,
            )
            await asyncio.sleep(4.0)
            await chat.bootstrap(BASE_URL, timeout_sec=120.0)
            await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
            await chat.ensure_e2e_api_base_binding()

        await chat.dismiss_modals()
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL)
        await chat.ensure_e2e_api_base_binding()

        prep = await chat.evaluate(prep_js, await_promise=True, recv_timeout=90.0)
        assert isinstance(prep, dict) and prep.get("ok") is True, prep
        assert prep.get("actionMode") == "fast", prep
        assert prep.get("searchDepth") == search_depth, prep
        injected_api = str(prep.get("apiBase") or "")
        assert (
            expected_api_origin in injected_api
        ), f"UI must stream to SHPOIB private API {api_base}, got {injected_api!r}"
        model_used = str(prep.get("model") or prep.get("providerId") or "unknown")
        assert (
            "minimax" in model_used.lower() or "minimax-m" in model_used.lower()
        ), f"Fast E2E must use lite/fast model (MiniMax), got {model_used!r}; prep={prep}"

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

        kickoff = await chat.evaluate(
            kickoff_js, await_promise=True, recv_timeout=120.0
        )
        assert isinstance(kickoff, dict) and kickoff.get("ok") is True, kickoff
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

        deadline = time.monotonic() + 300.0
        last: dict[str, object] = {}
        api_last: dict[str, object] = {"ready": False, "source": "api"}
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            ui_last, api_last = await _poll_fast_search_progress(
                chat, chat_id, api_base
            )
            if ui_last.get("ready") is True or api_last.get("ready") is True:
                last = _merge_fast_search_progress(ui_last, api_last)
                break
            last = _merge_fast_search_progress(ui_last, api_last)
            await asyncio.sleep(2.0)

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
    finally:
        try:
            await asyncio.to_thread(client.close)
        except Exception:
            pass


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(720)
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


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(720)
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
