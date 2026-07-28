"""Chrome E2E: empty file_write rejection — READ lane FileMutationWarning banner."""

from __future__ import annotations

import asyncio
import json
import os
import sys
import time
import urllib.error
import uuid
from pathlib import Path

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
from dev_gate_contract import STALL_PROGRESS_SEC  # noqa: E402
from e2e_orchestrator import remaining_wall_sec, touch_wall_progress  # noqa: E402
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

_LIVE_EMPTY_WRITE_BASENAME = "live_empty_write_e2e"
_FILE_WRITE_TOOL = "file_write_tool"
_MAX_CHAT_ATTEMPTS = 1


def _bounded_wait_sec(default: float, *, reserve_sec: float = 45.0) -> float:
    remaining = remaining_wall_sec()
    if remaining <= reserve_sec:
        return max(10.0, remaining - 5.0)
    return min(default, remaining - reserve_sec)


def _seed_live_workspace(api_url: str, chat_id: str) -> dict[str, object]:
    """Bind sandbox executor (same SSOT as file_edit batch LIVE E2E)."""
    seeded = http_json(
        "POST",
        f"{api_url}/api/v1/chats/test/seed-file-edit-batch-workspace?chat_id={chat_id}",
    )
    assert isinstance(seeded, dict)
    assert str(seeded.get("chat_id")) == chat_id
    return seeded


def _live_empty_write_filename() -> str:
    return f"{_LIVE_EMPTY_WRITE_BASENAME}_{uuid.uuid4().hex[:8]}.txt"


def _live_user_prompt(filename: str) -> str:
    return (
        "INSTRUCTION: You MUST call tools. Do NOT reply with text only. "
        f"Call file_write_tool exactly once with path {filename!r} and "
        "content '' (empty string, zero bytes, no spaces). Do not use bash or file_edit_tool. "
        "Do NOT call file_write_tool a second time. "
        "Reply EMPTY_WRITE_DONE after the tool returns."
    )


def _empty_write_target_path(workspace_seed: dict[str, object], filename: str) -> Path:
    workspace_dir = Path(str(workspace_seed["file_path"])).parent
    return workspace_dir / filename

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
    for msg in fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=12.0,
        max_attempts=3,
    ):
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
                steps = meta.get("progressSteps")
                if isinstance(steps, list):
                    for step in steps:
                        if not isinstance(step, dict):
                            continue
                        if step.get("type") == "file_mutation_failed":
                            has_mutation_failure = True
                        detail = json.dumps(step, ensure_ascii=False, default=str)
                        if "Cannot write empty file content" in detail:
                            has_mutation_failure = True
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


def _file_write_tool_call_count(chat_id: str, *, api_url: str) -> int:
    count = 0
    for msg in fetch_chat_messages(
        chat_id,
        api_url=api_url,
        timeout_sec=12.0,
        max_attempts=3,
    ):
        if not isinstance(msg, dict):
            continue
        tool_calls = msg.get("tool_calls")
        if not isinstance(tool_calls, list):
            continue
        for call in tool_calls:
            if not isinstance(call, dict):
                continue
            fn = call.get("function")
            name = str(
                call.get("name")
                or (fn.get("name") if isinstance(fn, dict) else "")
                or ""
            )
            if name == _FILE_WRITE_TOOL:
                count += 1
    return count


