"""Chrome LIVE_AGENT E2E: agent invokes skill_market_tool (external marketplace search).

Uses private SHPOIB agent-stream (same lane contract as background_shell LIVE) to verify
the live model calls skill_market_tool on a custom agent with skill_market mounted.
UI mount/toggle SSOT is covered by READ lane ``test_skill_mount_builtin_gate_chrome_e2e``.

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_skill_marketplace_live_agent_chrome_e2e.py
"""

from __future__ import annotations

import json
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import (  # noqa: E402
    fetch_chat_messages,
    get_e2e_api_url,
    wait_e2e_provider_ready,
)
from e2e_orchestrator import touch_wall_progress  # noqa: E402

from tests.support.chrome_mcp_e2e import guarded_httpx_request  # noqa: E402
from tests.support.e2e_runtime_guard import E2EResourceLedger, heartbeat_once

_MARKETPLACE_TOOL = "skill_market_tool"
_DISCOVER_TOOL = "skill_search_tool"
_MAX_STREAM_ATTEMPTS = 3

_USER_QUERY = (
    "我想从外部技能市场找一个跟 GitHub 工作流相关的技能。"
    "请先用 skill_market_tool 的 search 动作搜索外部市场，不要凭记忆回答。"
    "搜索完成后，把搜到的第一个技能名称简要告诉我。"
)

_AGENT_SYSTEM_PROMPT = (
    "You help users find and install skills from external marketplaces (GitHub, skills.sh, community catalogs). "
    f"When the user asks to search external markets, you MUST call {_MARKETPLACE_TOOL} with action=search "
    "before writing any answer. Never answer from memory or guess skill names. "
    f"Use {_DISCOVER_TOOL} only for skills already bound to this agent, not for external marketplace search. "
    "Present search results clearly with skill names."
)

_STREAM_TRANSPORT_ERRORS = (
    httpx.RemoteProtocolError,
    httpx.ConnectError,
    httpx.ReadError,
)
_RETRYABLE_STREAM_ERRORS = (AssertionError, httpx.HTTPError, httpx.TransportError)


def _create_marketplace_agent(client: httpx.Client, api_url: str) -> str:
    suffix = uuid.uuid4().hex[:8]
    payload = {
        "name": f"Marketplace E2E {suffix}",
        "description": "Chrome LIVE E2E for external skill marketplace search",
        "system_prompt": _AGENT_SYSTEM_PROMPT,
        "mcp_ids": [],
        "skill_ids": [],
        "enabled_builtin_tools": ["web_search", "memory", "skill_market"],
    }
    resp = guarded_httpx_request(
        client, "POST", f"{api_url}/api/v1/user-agents", json=payload, timeout=60.0
    )
    resp.raise_for_status()
    body = resp.json()
    agent_id = (
        body.get("data", {}).get("id")
        if isinstance(body.get("data"), dict)
        else body.get("id")
    )
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _tool_name_from_event(event: dict[str, object]) -> str | None:
    for key in ("tool_name", "name", "tool"):
        val = event.get(key)
        if isinstance(val, str) and val:
            return val
    data = event.get("data")
    if isinstance(data, dict):
        for key in ("tool_name", "name", "tool"):
            val = data.get(key)
            if isinstance(val, str) and val:
                return val
    return None


def _tool_names_from_event(event: dict[str, object]) -> list[str]:
    names: list[str] = []
    single = _tool_name_from_event(event)
    if single:
        names.append(single)
    data = event.get("data")
    if isinstance(data, dict):
        action_requests = data.get("actionRequests")
        if isinstance(action_requests, list):
            for req in action_requests:
                if not isinstance(req, dict):
                    continue
                action = req.get("action")
                if isinstance(action, str) and action:
                    names.append(action)
        action_type = data.get("action_type")
        if isinstance(action_type, str) and action_type:
            names.append(action_type)
    return names


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


