"""Chrome LIVE_AGENT E2E: real LLM turn edits a workspace file, then page reload →
RevertFiles restores it via requestMessageId.

Covers the real end-to-end path of the request_message_id fix:
1. A real LLM turn calls file_edit_tool (SnapshotObserver records the snapshot keyed by
   the r- prefixed request.message_id).
2. Page reload → hydrate: the assistant message gets messageId=DB UUID while
   requestMessageId is restored from extra_data.request_message_id.
3. RevertFiles (same `requestMessageId || messageId` resolution as the component)
   restores the file to its pre-edit content.

The fixture only needs the model to make one deterministic file_edit_tool call.
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
    fetch_chat_messages,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)
from cdp_chat.ui import chat_id_from_path  # noqa: E402
from dev_gate.contract import EvaluateIntent  # noqa: E402

from tests.api.agent.utils import (  # noqa: E402
    _strip_provider_prefix,
    get_lite_model_selection,
)
from tests.support.chrome_mcp_e2e import (  # noqa: E402
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
)
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once  # noqa: E402

try:
    from e2e_session_runtime.lifecycle import touch_wall_progress
except ImportError:  # pragma: no cover - lib on PYTHONPATH in e2e only

    def touch_wall_progress(*, current_node: str | None = None) -> None:
        del current_node


def _touch_progress(node: str) -> None:
    try:
        touch_wall_progress(current_node=node)
        heartbeat_once()
    except Exception:  # pragma: no cover - infra jitter resilience
        pass


BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

_FILE_EDIT_TOOL = "file_edit_tool"
_WORKSPACE_FILENAME = "batch_edit_e2e.txt"
_MAX_CHAT_ATTEMPTS = 2

_LIVE_USER_PROMPT = (
    f"The workspace file {_WORKSPACE_FILENAME} contains exactly three lines: line_a, line_b, line_c. "
    "Use file_edit_tool once with an edits array that replaces the line containing line_a "
    "with the line LINE_A. Do not change line_b or line_c. Reply REVERT_LIVE_OK when done."
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


def _create_revert_live_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"RevertFiles LIVE {suffix}",
        "description": "Chrome LIVE E2E for revert-files after page reload",
        "system_prompt": (
            "You edit workspace files with file_read_tool and file_edit_tool. "
            "When the user asks to replace a line, call file_edit_tool once with an "
            "edits array using old_str/new_str pairs. Reply REVERT_LIVE_OK when done."
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


def _seed_workspace_file(api_url: str, chat_id: str) -> dict[str, object]:
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-file-edit-batch-workspace?chat_id={chat_id}",
    )
    assert isinstance(seeded, dict)
    assert str(seeded.get("chat_id")) == chat_id
    return seeded


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


_SEED_CONTENT = "line_a\nline_b\nline_c\n"


def _assert_edited(file_path: Path) -> None:
    content = file_path.read_text(encoding="utf-8")
    assert content != _SEED_CONTENT, f"file unchanged by agent turn: {content!r}"


def _assert_restored(file_path: Path) -> None:
    content = file_path.read_text(encoding="utf-8")
    lines = content.splitlines()
    assert "line_a" in lines and "line_b" in lines and "line_c" in lines, (
        f"seed lines missing after restore: {content!r}"
    )
    assert "LINE_A" not in content, f"agent edit not reverted: {content!r}"


_HYDRATE_WITH_REQUEST_ID_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = (store?.messages || []).filter((m) => m.role === 'assistant');
  const msg = msgs[msgs.length - 1] || null;
  return {
    ready: !!msg,
    messageId: msg?.messageId ?? null,
    requestMessageId: msg?.requestMessageId ?? null,
    isRPrefix: typeof msg?.requestMessageId === 'string'
      && msg.requestMessageId.startsWith('r-'),
    count: (store?.messages || []).length,
  };
})()"""

_PROBE_REVERT_CHANGES_JS = """(() => {
  return (async () => {
    const chatId = location.pathname.replace(/^\\//, '');
    const store = window.__myrmChatStore?.getState?.();
    const msgs = (store?.messages || []).filter((m) => m.role === 'assistant');
    const msg = msgs[msgs.length - 1] || null;
    if (!msg) {
      return { ok: false, err: 'fixture-message-missing', chatId };
    }
    const mid = msg.requestMessageId || msg.messageId;
    let last = { ok: false, status: 0, chatId, messageId: msg.messageId, mid, body: '' };
    for (let attempt = 0; attempt < 12; attempt += 1) {
      const res = await fetch(`/api/v1/files/revert/changes/${chatId}/${mid}`);
      const body = await res.text();
      last = {
        ok: res.ok && body.startsWith('[') && body.includes('batch_edit_e2e.txt'),
        status: res.status,
        chatId,
        messageId: msg.messageId,
        requestMessageId: msg.requestMessageId ?? null,
        mid,
        body: body.slice(0, 300),
      };
      if (last.ok) return last;
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    return last;
  })();
})()"""

