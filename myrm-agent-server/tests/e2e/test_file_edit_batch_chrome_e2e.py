"""Chrome E2E: file_edit_tool batch edits — READ UI seed + LIVE_AGENT real WebUI flow."""

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

from cdp_chat_support import (  # noqa: E402
    ensure_e2e_yolo_mode,
    fetch_chat_messages,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)
from cdp_chat_ui import chat_id_from_path  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.api.agent.utils import (  # noqa: E402
    _strip_provider_prefix,
    get_lite_model_selection,
)
from tests.support.chrome_mcp_e2e import (
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    prepare_e2e_ui_session,
    wait_for_state,
    warm_ui_route,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

_FIXTURE_ANSWER = "Batch file edit E2E fixture answer."
_FILE_EDIT_TOOL = "file_edit_tool"
_BATCH_FIXTURE_FILE = "batch_edit_e2e.txt"
_MAX_CHAT_ATTEMPTS = 3
_LIVE_USER_PROMPT = (
    f"The workspace file {_BATCH_FIXTURE_FILE} contains three lines: line_a, line_b, line_c. "
    "Read it with file_read_tool, then call file_edit_tool exactly once with an edits array "
    "that replaces line_a with LINE_A and line_c with LINE_C. Reply BATCH_OK when finished."
)

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

_FILE_EDIT_STEP_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = store?.messages || [];
  for (const msg of msgs) {
    const metaSteps = Array.isArray(msg.metadata?.progressSteps) ? msg.metadata.progressSteps : [];
    const steps = (msg.progressSteps?.length ? msg.progressSteps : metaSteps) || [];
    for (const step of steps) {
      const key = String(step.step_key || step.tool_name || '');
      if (!key.includes('file_edit')) continue;
      for (const item of step.items || []) {
        const diff = String(item.diff || '');
        if (diff.includes('LINE_A') || diff.includes('-line_a') || diff.includes('line_a')) {
          return { ready: true, step_key: key, diff_head: diff.slice(0, 400) };
        }
      }
    }
  }
  return { ready: false, msg_count: msgs.length };
})()"""


def _seed_fixture(api_url: str, *, variant: str, agent_id: str | None = None) -> dict[str, object]:
    query = f"variant={variant}"
    if agent_id:
        query += f"&agent_id={agent_id}"
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-file-edit-batch-fixture?{query}",
    )
    assert isinstance(seeded, dict)
    chat_id = str(seeded.get("chat_id") or "")
    assert chat_id.startswith("e2efedit")
    return seeded


def _seed_workspace_file(api_url: str, chat_id: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-file-edit-batch-workspace?chat_id={chat_id}",
    )
    assert isinstance(seeded, dict)
    assert str(seeded.get("chat_id")) == chat_id
    return seeded


def _create_file_edit_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Batch File Edit LIVE {suffix}",
        "description": "Chrome LIVE E2E for batch file_edit_tool",
        "system_prompt": (
            "You edit workspace files with file_read_tool and file_edit_tool. "
            "When the user asks for batch edits, call file_edit_tool once with an edits array. "
            "Always read before edit. Reply BATCH_OK when the edits succeed."
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


def _file_edit_invoked_in_messages(chat_id: str, *, api_url: str) -> tuple[bool, str]:
    last_assistant = ""
    invoked = False
    for msg in fetch_chat_messages(chat_id, api_url=api_url):
        if not isinstance(msg, dict):
            continue
        blob = json.dumps(msg, ensure_ascii=False, default=str)
        if _FILE_EDIT_TOOL in blob:
            invoked = True
        if msg.get("role") == "assistant":
            last_assistant = str(msg.get("content") or "")
    return invoked, last_assistant


def _assert_batch_file_content(file_path: Path) -> None:
    content = file_path.read_text(encoding="utf-8")
    assert "LINE_A" in content and "LINE_C" in content, content
    assert "line_a" not in content.splitlines()
    assert "line_c" not in content.splitlines()
    assert "line_b" in content


@pytest.mark.chrome_e2e(lane="READ", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(240)
def test_file_edit_batch_read_ui_diff_card() -> None:
    api_url = get_e2e_api_url()
    ui_url = get_e2e_ui_url()
    seeded = _seed_fixture(api_url, variant="read_ui")
    chat_id = str(seeded["chat_id"])

    prepare_e2e_ui_session(api_url)
    warm_ui_route(f"/{chat_id}")
    with open_mcp_page(f"{ui_url}/{chat_id}", timeout_ms=120_000) as (client, page):
        probe = wait_for_state(
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
        assert probe.get("ready") is True, json.dumps(probe, ensure_ascii=False)

        step = wait_for_state(client, page, _FILE_EDIT_STEP_JS, timeout_sec=30.0)
        assert step.get("ready") is True, json.dumps(step, ensure_ascii=False)
        diff_head = str(step.get("diff_head") or "")
        assert "--- edit 1 ---" in diff_head or "-line_a" in diff_head


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.integration
@pytest.mark.timeout(900)
@pytest.mark.asyncio
async def test_file_edit_batch_live_agent_webui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live file-edit E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome"
        )

    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url()
    ensure_e2e_yolo_mode(api_url=api_base)
    agent_id = _create_file_edit_agent(api_base)
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
        file_path: Path,
        timeout_sec: float = 480.0,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last_api = ("", False)
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            invoked, assistant = _file_edit_invoked_in_messages(chat_id, api_url=api_base)
            last_api = (assistant, invoked)
            if invoked and "BATCH_OK" in assistant.upper():
                try:
                    _assert_batch_file_content(file_path)
                except AssertionError:
                    if time.monotonic() + 15.0 < deadline:
                        await asyncio.sleep(1.5)
                        continue
                    raise
                return {
                    "source": "api",
                    "assistant": assistant[:800],
                    "invoked": True,
                    "model_done": True,
                }

            raw = await chat.evaluate(
                """(() => {
                  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
                  const text = String(snap.lastAssistantSample || '');
                  return {
                    chatId: snap.chatId,
                    isStreaming: Boolean(snap.isStreaming),
                    userCount: snap.userCount ?? 0,
                    hasBatchOk: /BATCH_OK/i.test(text),
                    sample: text.slice(0, 600),
                  };
                })()""",
                await_promise=False,
                recv_timeout=20.0,
            )
            ui = raw if isinstance(raw, dict) else {"value": raw}
            if (
                ui.get("hasBatchOk") is True
                and ui.get("isStreaming") is False
                and int(ui.get("userCount") or 0) >= 1
            ):
                try:
                    _assert_batch_file_content(file_path)
                except AssertionError:
                    await asyncio.sleep(1.5)
                    continue
                return {
                    "source": "ui",
                    "assistant": str(ui.get("sample") or ""),
                    "invoked": last_api[1],
                    "model_done": True,
                    "ui": ui,
                }
            await asyncio.sleep(1.5)
        raise AssertionError(
            f"Batch file edit did not complete; api_assistant={last_api[0][:400]!r}; "
            f"file_edit_invoked={last_api[1]!r}; file={file_path}"
        )

    async def _run_flow(chat: McpChatSession) -> tuple[str, Path, dict[str, object]]:
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
        assert chat_id, "Expected client chat id after new chat before seeding workspace file"

        workspace_seed = _seed_workspace_file(api_base, chat_id)
        file_path = Path(str(workspace_seed["file_path"]))
        assert file_path.is_file(), workspace_seed

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
        resolved_chat_id = chat_id_hint or str(started.get("chatId") or "").strip() or None
        if not resolved_chat_id:
            after_start = await chat.main_state(_LIVE_USER_PROMPT, recv_timeout=30.0)
            resolved_chat_id = (
                chat_id_from_path(str(after_start.get("path") or ""))
                or str(after_start.get("bridgeChatId") or "").strip()
                or None
            )
        assert resolved_chat_id, (
            f"Expected chat id after stream start: started={started}; send={send_result}; "
            f"model={pinned_model.get('providerId')}/{pinned_model.get('model')}"
        )

        await chat.navigate_to_chat(resolved_chat_id, BASE_URL, timeout_sec=90.0)
        result = await _wait_turn_done(
            chat, resolved_chat_id, file_path=file_path, timeout_sec=480.0
        )
        assert result.get("model_done") is True, result
        invoked, _assistant = _file_edit_invoked_in_messages(
            resolved_chat_id, api_url=api_base
        )
        assert invoked, f"{_FILE_EDIT_TOOL} not found in persisted messages; result={result}"

        step = await chat.evaluate(
            _FILE_EDIT_STEP_JS, await_promise=False, recv_timeout=20.0
        )
        assert isinstance(step, dict) and step.get("ready") is True, step

        e2e_resource_ledger.register("chat", resolved_chat_id)
        return resolved_chat_id, file_path, pinned_model

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
                _chat_id, file_path, _pinned_model = await _run_flow(chat)
                _assert_batch_file_content(file_path)
                break
            except (AssertionError, RuntimeError, TimeoutError) as exc:
                last_error = str(exc)
                if attempt >= _MAX_CHAT_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(2.0)
        else:
            pytest.fail(last_error or "file_edit batch live WebUI flow failed")
    finally:
        await asyncio.to_thread(client.close)
