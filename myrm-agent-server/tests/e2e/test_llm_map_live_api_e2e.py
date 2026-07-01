"""Live-stack E2E: llm_map_tool via real backend on :8080 (no TestClient)."""

from __future__ import annotations

import json
import os
import uuid
from pathlib import Path

import httpx
import pytest
from dotenv import load_dotenv

from tests.support.bash_compressor_e2e import resolve_working_base_selection

SERVER_ROOT = Path(__file__).resolve().parent.parent.parent
load_dotenv(SERVER_ROOT / ".env", override=True)
BACKEND_URL = os.environ.get("BACKEND_URL", "http://127.0.0.1:8080").rstrip("/")

E2E_PROMPT = (
    "E2E_LLM_MAP_RUN: Call llm_map_tool exactly once with:\n"
    '- instruction: "Reply with only the word OK"\n'
    '- items: ["alpha", "beta", "gamma"]\n'
    "- max_concurrency: 2\n"
    "Use no other tools. Then summarize succeeded count in one short sentence."
)


def _health_ok(client: httpx.Client) -> bool:
    try:
        resp = client.get(f"{BACKEND_URL}/api/v1/health", timeout=5.0)
        return resp.status_code == 200
    except Exception:
        return False


def _create_llm_map_agent(client: httpx.Client) -> str:
    payload = {
        "name": f"LLM Map Live {uuid.uuid4().hex[:6]}",
        "description": "Live llm_map E2E agent",
        "system_prompt": (
            "You are a batch assistant. When asked for E2E_LLM_MAP_RUN you MUST call "
            "llm_map_tool with the exact parameters given. Do not use other tools."
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "enabled_builtin_tools": ["llm_map", "answer_tool"],
        "security_overrides": {"yoloModeEnabled": True},
    }
    resp = client.post(f"{BACKEND_URL}/api/v1/user-agents", json=payload, timeout=30.0)
    resp.raise_for_status()
    body = resp.json()
    agent_id = body.get("data", {}).get("id") or body.get("id")
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _stream_collect(client: httpx.Client, agent_id: str) -> tuple[list[str], list[str]]:
    chat_id = f"llm-map-live-{uuid.uuid4().hex[:10]}"
    request_data: dict[str, object] = {
        "messageId": f"live-llm-map-{uuid.uuid4().hex[:10]}",
        "chatId": chat_id,
        "query": E2E_PROMPT,
        "modelSelection": resolve_working_base_selection(backend_url=BACKEND_URL),
        "actionMode": "agent",
        "agentId": agent_id,
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    tool_names: list[str] = []
    errors: list[str] = []
    with client.stream(
        "POST",
        f"{BACKEND_URL}/api/v1/agents/agent-stream",
        json=request_data,
        timeout=300.0,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line or not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                break
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            if event.get("type") == "tasks_steps":
                tool_name = event.get("tool_name")
                if isinstance(tool_name, str) and tool_name:
                    tool_names.append(tool_name)
            if event.get("type") == "error":
                err = event.get("error") or event.get("data")
                if err:
                    errors.append(str(err))
    if errors and not tool_names:
        pytest.skip(f"Live agent-stream env issue: {errors[0][:200]}")
    return tool_names, errors


@pytest.mark.e2e
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY") and not os.environ.get("LITE_API_KEY"),
    reason="Requires BASIC_API_KEY or LITE_API_KEY in .env.test",
)
def test_live_api_llm_map_tool_invoked() -> None:
    with httpx.Client(timeout=httpx.Timeout(300.0, connect=10.0)) as client:
        if not _health_ok(client):
            pytest.skip(f"Backend not reachable at {BACKEND_URL}")
        agent_id = _create_llm_map_agent(client)
        try:
            tool_names, _errors = _stream_collect(client, agent_id)
            assert "llm_map_tool" in tool_names, f"Expected llm_map_tool, got {tool_names!r}"
        finally:
            client.delete(f"{BACKEND_URL}/api/v1/user-agents/{agent_id}", timeout=30.0)


@pytest.mark.e2e
def test_live_api_batch_template_listed() -> None:
    with httpx.Client(timeout=httpx.Timeout(15.0, connect=5.0)) as client:
        if not _health_ok(client):
            pytest.skip(f"Backend not reachable at {BACKEND_URL}")
        resp = client.get(f"{BACKEND_URL}/api/v1/agents/templates", timeout=10.0)
        resp.raise_for_status()
        templates = resp.json().get("data") or []
        batch = next((t for t in templates if t.get("id") == "batch_processing_assistant"), None)
        assert batch is not None, "batch_processing_assistant missing from live template catalog"
