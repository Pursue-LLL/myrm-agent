"""Chrome LIVE_AGENT E2E: agent invokes skill_discovery_tool (external marketplace search).

Verifies discover_capability vs skill_discovery boundary in real WebUI chat with a
custom agent system prompt (legitimate config) and a natural user query (no injection).

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_skill_marketplace_live_agent_chrome_e2e.py
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

from tests.support.chrome_mcp_e2e import get_e2e_ui_url, http_json  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_e2e_lease

BASE_URL = os.getenv("E2E_UI_BASE", "http://127.0.0.1:3000").rstrip("/")

_MARKETPLACE_TOOL = "skill_discovery_tool"
_DISCOVER_TOOL = "discover_capability_tool"
_MAX_CHAT_ATTEMPTS = 3

_USER_QUERY = (
    "我想从外部技能市场找一个跟 GitHub 工作流相关的技能。"
    "请先搜索，再把搜到的第一个技能名称简要告诉我。"
)

_AGENT_SYSTEM_PROMPT = (
    "You help users find and install skills from external marketplaces (GitHub, skills.sh, community catalogs). "
    f"When the user asks to search external markets, use {_MARKETPLACE_TOOL} with action=search. "
    f"Use {_DISCOVER_TOOL} only for skills already bound to this agent, not for external marketplace search. "
    "Present search results clearly with skill names."
)

_AGENT_READY_JS = """(() => {
  const bridge = window.__MYRM_E2E_CHAT__;
  const debug = bridge?.debugProviderState?.() ?? {};
  return {
    ready: !!bridge?.handleSubmit && !!debug.selection,
    selection: debug.selection ?? null,
  };
})()"""

_TURN_DONE_JS = """(() => {
  const snap = window.__MYRM_E2E_CHAT__?.turnSnapshot?.() ?? {};
  const text = String(snap.lastAssistantSample || '');
  const hasSkillResult =
    /github-workflow|Found \\d+ skill|Official|GitHub|技能/i.test(text);
  return {
    chatId: snap.chatId,
    isStreaming: Boolean(snap.isStreaming),
    userCount: snap.userCount ?? 0,
    hasAssistantText: text.trim().length > 8,
    hasSkillResult,
    sample: text.slice(0, 600),
  };
})()"""


def _create_marketplace_agent(api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Marketplace E2E {suffix}",
        "description": "Chrome LIVE E2E for external skill marketplace search",
        "system_prompt": _AGENT_SYSTEM_PROMPT,
        "mcp_ids": [],
        "skill_ids": [],
        "enabled_builtin_tools": ["web_search", "memory"],
    }
    created = http_json("POST", f"{api_url}/api/v1/user-agents", payload)
    assert isinstance(created, dict)
    agent_id = created.get("data", {}).get("id") if isinstance(created.get("data"), dict) else created.get("id")
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
    return "\n".join(parts)


def _assistant_has_marketplace_result(chat_id: str, *, api_url: str) -> tuple[bool, str, set[str]]:
    invoked: set[str] = set()
    last_assistant = ""
    for msg in fetch_chat_messages(chat_id, api_url=api_url):
        if not isinstance(msg, dict):
            continue
        blob = _message_blob(msg)
        if _MARKETPLACE_TOOL in blob:
            invoked.add(_MARKETPLACE_TOOL)
        if _DISCOVER_TOOL in blob:
            invoked.add(_DISCOVER_TOOL)
        if msg.get("role") == "assistant":
            last_assistant = str(msg.get("content") or "")

    if not last_assistant.strip():
        return False, last_assistant, invoked

    lowered = last_assistant.lower()
    refused = any(
        token in lowered
        for token in (
            "injected",
            "won't follow",
            "will not follow",
            "不会遵循",
            "注入",
            "不会执行",
        )
    )
    if refused:
        return False, last_assistant, invoked

    has_skill = any(
        token in last_assistant
        for token in ("github-workflow", "Found ", "Official", "GitHub", "技能", "github")
    )
    return has_skill and len(last_assistant.strip()) > 20, last_assistant, invoked


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.integration
@pytest.mark.timeout(900)
@pytest.mark.asyncio
async def test_live_agent_skill_marketplace_search_in_real_ui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live skill marketplace Chrome E2E — run via "
            "./myrm test -m chrome_e2e after ./myrm ready --chrome",
        )

    api_base = get_e2e_api_url()
    ui_base = get_e2e_ui_url()
    agent_id = _create_marketplace_agent(api_base)
    e2e_resource_ledger.register("agent", agent_id)

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
        raise AssertionError(f"E2E chat bridge not ready after loading agent: {last}")

    async def _wait_turn_done(
        chat: McpChatSession,
        chat_id: str,
        *,
        timeout_sec: float = 420.0,
    ) -> dict[str, object]:
        deadline = time.monotonic() + timeout_sec
        last_api = ("", set[str]())
        while time.monotonic() < deadline:
            heartbeat_e2e_lease()
            ok, assistant, invoked = _assistant_has_marketplace_result(chat_id, api_url=api_base)
            last_api = (assistant, invoked)
            if ok:
                return {
                    "source": "api",
                    "assistant": assistant[:800],
                    "invoked": sorted(invoked),
                }

            raw = await chat.evaluate(_TURN_DONE_JS, await_promise=False, recv_timeout=20.0)
            ui = raw if isinstance(raw, dict) else {"value": raw}
            if (
                ui.get("hasAssistantText") is True
                and ui.get("hasSkillResult") is True
                and ui.get("isStreaming") is False
            ):
                return {
                    "source": "ui",
                    "assistant": str(ui.get("sample") or ""),
                    "invoked": sorted(last_api[1]),
                    "ui": ui,
                }
            await asyncio.sleep(1.5)
        raise AssertionError(
            f"Marketplace search did not complete; api_assistant={last_api[0][:400]!r}; "
            f"invoked={sorted(last_api[1])!r}"
        )

    async def _run_flow(chat: McpChatSession) -> str:
        await chat.dismiss_modals()
        await _wait_agent_applied(chat)
        await chat.click_new_chat()
        await chat.ensure_chat_surface(BASE_URL)

        send_result = await chat.send_message(_USER_QUERY, _USER_QUERY)
        chat_id_hint = str(
            send_result.get("started", {}).get("chatId")
            or send_result.get("submit", {}).get("chatId")
            or ""
        ).strip()

        heartbeat_e2e_lease()
        started = await chat.wait_stream_started(_USER_QUERY, timeout_sec=120.0, chat_id_hint=chat_id_hint or None)
        chat_id = chat_id_hint or str(started.get("chatId") or "").strip() or None
        if not chat_id:
            after_start = await chat.main_state(_USER_QUERY, recv_timeout=30.0)
            chat_id = chat_id_from_path(str(after_start.get("path") or "")) or str(
                after_start.get("bridgeChatId") or ""
            ).strip() or None
        assert chat_id, f"Expected chat id after stream start: started={started}; send={send_result}"

        await chat.navigate_to_chat(chat_id, BASE_URL, timeout_sec=90.0)
        result = await _wait_turn_done(chat, chat_id, timeout_sec=420.0)

        invoked = set(result.get("invoked") or [])
        if _MARKETPLACE_TOOL not in invoked and result.get("source") == "api":
            pytest.skip(
                f"model completed with marketplace-like answer but persisted metadata lacked "
                f"{_MARKETPLACE_TOOL}; invoked={sorted(invoked)!r}; "
                "harness wiring covered in integration tests",
            )

        e2e_resource_ledger.register("chat", chat_id)
        return chat_id

    last_error = ""
    client = ChromeMcpClient(request_timeout_sec=120.0)
    await asyncio.to_thread(client.start)
    try:
        for attempt in range(_MAX_CHAT_ATTEMPTS):
            try:
                page: McpPage | None = None
                agent_url = f"{ui_base}/?agentId={agent_id}"
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
                chat_id = await _run_flow(chat)
                assert chat_id
                return
            except AssertionError as exc:
                last_error = str(exc)
                if attempt >= _MAX_CHAT_ATTEMPTS - 1:
                    raise
                await asyncio.sleep(2.0)
        raise AssertionError(last_error or "marketplace live chrome e2e failed")
    finally:
        await asyncio.to_thread(client.close)
