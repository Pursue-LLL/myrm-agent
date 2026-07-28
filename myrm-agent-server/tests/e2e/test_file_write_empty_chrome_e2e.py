"""Chrome E2E: empty file_write rejection — READ lane FileMutationWarning banner."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import uuid

import pytest

_LIB = os.path.join(
    os.path.dirname(__file__), "..", "..", "..", "scripts", "dev", "lib"
)
if _LIB not in sys.path:
    sys.path.insert(0, os.path.normpath(_LIB))

from cdp_chat_support import (  # noqa: E402
    ensure_e2e_yolo_mode,
    fetch_chat_messages,
    wait_e2e_provider_ready,
)
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.api.agent.utils import (  # noqa: E402
    _strip_provider_prefix,
    get_lite_model_selection,
)
from tests.support.chrome_mcp_e2e import (
    dismiss_blocking_modals,
    get_e2e_api_url,
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    reload_mcp_page,
    wait_for_state,
    warm_ui_route,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

_LIVE_EMPTY_WRITE_FILE = "live_empty_write_e2e.txt"
_LIVE_USER_PROMPT = (
    "INSTRUCTION: You MUST call tools. Do NOT reply with text only. "
    f"Call file_write_tool exactly once with path {_LIVE_EMPTY_WRITE_FILE!r} and "
    "content '' (empty string, zero bytes, no spaces). Do not use bash or file_edit_tool. "
    "Reply EMPTY_WRITE_DONE after the tool returns."
)
_FILE_WRITE_TOOL = "file_write_tool"
_MAX_CHAT_ATTEMPTS = 2


def _seed_live_workspace(api_url: str, chat_id: str) -> None:
    """Bind sandbox executor (same SSOT as file_edit batch LIVE E2E)."""
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-file-edit-batch-workspace?chat_id={chat_id}",
    )
    assert isinstance(seeded, dict)
    assert str(seeded.get("chat_id")) == chat_id

_PIN_LITE_MODEL_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.pinLiteModelForE2e) {
    return { ok: false, err: 'no-pinLiteModelForE2e' };
  }
  return bridge.pinLiteModelForE2e().then((pinned) => ({ ok: true, pinned }));
})()"""

_AGENT_READY_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const debug = bridge?.debugProviderState?.() ?? {};
  return {
    ready: !!bridge?.handleSubmit && !!debug.selection,
    selection: debug.selection ?? null,
  };
})()"""

_ENSURE_CHAT_SESSION_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  if (!bridge?.ensureChatSession) return { ok: false, err: 'no ensureChatSession' };
  return bridge.ensureChatSession().then(() => ({ ok: true }));
})()"""

