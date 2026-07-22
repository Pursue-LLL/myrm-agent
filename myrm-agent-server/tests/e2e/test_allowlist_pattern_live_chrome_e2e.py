"""Chrome LIVE_AGENT E2E: bash approval → allow-always pattern → Settings list.

Uses real WebUI chat (openai-like/mimo-v2.5-pro from .env.test seed) and Chrome MCP mux.
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

from cdp_chat_support import fetch_chat_messages, get_e2e_api_url, wait_e2e_provider_ready  # noqa: E402
from cdp_chat_ui import chat_id_from_path  # noqa: E402
from chrome_mcp_client import ChromeMcpClient, McpPage  # noqa: E402
from mcp_chat_ui import McpChatSession  # noqa: E402

from tests.support.chrome_allowlist_live_e2e import (
    _AGENT_READY_JS,
    _APPROVAL_VISIBLE_JS,
    _CLICK_ALLOW_ALWAYS_JS,
    _CONFIRM_ALLOW_ALWAYS_DIALOG_JS,
    _SELECT_PATTERN_SCOPE_JS,
    _TURN_DONE_JS,
)
from tests.support.chrome_allowlist_settings_e2e import SETTINGS_SECURITY_SHELL_READY_JS
from tests.support.chrome_mcp_e2e import get_e2e_ui_url, http_json, wait_for_state, warm_ui_route
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")
_BASH_TOOL = "bash_code_execute_tool"
_PATTERN_COMMAND = "echo E2E_ALLOWLIST_PATTERN"
_USER_PROMPT = (
    "You MUST call bash_code_execute_tool immediately with exactly this command and no other tools: "
    f"`{_PATTERN_COMMAND}`. Reason: allowlist pattern live e2e."
)
_MAX_CHAT_ATTEMPTS = 3


def _create_shell_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Allowlist Pattern LIVE {suffix}",
        "description": "Chrome LIVE E2E for shell allow-always pattern",
        "system_prompt": (
            "You MUST call bash_code_execute_tool when the user asks to run a shell command. "
            "Use the exact command string provided by the user. Do not reply with text only."
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "enabled_builtin_tools": ["code_execute"],
        "security_overrides": {"yoloModeEnabled": False, "autoModeEnabled": True},
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
    blob = ""
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


async def _wait_for_shell_approval_ui(
    chat: McpChatSession,
    chat_id: str,
    *,
    api_url: str,
    timeout_sec: float = 300.0,
) -> dict[str, object]:
    deadline = time.monotonic() + timeout_sec
    last_ui: dict[str, object] = {}
    last_invoked: set[str] = set()
    while time.monotonic() < deadline:
        heartbeat_e2e_lease()
        raw = await chat.evaluate(_APPROVAL_VISIBLE_JS, await_promise=False, recv_timeout=20.0)
        last_ui = raw if isinstance(raw, dict) else {"value": raw}
        if last_ui.get("ready") is True:
            return last_ui

        has_bash, invoked = _chat_bash_invocation(chat_id, api_url=api_url)
        last_invoked = invoked
        bridge = await chat.evaluate(
            """(() => window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {})()""",
            await_promise=False,
            recv_timeout=10.0,
        )
        if isinstance(bridge, dict) and bridge.get("isStreaming") is False and not has_bash:
            sample = str(bridge.get("lastAssistantSample") or "")
            if sample.strip():
                raise AssertionError(
                    "Model finished without invoking bash_code_execute_tool; "
                    f"assistant={sample[:400]!r}; ui={last_ui}"
                )
        await asyncio.sleep(1.0)

    raise AssertionError(
        "Shell approval UI did not appear; "
        f"ui={last_ui}; invoked={sorted(last_invoked)}"
    )


async def _run_live_pattern_flow(chat: McpChatSession, agent_id: str, *, api_url: str) -> str:
    await chat.dismiss_modals()
    await _wait_agent_applied(chat)
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
    await _wait_for_shell_approval_ui(chat, chat_id, api_url=api_url, timeout_sec=300.0)

    click_always = await chat.evaluate(_CLICK_ALLOW_ALWAYS_JS, await_promise=False)
    assert isinstance(click_always, dict) and click_always.get("ok") is True, click_always
    await asyncio.sleep(0.5)

    select_scope = await chat.evaluate(_SELECT_PATTERN_SCOPE_JS, await_promise=False)
    assert isinstance(select_scope, dict) and select_scope.get("ok") is True, select_scope
    await asyncio.sleep(0.3)

    confirm = await chat.evaluate(_CONFIRM_ALLOW_ALWAYS_DIALOG_JS, await_promise=False)
    assert isinstance(confirm, dict) and confirm.get("ok") is True, confirm

    await _wait_for_eval(chat, _TURN_DONE_JS, timeout_sec=300.0)
    return chat_id


@pytest.fixture(autouse=True)
def _clear_allowlist_before_live() -> None:
    api_base = get_e2e_api_url()
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


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.timeout(900)
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
        assert any("echo" in str(row.get("command_pattern", "")) for row in pattern_rows)

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
            """(() => {
              const text = document.body?.innerText || '';
              const hasPattern =
                text.includes('echo E2E_ALLOWLIST_PATTERN *') ||
                text.includes('echo E2E_ALLOWLIST_PATTERN');
              return { ready: hasPattern, sample: text.slice(0, 1200) };
            })()""",
            timeout_sec=60.0,
        )
        assert visible.get("ready") is True, visible
    finally:
        client.close()