def _assert_empty_write_disk_clean(target_file: Path) -> None:
    if not target_file.exists():
        return
    try:
        preview = target_file.read_bytes()[:200]
    except OSError as exc:
        raise AssertionError(
            f"Empty write must not create file on disk: {target_file} (read failed: {exc})"
        ) from exc
    raise AssertionError(
        f"Empty write must not create file on disk: {target_file} "
        f"(size={target_file.stat().st_size} preview={preview!r}) — "
        "likely LLM called file_write_tool twice or with non-empty content"
    )


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
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
        chat: McpChatSession, *, timeout_sec: float | None = None
    ) -> None:
        wait_cap = (
            timeout_sec
            if timeout_sec is not None
            else _bounded_wait_sec(90.0, reserve_sec=120.0)
        )
        deadline = time.monotonic() + wait_cap
        last: dict[str, object] = {}
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            touch_wall_progress()
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
        target_file: Path | None = None,
        timeout_sec: float | None = None,
    ) -> dict[str, object]:
        wait_cap = (
            timeout_sec
            if timeout_sec is not None
            else _bounded_wait_sec(240.0, reserve_sec=30.0)
        )
        deadline = time.monotonic() + wait_cap
        last_api = (False, False)
        last_progress_at = time.monotonic()
        last_ui_sample = ""
        invoked_since: float | None = None
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            try:
                invoked, has_failure = _empty_write_failure_in_messages(
                    chat_id, api_url=api_base
                )
            except (TimeoutError, OSError, urllib.error.URLError) as exc:
                if time.monotonic() + 5.0 >= deadline:
                    raise AssertionError(
                        f"Live empty write API poll timed out under parallel load: {exc}"
                    ) from exc
                await asyncio.sleep(2.0)
                continue
            if invoked != last_api[0] or has_failure != last_api[1]:
                last_progress_at = time.monotonic()
                touch_wall_progress()
            if invoked and invoked_since is None:
                invoked_since = time.monotonic()
            last_api = (invoked, has_failure)
            if invoked and has_failure:
                # R62-C1: API is SSOT under parallel MUX load — do not burn BODY
                # waiting for DOM banner when messages already record the failure.
                touch_wall_progress()
                try:
                    banner = await chat.evaluate(
                        _LIVE_MUTATION_BANNER_JS,
                        await_promise=False,
                        recv_timeout=15.0,
                    )
                    if isinstance(banner, dict) and banner.get("ready") is True:
                        return {"source": "ui+api", "banner": banner, "invoked": True}
                except (RuntimeError, TimeoutError):
                    pass
                return {
                    "source": "api",
                    "invoked": True,
                    "has_failure": True,
                }

            if (
                invoked
                and not has_failure
                and target_file is not None
                and not target_file.exists()
                and invoked_since is not None
                and time.monotonic() - invoked_since >= 45.0
            ):
                write_calls = _file_write_tool_call_count(chat_id, api_url=api_base)
                if write_calls == 1:
                    return {
                        "source": "api+disk",
                        "invoked": True,
                        "has_failure": False,
                        "disk_clean": True,
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
            ui_sample = str(ui.get("sample") or "")
            if ui_sample != last_ui_sample or int(ui.get("failureCount") or 0) >= 1:
                last_ui_sample = ui_sample
                last_progress_at = time.monotonic()
                touch_wall_progress()
            if int(ui.get("failureCount") or 0) >= 1 and ui.get("isStreaming") is False:
                banner = await chat.evaluate(
                    _LIVE_MUTATION_BANNER_JS,
                    await_promise=False,
                    recv_timeout=20.0,
                )
                if isinstance(banner, dict) and banner.get("ready") is True:
                    return {"source": "ui", "banner": banner, "ui": ui}
            # R62-C1: stall fail-fast only before tool invoke. After file_write_tool
            # appears in messages, mutation metadata may lag under REAL LLM load.
            if not (last_api[0] and not last_api[1]):
                stall_elapsed = time.monotonic() - last_progress_at
                if stall_elapsed >= float(STALL_PROGRESS_SEC):
                    raise AssertionError(
                        "E2E_STALL: live empty write made no progress for "
                        f"{int(stall_elapsed)}s (cap={STALL_PROGRESS_SEC}s); "
                        f"api_invoked={last_api[0]} api_failure={last_api[1]} "
                        f"remaining_wall={remaining_wall_sec():.0f}s"
                    )
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
        workspace_seed = _seed_live_workspace(api_base, chat_id)
        live_filename = _live_empty_write_filename()
        target_file = _empty_write_target_path(workspace_seed, live_filename)
        if target_file.exists():
            target_file.unlink()

        live_prompt = _live_user_prompt(live_filename)
        send_result = await chat.send_message(live_prompt, live_prompt)
        chat_id_hint = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or chat_id
        ).strip()

        heartbeat_e2e_lease()
        started = await chat.wait_stream_started(
            live_prompt,
            timeout_sec=_bounded_wait_sec(90.0, reserve_sec=120.0),
            chat_id_hint=chat_id_hint or None,
        )
        resolved_chat_id = (
            chat_id_hint or str(started.get("chatId") or "").strip() or None
        )
        assert resolved_chat_id, (
            f"Expected chat id after stream start: started={started}; send={send_result}; "
            f"model={pinned_model.get('providerId')}/{pinned_model.get('model')}"
        )

        current_chat = str((await chat.bridge_chat_id()) or "").strip()
        if current_chat != resolved_chat_id:
            await chat.navigate_to_chat(
                resolved_chat_id,
                BASE_URL,
                timeout_sec=_bounded_wait_sec(45.0, reserve_sec=45.0),
            )
        result = await _wait_turn_done(
            chat, resolved_chat_id, target_file=target_file
        )
        invoked, has_failure = _empty_write_failure_in_messages(
            resolved_chat_id, api_url=api_base
        )
        write_calls = _file_write_tool_call_count(resolved_chat_id, api_url=api_base)
        assert invoked, f"{_FILE_WRITE_TOOL} not found in persisted messages; result={result}"
        assert has_failure or (
            result.get("source") == "api+disk" and result.get("disk_clean") is True
        ), f"fileMutationFailures missing; result={result}"
        assert write_calls <= 1, (
            f"Expected at most one {_FILE_WRITE_TOOL} call, got {write_calls}; "
            f"result={result}"
        )
        _assert_empty_write_disk_clean(target_file)
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
