"""Chrome LIVE_AGENT E2E: bash approval → allow-always pattern → Settings list.

Uses ``private_backend=True`` so chat/agent-stream hit an isolated ``:180xx`` API — never
contends with shared ``:8080`` agent-stream lock while parallel LIVE pytest runs.

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_allowlist_pattern_live_chrome_e2e.py
"""

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

from cdp_chat_support import fetch_chat_messages, get_e2e_api_url, wait_e2e_provider_ready  # noqa: E402
from cdp_chat_support import ensure_e2e_hitl_mode  # noqa: E402
from cdp_chat_ui import chat_id_from_path  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_allowlist_live_e2e import (
    SETTINGS_PATTERN_VISIBLE_JS,
    _AGENT_READY_JS,
    _APPROVAL_VISIBLE_JS,
    _CLICK_ALLOW_ALWAYS_JS,
    _CONFIRM_ALLOW_ALWAYS_DIALOG_JS,
    _RUNTIME_BINDING_JS,
    _SELECT_PATTERN_SCOPE_JS,
    _TURN_DONE_JS,
)
from tests.support.chrome_allowlist_settings_e2e import SETTINGS_SECURITY_SHELL_READY_JS
from tests.support.chrome_mcp_e2e import get_e2e_ui_url, http_json, wait_for_state, warm_ui_route
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
_BASH_TOOL = "bash_code_execute_tool"
# Must be UNKNOWN risk (not SAFE like echo) or engine auto-allows without HITL dialog.
_PATTERN_COMMAND = "curl ALLOWLIST_LIVE_PROBE"
# Natural-language user turn (no E2E_* / MUST injection — mimo rejects those in user text).
_USER_PROMPT = (
    "请用 bash_code_execute_tool 执行一条 shell 命令："
    f"`{_PATTERN_COMMAND}`，只执行这一条命令，不要调用其他工具。"
)
_APPROVAL_WAIT_SEC = 240.0
_STALL_AFTER_STREAM_SEC = 90.0
_MAX_CHAT_ATTEMPTS = 2