def _invoked_tools_from_messages(chat_id: str, *, api_url: str) -> set[str]:
    invoked: set[str] = set()
    messages = fetch_chat_messages(chat_id, api_url=api_url)
    for msg in messages:
        if not isinstance(msg, dict):
            continue
        blob = _message_blob(msg)
        if _MARKETPLACE_TOOL in blob:
            invoked.add(_MARKETPLACE_TOOL)
        if _DISCOVER_TOOL in blob:
            invoked.add(_DISCOVER_TOOL)
        for step in msg.get("progressSteps") or []:
            if not isinstance(step, dict):
                continue
            tool_name = str(step.get("tool_name") or step.get("toolName") or "")
            if tool_name == _MARKETPLACE_TOOL:
                invoked.add(_MARKETPLACE_TOOL)
            if tool_name == _DISCOVER_TOOL:
                invoked.add(_DISCOVER_TOOL)
    return invoked


def _stream_marketplace_search(
    client: httpx.Client,
    *,
    api_url: str,
    agent_id: str,
    chat_id: str,
) -> tuple[list[str], list[str]]:
    request_data: dict[str, object] = {
        "messageId": f"skill-market-{uuid.uuid4().hex[:10]}",
        "chatId": chat_id,
        "query": _USER_QUERY,
        "actionMode": "agent",
        "agentId": agent_id,
        "agentConfig": {
            "enabledBuiltinTools": ["web_search", "memory", "skill_market"]
        },
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    tool_names: list[str] = []
    errors: list[str] = []
    with client.stream(
        "POST",
        f"{api_url}/api/v1/agents/agent-stream",
        json=request_data,
        timeout=600.0,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            heartbeat_once()
            touch_wall_progress(current_node="skill_market_live_stream")
            if line == "data: [DONE]":
                break
            if not line or not line.startswith("data: "):
                continue
            try:
                event = json.loads(line[6:])
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event_type = event.get("type")
            if event_type in (
                "tool_start",
                "tool_end",
                "tool_result",
                "tool_complete",
                "tool_failure",
                "tasks_steps",
            ):
                for name in _tool_names_from_event(event):
                    if name not in tool_names:
                        tool_names.append(name)
                if event_type == "tasks_steps" and event.get("status") == "error":
                    err = event.get("error")
                    if err:
                        errors.append(str(err))
            if event_type == "error":
                err = event.get("error") or event.get("data")
                if err:
                    errors.append(str(err))
    return tool_names, errors


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE", access_scope="NAMESPACE_WRITE", workload="LIVE"
, private_reason="live_shpoib")
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_live_agent_skill_marketplace_search_in_real_ui(
    e2e_resource_ledger: E2EResourceLedger,
) -> None:
    if not wait_e2e_provider_ready():
        pytest.fail(
            "Provider config not ready for live skill marketplace Chrome E2E — run via "
            "./myrm test -m chrome_e2e after ./myrm ready --chrome",
        )

    api_base = get_e2e_api_url()
    last_error = ""
    chat_id = ""

    for attempt in range(_MAX_STREAM_ATTEMPTS):
        chat_id = f"e2e-skillmkt-{uuid.uuid4().hex[:10]}"
        heartbeat_once()
        touch_wall_progress(current_node="skill_market_live_attempt")
        try:
            with httpx.Client() as client:
                chat_resp = guarded_httpx_request(
                    client,
                    "POST",
                    f"{api_base}/api/v1/chats/",
                    json={"chat_id": chat_id},
                    timeout=30.0,
                )
                chat_resp.raise_for_status()
                agent_id = _create_marketplace_agent(client, api_base)
                e2e_resource_ledger.register("agent", agent_id)
                stream_tools, stream_errors = _stream_marketplace_search(
                    client,
                    api_url=api_base,
                    agent_id=agent_id,
                    chat_id=chat_id,
                )
            break
        except _RETRYABLE_STREAM_ERRORS as exc:
            last_error = str(exc)
            if attempt >= _MAX_STREAM_ATTEMPTS - 1:
                raise AssertionError(last_error) from exc
            time.sleep(2.0)
    else:
        raise AssertionError(last_error or "skill marketplace live stream failed")

    persisted = _invoked_tools_from_messages(chat_id, api_url=api_base)
    invoked = set(stream_tools) | persisted
    assert _MARKETPLACE_TOOL in invoked, (
        f"Expected {_MARKETPLACE_TOOL} in live stream or persisted chat; "
        f"stream_tools={stream_tools!r}; persisted={sorted(persisted)!r}; "
        f"stream_errors={stream_errors!r}"
    )
    e2e_resource_ledger.register("chat", chat_id)
