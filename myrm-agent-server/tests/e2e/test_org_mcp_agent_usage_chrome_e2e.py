"""Chrome E2E: org-managed MCP server invoked during a live agent chat.

[INPUT]
- Control Plane pushes an org-level stdio MCP server via ``POST /api/admin/org-mcp-sync``.
- WebUI chat sends a message that requires calling the org MCP server's tool.

[OUTPUT]
- The assistant turn completes and the tool result (``pong``) surfaces in the
  persisted chat messages — proving org MCPs are wired into the live agent path
  end to end (sync → merge → agent toolset → tool call → UI result).
"""

from __future__ import annotations

import asyncio
import json
import sys
from pathlib import Path

import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat.support import (  # noqa: E402
    ensure_e2e_yolo_mode,
    fetch_chat_messages,
    get_e2e_api_url,
    get_e2e_ui_url,
)
from cdp_chat.ui import chat_id_from_path, wait_e2e_provider_ready  # noqa: E402
from chrome_mcp.client import ChromeMcpClient, McpPage  # noqa: E402
from dev_gate.contract import EvaluateIntent  # noqa: E402
from cdp_chat.mcp_ui import McpChatSession  # noqa: E402

from tests.support.chrome_mcp_e2e import http_json  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once  # noqa: E402

_ORG_PROBE_NAME = "e2e-minimal"
_ORG_MCP_SYNC_PATH = "/api/admin/org-mcp-sync"
_STDIO_STUB = (
    Path(__file__).resolve().parents[1] / "support" / "e2e_minimal_stdio_mcp_server.py"
)

E2E_PROMPT = (
    "请调用 e2e-minimal MCP server 提供的 ping 工具。这是一个真实存在的 MCP 工具，"
    "必须真正调用它，禁止自己编造或用代码模拟。然后把工具返回的原始结果一字不差地告诉我，"
    "最后回复 OK。"
)
TURN_WAIT_SEC = 120.0


def _sync_org_mcp(api_url: str, servers: list[dict[str, object]]) -> None:
    resp = http_json(
        "POST",
        f"{api_url}{_ORG_MCP_SYNC_PATH}",
        {"mcp_servers": servers},
    )
    assert isinstance(resp, dict) and resp.get("status") == "synced", resp


def _org_mcp_server_names(api_url: str) -> list[str]:
    record = http_json("GET", f"{api_url}/api/v1/config/orgMcpServers")
    assert isinstance(record, dict), record
    value = record.get("value") or {}
    servers = value.get("servers") or []
    assert isinstance(servers, list), servers
    return [str(s.get("name", "")) for s in servers if isinstance(s, dict)]


def _pong_evidence(messages: list[dict[str, object]]) -> str:
    """Return the first ``pong`` evidence in tool results or assistant text."""
    for msg in messages:
        role = str(msg.get("role") or "")
        content = msg.get("content")
        if isinstance(content, str):
            text = content
        elif isinstance(content, list):
            parts: list[str] = []
            for chunk in content:
                if isinstance(chunk, str):
                    parts.append(chunk)
                elif isinstance(chunk, dict):
                    text_chunk = chunk.get("text")
                    if isinstance(text_chunk, str):
                        parts.append(text_chunk)
            text = "".join(parts)
        else:
            continue
        if "pong" in text.lower():
            return f"{role}:{text[:120]}"
    return ""


def _extract_chat_id(url: str) -> str | None:
    from urllib.parse import urlparse

    return chat_id_from_path(urlparse(url).path)


async def _resolve_chat_id(
    chat: McpChatSession,
    state: dict[str, object],
) -> str | None:
    chat_id = _extract_chat_id(str(state.get("url") or ""))
    if not chat_id:
        chat_id = str(state.get("chatId") or "").strip() or None
    if chat_id:
        return chat_id
    base = get_e2e_ui_url().rstrip("/")
    href = await chat.evaluate(
        f"""(() => {{
          const base = {json.dumps(base)};
          const links = Array.from(document.querySelectorAll('aside a[href]'))
            .map((anchor) => anchor.href)
            .filter((url) => url.startsWith(base) && !url.endsWith('/') && !url.includes('/settings'));
          return links[0] || location.href;
        }})()""",
        intent=EvaluateIntent.SYNC_PROBE,
    )
    return _extract_chat_id(str(href) if href else "")


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="GLOBAL_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
@pytest.mark.asyncio
async def test_org_mcp_tool_invoked_in_live_chat(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    """Org-pushed MCP server's tool is actually called and its result surfaces."""
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live E2E — run via ./myrm test -m chrome_e2e "
            "after ./myrm ready --chrome (API /api/v1/config/readiness provider.is_ready must be true)"
        )

    api_url = get_e2e_api_url()
    probe = {
        "name": _ORG_PROBE_NAME,
        "type": "stdio",
        "command": sys.executable,
        "args": [str(_STDIO_STUB)],
        "description": "E2E org-managed MCP probe",
    }
    _sync_org_mcp(api_url, [probe])
    assert _org_mcp_server_names(api_url) == [_ORG_PROBE_NAME], (
        "org MCP config not visible on the private E2E backend"
    )
    ensure_e2e_yolo_mode(api_url=api_url)
    try:
        client = ChromeMcpClient(request_timeout_sec=180.0)
        await asyncio.to_thread(client.start)
        try:
            page: McpPage | None = await asyncio.to_thread(
                client.new_page,
                get_e2e_ui_url().rstrip("/"),
                timeout_ms=120_000,
            )
            if page is None:
                raise RuntimeError("new_page returned no page")

            chat = McpChatSession(client, page)
            await chat.bootstrap(
                get_e2e_ui_url().rstrip("/"),
                navigate=False,
                timeout_sec=180.0,
            )
            await chat.click_new_chat()
            heartbeat_once()

            first_send = await chat.send_message(E2E_PROMPT, E2E_PROMPT)
            chat_id_hint = str(
                first_send.get("started", {}).get("chatId")
                or first_send.get("submit", {}).get("chatId")
                or ""
            ).strip() or None

            after = await chat.wait_turn_done(
                E2E_PROMPT,
                chat_id_hint=chat_id_hint,
                timeout_sec=TURN_WAIT_SEC,
            )
            if str(after.get("path", "")).startswith("/settings"):
                pytest.fail(f"Send redirected to settings: {after}")

            chat_id = await _resolve_chat_id(chat, after)
            assert chat_id, f"Expected chat id after turn: {after}"
            e2e_resource_ledger.register("chat", chat_id)

            messages = fetch_chat_messages(chat_id, api_url=api_url)
            evidence = _pong_evidence(messages)
            assert evidence, (
                f"Expected org MCP tool result 'pong' in chat {chat_id} messages; "
                f"got {json.dumps(messages, ensure_ascii=False)[:2000]}"
            )
        finally:
            await asyncio.to_thread(client.close)
    finally:
        _sync_org_mcp(api_url, [])
