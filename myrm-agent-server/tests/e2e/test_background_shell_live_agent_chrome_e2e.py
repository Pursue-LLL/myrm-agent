"""Chrome E2E LIVE_AGENT: agent-stream spawns a background shell (API-only).

Panel running-row UX is covered by ``test_background_tasks_panel_chrome_e2e.py`` (seed + cancel).
Teardown cancels the spawned shell via ``POST /background-tasks/{task_id}/cancel`` (best-effort).
Failed wait attempts cancel running shells for that ``chat_id`` before retry (no cross-attempt orphans).

Formal run (须 ``-m chrome_e2e``；不传 ``modelSelection``，使用 WebUI ``defaultModelConfig``)::

    ./myrm test -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_background_shell_live_agent_chrome_e2e.py \\
      ::test_live_agent_background_shell_spawn_via_agent_stream
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

from cdp_chat_support import get_e2e_api_url, wait_e2e_provider_ready  # noqa: E402

from tests.support.chrome_mcp_e2e import http_json

_STREAM_TRANSPORT_ERRORS = (httpx.RemoteProtocolError, httpx.ConnectError, httpx.ReadError)

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


def _shell_task_id_from_row(row: dict[str, object]) -> str | None:
    task_id = row.get("task_id")
    if isinstance(task_id, str) and task_id.startswith("shell:"):
        return task_id
    job_id = row.get("job_id")
    if isinstance(job_id, str) and job_id:
        return f"shell:{job_id}"
    return None


def _cancel_background_task_best_effort(api_base: str, task_id: str) -> None:
    """Teardown helper: cancel a spawned shell without masking test failures."""
    try:
        http_json(
            "POST",
            f"{api_base}/api/v1/background-tasks/{task_id}/cancel",
            expected_statuses=frozenset({200, 201, 400}),
        )
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError):
        pass


def _cancel_running_shells_for_chat_best_effort(api_base: str, chat_id: str) -> None:
    """Cancel running shell tasks for one chat (failed-attempt cleanup before retry)."""
    try:
        payload = http_json("GET", f"{api_base}/api/v1/background-tasks")
        if not isinstance(payload, dict):
            return
        for row in payload.get("tasks", []):
            if not isinstance(row, dict):
                continue
            if row.get("kind") != "shell":
                continue
            if row.get("status") != "running":
                continue
            if row.get("chat_id") != chat_id:
                continue
            task_id = _shell_task_id_from_row(row)
            if task_id is not None:
                _cancel_background_task_best_effort(api_base, task_id)
    except (RuntimeError, OSError, ValueError, json.JSONDecodeError):
        pass


def _stream_background_spawn(client: httpx.Client, api_base: str, agent_id: str, chat_id: str) -> None:
    request_data: dict[str, object] = {
        "messageId": f"bg-shell-{uuid.uuid4().hex[:10]}",
        "chatId": chat_id,
        "query": _BG_SPAWN_PROMPT,
        "actionMode": "agent",
        "agentId": agent_id,
        "agentConfig": {"enabledBuiltinTools": ["code_execute"]},
        "yoloModeEnabled": True,
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }

    def _consume_stream(payload: dict[str, object]) -> tuple[dict[str, object] | None, list[str], list[str]]:
        resume_payload: dict[str, object] | None = None
        tool_names: list[str] = []
        errors: list[str] = []
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
                if event_type in ("tool_start", "tool_end", "tool_result", "tasks_steps"):
                    name = _tool_name_from_event(event)
                    if name:
                        tool_names.append(name)
                if event_type == "error":
                    err = event.get("error") or event.get("data")
                    if err:
                        errors.append(str(err))
                if event_type in ("interrupt", "tool_approval", "approval", "approval_required"):
                    data = event.get("data")
                    if isinstance(data, dict):
                        resume_payload = data
        return resume_payload, tool_names, errors

    def _run_stream_once(payload: dict[str, object]) -> None:
        resume_payload, tool_names, errors = _consume_stream(payload)
        if resume_payload is not None:
            resume_request = {
                **payload,
                "messageId": f"bg-shell-resume-{uuid.uuid4().hex[:10]}",
                "resumeValue": resume_payload,
            }
            _, resume_tools, resume_errors = _consume_stream(resume_request)
            tool_names.extend(resume_tools)
            errors.extend(resume_errors)

        if "bash_code_execute_tool" not in tool_names:
            detail = errors[0][:300] if errors else "no tool events in agent-stream"
            pytest.fail(
                f"agent-stream did not invoke bash_code_execute_tool; "
                f"tools={tool_names or ['<none>']}; detail={detail}",
            )

    for stream_attempt in range(2):
        stream_payload = dict(request_data)
        if stream_attempt == 1:
            stream_payload["messageId"] = f"bg-shell-retry-{uuid.uuid4().hex[:10]}"
        try:
            _run_stream_once(stream_payload)
            return
        except _STREAM_TRANSPORT_ERRORS:
            if stream_attempt == 1:
                raise
            # Stream may drop after spawn; avoid double-spawn retry when shell is already running.
            try:
                _wait_for_running_shell(api_base, chat_id, timeout_sec=10.0)
                return
            except AssertionError:
                continue


def _wait_for_running_shell(api_base: str, chat_id: str, timeout_sec: float = 180.0) -> str:
    deadline = time.monotonic() + timeout_sec
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
            if row.get("chat_id") != chat_id:
                continue
            task_id = _shell_task_id_from_row(row)
            if task_id is not None:
                return task_id
        time.sleep(1.0)
    raise AssertionError(f"No running shell task for chat_id={chat_id} within {timeout_sec}s")


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.timeout(600)
def test_live_agent_background_shell_spawn_via_agent_stream() -> None:
    if not wait_e2e_provider_ready():
        pytest.fail("Provider config not ready — configure default model in WebUI E2E profile")

    api_base = get_e2e_api_url()
    last_error = ""
    task_id: str | None = None

    try:
        for attempt in range(2):
            chat_id = f"e2e-bgshell-{uuid.uuid4().hex[:10]}"
            with httpx.Client() as client:
                chat_resp = client.post(f"{api_base}/api/v1/chats/", json={"chat_id": chat_id}, timeout=30.0)
                chat_resp.raise_for_status()
                agent_id = _create_background_agent(client, api_base)
                _stream_background_spawn(client, api_base, agent_id, chat_id)
            try:
                task_id = _wait_for_running_shell(api_base, chat_id, timeout_sec=240.0)
                break
            except AssertionError as exc:
                last_error = str(exc)
                _cancel_running_shells_for_chat_best_effort(api_base, chat_id)
                if attempt == 1:
                    raise AssertionError(last_error) from exc
        else:
            raise AssertionError(last_error or "background shell spawn failed")

        row = http_json("GET", f"{api_base}/api/v1/background-tasks/{task_id}")
        assert isinstance(row, dict)
        assert row.get("status") == "running"
        assert row.get("chat_id") == chat_id
    finally:
        if task_id is not None:
            _cancel_background_task_best_effort(api_base, task_id)