_LIVE_MUTATION_BANNER_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const failures = (store?.messages || []).flatMap((msg) =>
    Array.isArray(msg.fileMutationFailures) ? msg.fileMutationFailures : [],
  );
  const bodyText = document.body?.innerText || '';
  const hasTitle = /File Modification Failed|文件修改失败/i.test(bodyText);
  const hasError = /Cannot write empty file content/i.test(bodyText)
    || failures.some((item) => String(item?.error_preview || '').includes('Cannot write empty'));
  return {
    ready: failures.length > 0 && hasTitle && hasError,
    failureCount: failures.length,
    hasTitle,
    hasError,
    sample: bodyText.slice(0, 500),
  };
})()"""

_FIXTURE_ANSWER = "Empty write E2E fixture answer."

_MUTATION_BANNER_READY_JS = f"""(() => {{
  const target = {json.dumps(_FIXTURE_ANSWER)};
  const store = window.__myrmChatStore?.getState?.();
  const msg = (store?.messages || []).find(
    (item) => item.role === 'assistant' && (item.content || '').includes(target),
  );
  const failures = Array.isArray(msg?.fileMutationFailures) ? msg.fileMutationFailures : [];
  const bodyText = document.body?.innerText || '';
  const hasTitle = /File Modification Failed|文件修改失败/i.test(bodyText);
  const hasCount = /file modification failed|文件修改失败|个文件修改失败/i.test(bodyText);
  const hasError = /Cannot write empty file content/i.test(bodyText)
    || failures.some((item) => String(item?.error_preview || '').includes('Cannot write empty'));
  return {{
    ready: failures.length > 0 && hasTitle && hasCount,
    failureCount: failures.length,
    hasTitle,
    hasCount,
    hasError,
    sample: bodyText.slice(0, 500),
  }};
}})()"""


def _seed_file_mutation_fixture(api_url: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-file-mutation-fixture?variant=empty_write",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    message_id = str(seeded.get("message_id") or "")
    ui_path = str(seeded.get("ui_path") or "")
    assert chat_id.startswith("e2efmut")
    assert len(message_id) >= 8
    assert ui_path == f"/{chat_id}"
    return seeded


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_file_write_empty_shows_mutation_warning_banner() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_file_mutation_fixture(api_url)
    chat_id = str(seeded["chat_id"])

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        message_ready = wait_for_state(
            client,
            page,
            f"""(() => {{
              const target = {json.dumps(_FIXTURE_ANSWER)};
              const store = window.__myrmChatStore?.getState?.();
              const msg = (store?.messages || []).find(
                (item) => item.role === 'assistant' && (item.content || '').includes(target),
              );
              return {{ ready: !!msg, count: store?.messages?.length ?? 0 }};
            }})()""",
            timeout_sec=90.0,
        )
        assert message_ready.get("ready") is True, json.dumps(
            message_ready,
            ensure_ascii=False,
        )

        dismiss_blocking_modals(client, page)

        banner = wait_for_state(
            client,
            page,
            _MUTATION_BANNER_READY_JS,
            timeout_sec=30.0,
        )
        assert banner.get("ready") is True, json.dumps(banner, ensure_ascii=False)
        assert int(banner.get("failureCount") or 0) >= 1

        expanded = wait_for_state(
            client,
            page,
            """(() => {
              const btn = Array.from(document.querySelectorAll('button')).find((el) => {
                const text = el.textContent || '';
                return /File Modification Failed|文件修改失败/i.test(text);
              });
              if (!btn) return { ready: false, err: 'banner-button-missing' };
              btn.click();
              const store = window.__myrmChatStore?.getState?.();
              const failures = (store?.messages || [])
                .flatMap((msg) => Array.isArray(msg.fileMutationFailures) ? msg.fileMutationFailures : []);
              const hasStoreError = failures.some((item) =>
                String(item?.error_preview || '').includes('Cannot write empty file content'),
              );
              const bodyText = document.body?.innerText || '';
              const hasDomError = /Cannot write empty file content/i.test(bodyText);
              const hasPath = /empty_write_e2e\\.txt/i.test(bodyText);
              return {
                ready: hasStoreError && (hasDomError || hasPath),
                hasStoreError,
                hasDomError,
                hasPath,
                sample: bodyText.slice(0, 500),
              };
            })()""",
            timeout_sec=15.0,
        )
        assert expanded.get("ready") is True, json.dumps(expanded, ensure_ascii=False)


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_file_write_empty_mutation_banner_survives_page_reload() -> None:
    """Hydrate from DB: reload must still show FileMutationWarning from metadata."""
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_file_mutation_fixture(api_url)
    chat_id = str(seeded["chat_id"])

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        message_ready = wait_for_state(
            client,
            page,
            f"""(() => {{
              const target = {json.dumps(_FIXTURE_ANSWER)};
              const store = window.__myrmChatStore?.getState?.();
              const msg = (store?.messages || []).find(
                (item) => item.role === 'assistant' && (item.content || '').includes(target),
              );
              return {{ ready: !!msg }};
            }})()""",
            timeout_sec=90.0,
        )
        assert message_ready.get("ready") is True, json.dumps(
            message_ready,
            ensure_ascii=False,
        )

        dismiss_blocking_modals(client, page)

        banner_before_reload = wait_for_state(
            client,
            page,
            _MUTATION_BANNER_READY_JS,
            timeout_sec=30.0,
        )
        assert banner_before_reload.get("ready") is True, json.dumps(
            banner_before_reload,
            ensure_ascii=False,
        )

        reload_mcp_page(client, page)
        dismiss_blocking_modals(client, page)

        reloaded = wait_for_state(
            client,
            page,
            _MUTATION_BANNER_READY_JS,
            timeout_sec=120.0,
        )
        assert reloaded.get("ready") is True, json.dumps(reloaded, ensure_ascii=False)


def _create_empty_write_live_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Empty Write LIVE {suffix}",
        "description": "Chrome LIVE E2E for file_write_tool empty content rejection",
        "system_prompt": (
            "You write workspace files with file_write_tool when asked. "
            "When the user specifies empty content, call file_write_tool with content exactly "
            "as an empty string. Do not substitute spaces, placeholders, or skip the tool call. "
            "Reply EMPTY_WRITE_DONE after the tool returns."
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "enabled_builtin_tools": ["code_execute"],
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


def _empty_write_failure_in_messages(chat_id: str, *, api_url: str) -> tuple[bool, bool]:
    tool_invoked = False
    has_mutation_failure = False
    for msg in fetch_chat_messages(chat_id, api_url=api_url):
        if not isinstance(msg, dict):
            continue
        blob = json.dumps(msg, ensure_ascii=False, default=str)
        if _FILE_WRITE_TOOL in blob:
            tool_invoked = True
        failures = msg.get("fileMutationFailures")
        if not isinstance(failures, list):
            meta = msg.get("metadata")
            if isinstance(meta, dict):
                failures = meta.get("fileMutationFailures")
        if isinstance(failures, list) and failures:
            for row in failures:
                if not isinstance(row, dict):
                    continue
                preview = str(row.get("error_preview") or "")
                if "Cannot write empty file content" in preview:
                    has_mutation_failure = True
        if "Cannot write empty file content" in blob:
            has_mutation_failure = True
    return tool_invoked, has_mutation_failure


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(900)
@pytest.mark.asyncio
async def test_file_write_empty_live_agent_webui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """LIVE_AGENT: real LLM calls file_write_tool with empty content → FileMutationWarning."""
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live empty-write E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome"
        )

    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url()
    ensure_e2e_yolo_mode(api_url=api_base)
    agent_id = _create_empty_write_live_agent(api_base)
    e2e_resource_ledger.register("agent", agent_id)

    async def _wait_agent_applied(
        chat: McpChatSession, *, timeout_sec: float = 90.0
    ) -> None:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            raw = await chat.evaluate(
                _AGENT_READY_JS, await_promise=False, recv_timeout=20.0
            )
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return
            await asyncio.sleep(1.0)
        raise AssertionError(f"E2E chat bridge not ready after loading agent: {last}")

    async def _pin_lite_model(chat: McpChatSession) -> dict[str, object]:
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
        pinned = await chat.evaluate(
            _PIN_LITE_MODEL_JS, await_promise=True, recv_timeout=30.0
        )
        assert isinstance(pinned, dict)
        assert pinned.get("ok") is True, f"Failed to pin lite model: {pinned}"
        expected_lite = get_lite_model_selection()
        pinned_model = pinned.get("pinned")
        assert isinstance(pinned_model, dict), f"Missing pinned model payload: {pinned}"
        assert pinned_model.get("providerId") == expected_lite["providerId"]
        assert pinned_model.get("model") == _strip_provider_prefix(
            str(expected_lite["model"])
        )
        return pinned_model

    async def _wait_turn_done(
        chat: McpChatSession,
        chat_id: str,
        *,
        timeout_sec: float = 480.0,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last_api = (False, False)
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            invoked, has_failure = _empty_write_failure_in_messages(
                chat_id, api_url=api_base
            )
            last_api = (invoked, has_failure)
            if invoked and has_failure:
                banner = await chat.evaluate(
                    _LIVE_MUTATION_BANNER_JS,
                    await_promise=False,
                    recv_timeout=20.0,
                )
                if isinstance(banner, dict) and banner.get("ready") is True:
                    return {"source": "ui+api", "banner": banner, "invoked": True}
                if time.monotonic() + 30.0 < deadline:
                    await asyncio.sleep(1.5)
                    continue
                return {
                    "source": "api",
                    "invoked": True,
                    "has_failure": True,
                    "banner": banner,
                }

            raw = await chat.evaluate(
                """(() => {
                  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
                  const text = String(snap.lastAssistantSample || '');
                  const store = window.__myrmChatStore?.getState?.();
                  const failures = (store?.messages || []).flatMap((msg) =>
                    Array.isArray(msg.fileMutationFailures) ? msg.fileMutationFailures : [],
                  );
                  return {
                    isStreaming: Boolean(snap.isStreaming),
                    hasEmptyWriteDone: /EMPTY_WRITE_DONE/i.test(text),
                    failureCount: failures.length,
                    sample: text.slice(0, 600),
                  };
                })()""",
                await_promise=False,
                recv_timeout=20.0,
            )
            ui = raw if isinstance(raw, dict) else {"value": raw}
            if int(ui.get("failureCount") or 0) >= 1 and ui.get("isStreaming") is False:
                banner = await chat.evaluate(
                    _LIVE_MUTATION_BANNER_JS,
                    await_promise=False,
                    recv_timeout=20.0,
                )
                if isinstance(banner, dict) and banner.get("ready") is True:
                    return {"source": "ui", "banner": banner, "ui": ui}
            await asyncio.sleep(1.5)
        raise AssertionError(
            f"Live empty write did not produce mutation failure banner; "
            f"api_invoked={last_api[0]} api_failure={last_api[1]}"
        )

    async def _run_flow(chat: McpChatSession) -> tuple[str, dict[str, object]]:
        await chat.dismiss_modals()
        await _wait_agent_applied(chat)
        pinned_model = await _pin_lite_model(chat)
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL)

        ensured = await chat.evaluate(
            _ENSURE_CHAT_SESSION_JS, await_promise=True, recv_timeout=30.0
        )
        assert isinstance(ensured, dict) and ensured.get("ok") is True, ensured

        chat_id = str((await chat.bridge_chat_id()) or "").strip()
        assert chat_id, "Expected client chat id after new chat before sandbox seed"
        _seed_live_workspace(api_base, chat_id)

        send_result = await chat.send_message(_LIVE_USER_PROMPT, _LIVE_USER_PROMPT)
        chat_id_hint = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or chat_id
        ).strip()

        heartbeat_e2e_lease()
        started = await chat.wait_stream_started(
            _LIVE_USER_PROMPT, timeout_sec=120.0, chat_id_hint=chat_id_hint or None
        )
        resolved_chat_id = (
            chat_id_hint or str(started.get("chatId") or "").strip() or None
        )
        assert resolved_chat_id, (
            f"Expected chat id after stream start: started={started}; send={send_result}; "
            f"model={pinned_model.get('providerId')}/{pinned_model.get('model')}"
        )

        await chat.navigate_to_chat(resolved_chat_id, BASE_URL, timeout_sec=90.0)
        result = await _wait_turn_done(chat, resolved_chat_id, timeout_sec=480.0)
        invoked, has_failure = _empty_write_failure_in_messages(
            resolved_chat_id, api_url=api_base
        )
        assert invoked, f"{_FILE_WRITE_TOOL} not found in persisted messages; result={result}"
        assert has_failure, f"fileMutationFailures missing; result={result}"
        e2e_resource_ledger.register("chat", resolved_chat_id)
        return resolved_chat_id, result

    last_error = ""
    client = ChromeMcpClient(request_timeout_sec=300.0)
    await asyncio.to_thread(client.start)
    try:
        agent_url = f"{ui_base}/?agentId={agent_id}"
        for attempt in range(_MAX_CHAT_ATTEMPTS):
            heartbeat_e2e_lease()
            try:
                page: McpPage | None = None
                for page_attempt in range(3):
                    try:
                        page = await asyncio.to_thread(
                            client.new_page, agent_url, timeout_ms=120_000
                        )
                        break
                    except (TimeoutError, RuntimeError) as exc:
                        if page_attempt >= 2 or "new_page" not in str(exc):
                            raise
                        await asyncio.sleep(2.0 * (page_attempt + 1))
                if page is None:
                    raise RuntimeError("new_page returned no page")
                chat = McpChatSession(client, page)
                await chat.bootstrap(agent_url, timeout_sec=120.0)
                chat_id, result = await _run_flow(chat)
                assert chat_id
                assert result.get("invoked") is True or "banner" in result
                break
            except (AssertionError, RuntimeError, TimeoutError) as exc:
                last_error = str(exc)
                if attempt >= _MAX_CHAT_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(2.0)
        else:
            pytest.fail(last_error or "live empty write WebUI flow failed")
    finally:
        await asyncio.to_thread(client.close)