def _create_shell_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Allowlist Pattern LIVE {suffix}",
        "description": "Chrome LIVE E2E for shell allow-always pattern",
        "system_prompt": (
            "When the user asks to run a shell command, you MUST call bash_code_execute_tool "
            "with the exact command string provided. Do not reply with text only."
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "enabled_builtin_tools": ["code_execute"],
        "security_overrides": {"yoloModeEnabled": False, "autoModeEnabled": False},
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


def _message_blob(msg: dict[str, object]) -> str:
    parts: list[str] = [str(msg.get("content") or "")]
    metadata = msg.get("metadata")
    if metadata is not None:
        try:
            parts.append(json.dumps(metadata, ensure_ascii=False))
        except TypeError:
            parts.append(str(metadata))
    progress = msg.get("progressSteps")
    if progress is not None:
        try:
            parts.append(json.dumps(progress, ensure_ascii=False))
        except TypeError:
            parts.append(str(progress))
    return "\n".join(parts)


def _chat_bash_invocation(chat_id: str, *, api_url: str) -> tuple[bool, set[str]]:
    invoked: set[str] = set()
    for msg in fetch_chat_messages(chat_id, api_url=api_url):
        if not isinstance(msg, dict) or msg.get("role") != "assistant":
            continue
        blob = _message_blob(msg)
        if _BASH_TOOL in blob or "bash_code_execute" in blob:
            invoked.add(_BASH_TOOL)
        for step in msg.get("progressSteps") or []:
            if not isinstance(step, dict):
                continue
            tool_name = str(step.get("tool_name") or step.get("toolName") or "")
            if "bash" in tool_name.lower():
                invoked.add(tool_name)
    return bool(invoked), invoked


def _api_origin(url: str) -> str:
    parsed = urlparse(url.rstrip("/"))
    if not parsed.scheme or not parsed.netloc:
        raise ValueError(f"Invalid API base: {url!r}")
    return f"{parsed.scheme}://{parsed.netloc}"


async def _wait_for_eval(chat: McpChatSession, expression: str, *, timeout_sec: float) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        raw = await chat.evaluate(expression, await_promise=False, recv_timeout=30.0)
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ready") is True or last.get("ok") is True:
            return last
        await asyncio.sleep(0.5)
    raise AssertionError(f"Timed out waiting for browser state: {last}")


async def _wait_agent_applied(chat: McpChatSession, *, timeout_sec: float = 90.0) -> None:
    deadline = time.monotonic() + timeout_sec
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        raw = await chat.evaluate(_AGENT_READY_JS, await_promise=False, recv_timeout=20.0)
        last = raw if isinstance(raw, dict) else {"value": raw}
        if last.get("ready") is True:
            return
        await asyncio.sleep(1.0)
    raise AssertionError(f"E2E chat bridge not ready for shell agent: {last}")


async def _assert_runtime_binding(chat: McpChatSession, *, expected_api: str) -> None:
    expected_origin = _api_origin(expected_api)
    raw = await chat.evaluate(_RUNTIME_BINDING_JS, await_promise=False, recv_timeout=15.0)
    binding = raw if isinstance(raw, dict) else {}
    bound = str(binding.get("apiBase") or binding.get("runtimeApi") or "").strip()
    if _api_origin(bound) != expected_origin:
        raise AssertionError(
            f"SHPOIB runtime binding mismatch: expected={expected_origin!r} got={binding!r}"
        )


async def _wait_for_shell_approval_ui(
    chat: McpChatSession,
    chat_id: str,
    *,
    api_url: str,
    timeout_sec: float = _APPROVAL_WAIT_SEC,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last_ui: dict[str, object] = {}
    last_invoked: set[str] = set()
    stream_idle_since: float | None = None
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        raw = await chat.evaluate(_APPROVAL_VISIBLE_JS, await_promise=False, recv_timeout=20.0)
        last_ui = raw if isinstance(raw, dict) else {"value": raw}
        if last_ui.get("ready") is True:
            return last_ui

        has_bash, invoked = _chat_bash_invocation(chat_id, api_url=api_url)
        last_invoked = invoked
        if has_bash and not last_ui.get("hasDialog"):
            sample_text = str(last_ui.get("sample") or "")
            if "命令执行完成" in sample_text or "命令已执行完毕" in sample_text or "Command execution complete" in sample_text.lower():
                raise AssertionError(
                    "bash auto-executed without approval (SAFE-command bypass or yolo); "
                    f"ui={last_ui}; invoked={sorted(invoked)}; api={api_url}"
                )
        bridge = await chat.evaluate(
            """(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {})()""",
            await_promise=False,
            recv_timeout=10.0,
        )
        is_streaming = isinstance(bridge, dict) and bridge.get("isStreaming") is True
        if is_streaming:
            stream_idle_since = None
        elif stream_idle_since is None:
            stream_idle_since = time.monotonic()

        if isinstance(bridge, dict) and not is_streaming:
            sample = str(bridge.get("lastAssistantSample") or "")
            if sample.strip() and not has_bash:
                raise AssertionError(
                    "Model finished without invoking bash_code_execute_tool; "
                    f"assistant={sample[:400]!r}; ui={last_ui}; api={api_url}"
                )
            if (
                stream_idle_since is not None
                and not has_bash
                and time.monotonic() - stream_idle_since >= _STALL_AFTER_STREAM_SEC
            ):
                raise AssertionError(
                    "Stream idle without bash_code_execute_tool; "
                    f"idle_sec={time.monotonic() - stream_idle_since:.0f}; "
                    f"ui={last_ui}; api={api_url}"
                )
            if has_bash and not last_ui.get("hasDialog") and stream_idle_since is not None:
                idle = time.monotonic() - stream_idle_since
                if idle >= 120.0:
                    raise AssertionError(
                        "bash invoked on API but ToolApproval dialog never opened; "
                        f"idle_sec={idle:.0f}; ui={last_ui}; invoked={sorted(invoked)}"
                    )
        await asyncio.sleep(1.0)

    raise AssertionError(
        "Shell approval UI did not appear; "
        f"ui={last_ui}; invoked={sorted(last_invoked)}; api={api_url}"
    )


async def _run_live_pattern_flow(chat: McpChatSession, agent_id: str, *, api_url: str) -> str:
    await chat.dismiss_modals()
    await _wait_agent_applied(chat)
    await _assert_runtime_binding(chat, expected_api=api_url)
    await chat.click_new_chat()
    await chat.ensure_chat_surface(BASE_URL)

    send_result = await chat.send_message(_USER_PROMPT, _USER_PROMPT)
    chat_id_hint = str(
        send_result.get("started", {}).get("chatId")
        or send_result.get("submit", {}).get("chatId")
        or ""
    ).strip()

    started = await chat.wait_stream_started(
        _USER_PROMPT, timeout_sec=120.0, chat_id_hint=chat_id_hint or None
    )
    chat_id = chat_id_hint or str(started.get("chatId") or "").strip() or None
    if not chat_id:
        after_start = await chat.main_state(_USER_PROMPT, recv_timeout=30.0)
        chat_id = (
            chat_id_from_path(str(after_start.get("path") or ""))
            or str(after_start.get("bridgeChatId") or "").strip()
            or None
        )
    assert chat_id, f"Expected chat id after stream start: started={started}; send={send_result}"

    await chat.navigate_to_chat(chat_id, BASE_URL, timeout_sec=90.0)
    await _assert_runtime_binding(chat, expected_api=api_url)
    await _wait_for_shell_approval_ui(chat, chat_id, api_url=api_url, timeout_sec=_APPROVAL_WAIT_SEC)

    click_always = await chat.evaluate(_CLICK_ALLOW_ALWAYS_JS, await_promise=False)
    assert isinstance(click_always, dict) and click_always.get("ok") is True, click_always
    await asyncio.sleep(0.5)

    select_scope = await chat.evaluate(_SELECT_PATTERN_SCOPE_JS, await_promise=False)
    assert isinstance(select_scope, dict) and select_scope.get("ok") is True, select_scope
    await asyncio.sleep(0.3)

    confirm = await chat.evaluate(_CONFIRM_ALLOW_ALWAYS_DIALOG_JS, await_promise=False)
    assert isinstance(confirm, dict) and confirm.get("ok") is True, confirm

    await _wait_for_eval(chat, _TURN_DONE_JS, timeout_sec=240.0)
    return chat_id


@pytest.fixture(autouse=True)
def _clear_allowlist_before_live(_chrome_e2e_item_runtime: object | None) -> None:
    api_base = get_e2e_api_url()
    ensure_e2e_hitl_mode(api_url=api_base)
    http_json(
        "DELETE",
        f"{api_base}/api/v1/security/allowlist/test/clear-pattern-fixture",
        expected_statuses=frozenset({200, 204, 404}),
    )
    yield
    http_json(
        "DELETE",
        f"{api_base}/api/v1/security/allowlist/test/clear-pattern-fixture",
        expected_statuses=frozenset({200, 204, 404}),
    )


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=True)
@pytest.mark.asyncio
async def test_live_agent_shell_allow_always_pattern_settings_roundtrip(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail("Provider not ready — seed WebUI model via chrome-e2e-model-seed.mjs")

    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url()
    agent_id = _create_shell_agent(api_base)
    e2e_resource_ledger.register("agent", agent_id)

    client = ChromeMcpClient(request_timeout_sec=180.0)
    await asyncio.to_thread(client.start)
    try:
        page: McpPage | None = None
        agent_url = f"{ui_base}/?agentId={agent_id}"
        last_error = ""
        chat_id = ""
        for attempt in range(1, _MAX_CHAT_ATTEMPTS + 1):
            heartbeat_e2e_lease()
            try:
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
                chat_id = await _run_live_pattern_flow(chat, agent_id, api_url=api_base)
                e2e_resource_ledger.register("chat", chat_id)
                break
            except (AssertionError, RuntimeError, TimeoutError) as exc:
                last_error = str(exc)
                if attempt >= _MAX_CHAT_ATTEMPTS:
                    raise
                await asyncio.sleep(2.0)
        else:
            pytest.fail(last_error or "live pattern flow failed")
        assert chat_id

        listed = http_json("GET", f"{api_base}/api/v1/security/allowlist")
        rows = listed.get("data") if isinstance(listed, dict) else None
        assert isinstance(rows, list) and len(rows) >= 1, listed
        pattern_rows = [row for row in rows if row.get("granularity") == "pattern"]
        assert pattern_rows, rows
        assert any("ALLOWLIST_LIVE_PROBE" in str(row.get("command_pattern", "")) for row in pattern_rows)

        warm_ui_route("/settings/security")
        await asyncio.to_thread(
            client.navigate, page, f"{ui_base}/settings/security", timeout_ms=90_000
        )
        shell = await asyncio.to_thread(
            wait_for_state,
            client,
            page,
            SETTINGS_SECURITY_SHELL_READY_JS,
            timeout_sec=90.0,
        )
        assert shell.get("ready") is True, shell
        visible = await asyncio.to_thread(
            wait_for_state,
            client,
            page,
            SETTINGS_PATTERN_VISIBLE_JS,
            timeout_sec=60.0,
        )
        assert visible.get("ready") is True, visible
    finally:
        client.close()
