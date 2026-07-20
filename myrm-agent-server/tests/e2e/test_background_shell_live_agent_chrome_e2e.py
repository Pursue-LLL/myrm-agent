"""Chrome E2E LIVE_AGENT: agent-stream spawns a background shell (API-only).

Panel running-row UX is covered by ``test_background_tasks_panel_chrome_e2e.py`` (seed + cancel).
"""

from __future__ import annotations

import json
import os
import sys
import time
import uuid
from pathlib import Path

import httpx
import pytest

_LIB = Path(__file__).resolve().parents[3] / "scripts" / "dev" / "lib"
if str(_LIB) not in sys.path:
    sys.path.insert(0, str(_LIB))

from cdp_chat_support import get_e2e_api_url, wait_e2e_provider_ready  # noqa: E402

from tests.support.bash_compressor_e2e import resolve_working_base_selection
from tests.support.chrome_mcp_e2e import http_json

_BG_SPAWN_PROMPT = (
    "E2E_BACKGROUND_SHELL: Call bash_code_execute_tool exactly once with:\n"
    '- command: python3 -c "import time; time.sleep(120)"\n'
    "- run_in_background: true\n"
    "- reason: live agent background shell e2e\n"
    "Then reply with ONLY the numeric pid from tool metadata."
)


def _create_background_agent(client: httpx.Client, api_base: str) -> str:
    payload = {
        "name": f"BG Shell Live {uuid.uuid4().hex[:6]}",
        "description": "Live background shell Chrome E2E",
        "system_prompt": (
            "You MUST use bash_code_execute_tool when asked. "
            "Always pass run_in_background=true when instructed."
        ),
        "skill_ids": [],
        "mcp_ids": [],
        "enabled_builtin_tools": ["code_execute"],
        "security_overrides": {"yoloModeEnabled": True},
    }
    resp = client.post(f"{api_base}/api/v1/user-agents", json=payload, timeout=60.0)
    resp.raise_for_status()
    body = resp.json()
    agent_id = body.get("data", {}).get("id") or body.get("id")
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


def _stream_background_spawn(client: httpx.Client, api_base: str, agent_id: str, chat_id: str) -> None:
    request_data: dict[str, object] = {
        "messageId": f"bg-shell-{uuid.uuid4().hex[:10]}",
        "chatId": chat_id,
        "query": _BG_SPAWN_PROMPT,
        "modelSelection": resolve_working_base_selection(backend_url=api_base),
        "actionMode": "agent",
        "agentId": agent_id,
        "agentConfig": {"enabledBuiltinTools": ["code_execute"]},
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    def _consume_stream(payload: dict[str, object]) -> tuple[dict[str, object] | None, list[str]]:
        resume_payload: dict[str, object] | None = None
        tool_names: list[str] = []
        with client.stream(
            "POST",
            f"{api_base}/api/v1/agents/agent-stream",
            json=payload,
            timeout=600.0,
        ) as response:
            response.raise_for_status()
            for line in response.iter_lines():
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
                if event_type in ("tool_start", "tool_end", "tool_result"):
                    name = _tool_name_from_event(event)
                    if name:
                        tool_names.append(name)
                if event_type in ("interrupt", "tool_approval", "approval", "approval_required"):
                    data = event.get("data")
                    if isinstance(data, dict):
                        resume_payload = data
        return resume_payload, tool_names

    resume_payload, tool_names = _consume_stream(request_data)
    if resume_payload is not None:
        resume_request = {
            **request_data,
            "messageId": f"bg-shell-resume-{uuid.uuid4().hex[:10]}",
            "resumeValue": resume_payload,
        }
        resume_payload, resume_tools = _consume_stream(resume_request)
        tool_names.extend(resume_tools)

    if "bash_code_execute_tool" not in tool_names:
        raise AssertionError(
            f"agent-stream did not invoke bash_code_execute_tool; tools={tool_names or ['<none>']}",
        )


def _wait_for_running_shell(api_base: str, chat_id: str, timeout_sec: float = 180.0) -> str:
    deadline = time.monotonic() + timeout_sec
    fallback_task_id = ""
    while time.monotonic() < deadline:
        payload = http_json("GET", f"{api_base}/api/v1/background-tasks")
        assert isinstance(payload, dict)
        for row in payload.get("tasks", []):
            if not isinstance(row, dict):
                continue
            if row.get("kind") != "shell":
                continue
            if row.get("status") != "running":
                continue
            task_id = row.get("task_id")
            resolved = ""
            if isinstance(task_id, str) and task_id.startswith("shell:"):
                resolved = task_id
            else:
                job_id = row.get("job_id")
                if isinstance(job_id, str) and job_id:
                    resolved = f"shell:{job_id}"
            if not resolved:
                continue
            if row.get("chat_id") == chat_id:
                return resolved
            if not fallback_task_id:
                fallback_task_id = resolved
        if fallback_task_id:
            return fallback_task_id
        time.sleep(1.0)
    raise AssertionError(f"No running shell task for chat_id={chat_id} within {timeout_sec}s")


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.timeout(600)
def test_live_agent_background_shell_spawn_via_agent_stream() -> None:
    if not os.environ.get("BASIC_API_KEY") or not os.environ.get("LITE_API_KEY"):
        pytest.skip("Requires BASIC_API_KEY and LITE_API_KEY from .env.test")
    if not wait_e2e_provider_ready():
        pytest.fail("Provider config not ready — configure default model in WebUI E2E profile")

    api_base = get_e2e_api_url()
    chat_id = f"e2e-bgshell-{uuid.uuid4().hex[:10]}"

    with httpx.Client() as client:
        agent_id = _create_background_agent(client, api_base)
        _stream_background_spawn(client, api_base, agent_id, chat_id)

    task_id = _wait_for_running_shell(api_base, chat_id)
    row = http_json("GET", f"{api_base}/api/v1/background-tasks/{task_id}")
    assert isinstance(row, dict)
    assert row.get("status") == "running"
    assert row.get("chat_id") == chat_id