_REVERT_BUTTON_READY_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = (store?.messages || []).filter((m) => m.role === 'assistant');
  const msg = msgs[msgs.length - 1] || null;
  if (!msg) return { ready: false, err: 'no-assistant-msg' };
  const markdown = document.querySelector(`[data-message-id="${msg.messageId}"]`);
  const scope = markdown?.closest('.flex.flex-col.space-y-2') ?? markdown?.parentElement;
  const btn = scope
    ? Array.from(scope.querySelectorAll('button[title]')).find((candidate) => {
        const title = candidate.getAttribute('title') || '';
        return /Undo file changes|Undo \\d+ file change|撤销文件变更|撤销 \\d+ 个文件变更/i.test(title);
      })
    : null;
  return { ready: !!btn, err: btn ? null : 'revert-button-missing', messageId: msg.messageId };
})()"""

_CLICK_REVERT_AND_WAIT_POPOVER_JS = """(() => {
  const store = window.__myrmChatStore?.getState?.();
  const msgs = (store?.messages || []).filter((m) => m.role === 'assistant');
  const msg = msgs[msgs.length - 1] || null;
  const findBtn = () => {
    if (!msg) return null;
    const markdown = document.querySelector(`[data-message-id="${msg.messageId}"]`);
    const scope = markdown?.closest('.flex.flex-col.space-y-2') ?? markdown?.parentElement;
    if (!scope) return null;
    return Array.from(scope.querySelectorAll('button[title]')).find((candidate) => {
      const title = candidate.getAttribute('title') || '';
      return /Undo file changes|Undo \\d+ file change|撤销文件变更|撤销 \\d+ 个文件变更/i.test(title);
    }) || null;
  };
  return (async () => {
    const btn = findBtn();
    if (!btn) return { ready: false, err: 'revert-button-missing' };
    btn.click();
    const deadline = Date.now() + 45000;
    while (Date.now() < deadline) {
      const popover = document.querySelector('[data-radix-popper-content-wrapper]');
      const text = popover?.textContent || '';
      const hasConfirm = /Undo these changes\\?|撤销这些变更？/i.test(text);
      const hasFile = /batch_edit_e2e\\.txt/i.test(text);
      const hasAction = /Confirm revert|确认撤销/i.test(text);
      if (popover && hasConfirm && hasFile && hasAction) {
        return { ready: true, sample: text.slice(0, 400) };
      }
      await new Promise((resolve) => setTimeout(resolve, 300));
    }
    const fallback = document.querySelector('[data-radix-popper-content-wrapper]')?.textContent
      || document.body?.innerText
      || '';
    return { ready: false, sample: fallback.slice(0, 400) };
  })();
})()"""

_CLICK_CONFIRM_JS = """(() => {
  const popover = document.querySelector('[data-radix-popper-content-wrapper]');
  const scope = popover || document;
  const btn = Array.from(scope.querySelectorAll('button')).find((el) => {
    const label = (el.textContent || '').trim();
    return /Confirm revert|确认撤销/i.test(label);
  });
  if (!btn) return { clicked: false };
  btn.click();
  return { clicked: true };
})()"""

_HOOK_RESYNC_JS = """(() => {
  window.__MYRM_REVERT_RESYNC__ = false;
  window.addEventListener('app_resync_required', () => {
    window.__MYRM_REVERT_RESYNC__ = true;
  }, { once: true });
  return { hooked: true };
})()"""

_SUCCESS_STATE_JS = """(() => {
  return {
    ready: window.__MYRM_REVERT_RESYNC__ === true,
    resyncSeen: window.__MYRM_REVERT_RESYNC__ === true,
  };
})()"""


@pytest.mark.chrome_e2e(execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE", private_reason="live_shpoib")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_revert_files_live_agent_after_reload_restores_file(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live revert E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome"
        )

    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url()
    ensure_e2e_yolo_mode(api_url=api_base)
    agent_id = _create_revert_live_agent(api_base)
    e2e_resource_ledger.register("agent", agent_id)

    async def _wait_agent_applied(chat: McpChatSession, *, timeout_sec: float = 90.0) -> None:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            raw = await chat.evaluate(
                _AGENT_READY_JS, intent=EvaluateIntent.BRIDGE_POLL
            )
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return
            await asyncio.sleep(1.0)
        raise AssertionError(f"E2E chat bridge not ready after loading agent: {last}")

    async def _pin_lite_model(chat: McpChatSession) -> dict[str, object]:
        await chat.ensure_react_e2e_bridge(timeout_sec=60.0)
        pinned = await chat.evaluate(
            _PIN_LITE_MODEL_JS, intent=EvaluateIntent.AGENT_SUBMIT
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

    async def _wait_live_turn_done(
        chat: McpChatSession,
        chat_id: str,
        *,
        file_path: Path,
        timeout_sec: float = 180.0,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last_api = ("", False)
        claim_seen_at: float | None = None

        def _finalize(source: str, assistant_text: str) -> dict[str, object]:
            """Agent claims REVERT_LIVE_OK: give the file write a short settle
            window, then fail fast with full diagnostics instead of waiting."""
            try:
                _assert_edited(file_path)
            except AssertionError:
                raise AssertionError(
                    f"agent claimed REVERT_LIVE_OK but file unchanged: {file_path} "
                    f"content={file_path.read_text(encoding='utf-8')!r} "
                    f"assistant={assistant_text[:400]!r}"
                ) from None
            return {"source": source, "assistant": assistant_text[:800], "invoked": True}

        while time.monotonic() < deadline:
            heartbeat_once()
            invoked, assistant = _file_edit_invoked_in_messages(
                chat_id, api_url=api_base
            )
            last_api = (assistant, invoked)
            if invoked and "REVERT_LIVE_OK" in assistant.upper():
                if claim_seen_at is None:
                    claim_seen_at = time.monotonic()
                if time.monotonic() - claim_seen_at >= 20.0:
                    return _finalize("api", assistant)
            else:
                claim_seen_at = None

            raw = await chat.evaluate(
                """(() => {
                  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
                  const text = String(snap.lastAssistantSample || '');
                  return {
                    chatId: snap.chatId,
                    isStreaming: Boolean(snap.isStreaming),
                    userCount: snap.userCount ?? 0,
                    hasDone: /REVERT_LIVE_OK/i.test(text),
                    sample: text.slice(0, 600),
                  };
                })()""",
                intent=EvaluateIntent.BRIDGE_POLL,
            )
            ui = raw if isinstance(raw, dict) else {"value": raw}
            if (
                ui.get("hasDone") is True
                and ui.get("isStreaming") is False
                and int(ui.get("userCount") or 0) >= 1
            ):
                if claim_seen_at is None:
                    claim_seen_at = time.monotonic()
                if time.monotonic() - claim_seen_at >= 20.0:
                    return _finalize("ui", str(ui.get("sample") or ""))
            else:
                claim_seen_at = None
            await asyncio.sleep(1.5)
        raise AssertionError(
            f"Live revert turn did not complete; api_assistant={last_api[0][:400]!r}; "
            f"file_edit_invoked={last_api[1]!r}; file={file_path}; "
            f"last_ui={ui.get('sample', '')!r}"
        )

    async def _wait_hydrate_request_id(chat: McpChatSession, *, timeout_sec: float = 90.0) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_once()
            raw = await chat.evaluate(
                _HYDRATE_WITH_REQUEST_ID_JS, intent=EvaluateIntent.BRIDGE_POLL
            )
            last = raw if isinstance(raw, dict) else {"value": raw}
            if last.get("ready") is True:
                return last
            await asyncio.sleep(1.0)
        raise AssertionError(f"Hydrate with requestMessageId not reached: {last}")

    async def _run_flow(chat: McpChatSession) -> tuple[str, Path]:
        await chat.dismiss_modals()
        await _wait_agent_applied(chat)
        await _pin_lite_model(chat)
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL)

        ensured = await chat.evaluate(
            _ENSURE_CHAT_SESSION_JS, intent=EvaluateIntent.ROUTE_ATTACH
        )
        assert isinstance(ensured, dict) and ensured.get("ok") is True, ensured

        chat_id = str((await chat.bridge_chat_id()) or "").strip()
        assert chat_id, "Expected client chat id after new chat before seeding workspace"

        workspace_seed = _seed_workspace_file(api_base, chat_id)
        file_path = Path(str(workspace_seed["file_path"]))
        assert file_path.is_file(), workspace_seed

        send_result = await chat.send_message(_LIVE_USER_PROMPT, _LIVE_USER_PROMPT)
        chat_id_hint = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or chat_id
        ).strip()

        heartbeat_once()
        started = await chat.wait_stream_started(
            _LIVE_USER_PROMPT, timeout_sec=120.0, chat_id_hint=chat_id_hint or None
        )
        resolved_chat_id = (
            chat_id_hint or str(started.get("chatId") or "").strip() or None
        )
        if not resolved_chat_id:
            after_start = await chat.main_state(
                _LIVE_USER_PROMPT, intent=EvaluateIntent.BRIDGE_POLL
            )
            resolved_chat_id = (
                chat_id_from_path(str(after_start.get("path") or ""))
                or str(after_start.get("bridgeChatId") or "").strip()
                or None
            )
        assert resolved_chat_id, (
            f"Expected chat id after stream start: started={started}; send={send_result}"
        )

        await chat.navigate_to_chat(resolved_chat_id, BASE_URL, timeout_sec=90.0)
        result = await _wait_live_turn_done(
            chat, resolved_chat_id, file_path=file_path, timeout_sec=180.0
        )
        assert result.get("invoked") is True, result

        # --- 核心链路：刷新页面 → hydrate → requestMessageId 恢复 ---
        _touch_progress("revert_live_reload")
        await chat.navigate_to_chat(resolved_chat_id, BASE_URL, timeout_sec=120.0)
        await chat.evaluate(_HOOK_RESYNC_JS, intent=EvaluateIntent.BRIDGE_POLL, recv_timeout=10.0)

        hydrated = await _wait_hydrate_request_id(chat, timeout_sec=120.0)
        assert hydrated.get("ready") is True, hydrated
        assert hydrated.get("isRPrefix") is True, (
            f"requestMessageId must be an r- prefixed request id after reload: {hydrated}"
        )

        # probe 与 RevertFiles 组件同一解析逻辑（requestMessageId || messageId）
        probe = await chat.evaluate(
            _PROBE_REVERT_CHANGES_JS, intent=EvaluateIntent.AGENT_SUBMIT
        )
        assert isinstance(probe, dict) and probe.get("ok") is True, json.dumps(
            probe, ensure_ascii=False
        )

        # --- 真实 UI 回退操作 ---
        button = await chat.evaluate(
            _REVERT_BUTTON_READY_JS, intent=EvaluateIntent.BRIDGE_POLL
        )
        assert isinstance(button, dict) and button.get("ready") is True, button

        popover = await chat.evaluate(
            _CLICK_REVERT_AND_WAIT_POPOVER_JS, intent=EvaluateIntent.AGENT_SUBMIT
        )
        assert isinstance(popover, dict) and popover.get("ready") is True, json.dumps(
            popover, ensure_ascii=False
        )

        confirmed = await chat.evaluate(
            _CLICK_CONFIRM_JS, intent=EvaluateIntent.AGENT_SUBMIT
        )
        assert (
            isinstance(confirmed, dict) and confirmed.get("clicked") is True
        ), confirmed

        success = await chat.evaluate(
            _SUCCESS_STATE_JS, intent=EvaluateIntent.BRIDGE_POLL
        )
        # resync 事件可能已触发（hook 是 once）；轮询兜底
        deadline = time.monotonic() + 60.0
        while time.monotonic() < deadline and not (
            isinstance(success, dict) and success.get("ready") is True
        ):
            await asyncio.sleep(1.0)
            success = await chat.evaluate(
                _SUCCESS_STATE_JS, intent=EvaluateIntent.BRIDGE_POLL
            )
        assert isinstance(success, dict) and success.get("ready") is True, json.dumps(
            success, ensure_ascii=False
        )

        _assert_restored(file_path)

        e2e_resource_ledger.register("chat", resolved_chat_id)
        return resolved_chat_id, file_path

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
                chat_id, file_path = await _run_flow(chat)
            _assert_restored(file_path)
            assert chat_id
            break
        except (AssertionError, RuntimeError, TimeoutError) as exc:
            last_error = str(exc)
            if attempt >= _MAX_CHAT_ATTEMPTS - 1:
                raise
            await asyncio.sleep(2.0)
    else:
        pytest.fail(last_error or "live revert WebUI flow failed")
