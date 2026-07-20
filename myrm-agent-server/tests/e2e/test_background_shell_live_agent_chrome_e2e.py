"""Chrome E2E LIVE_AGENT: real agent-stream spawns background shell → panel shows running job."""

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
from tests.support.chrome_mcp_e2e import (
    get_e2e_ui_url,
    http_json,
    open_mcp_page,
    wait_for_state,
    warm_ui_route,
)

_OPEN_PANEL_JS = """(() => {
  const btn = document.querySelector('button[aria-label="Background Tasks"], button[aria-label="后台任务"]');
  if (!btn) return { ready: false, clicked: false };
  btn.click();
  return { ready: true, clicked: true };
})()"""

_PANEL_READY_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasTitle = /Background Tasks|后台任务/.test(text);
  const hasShellSection = /Long-running tasks|耗时任务/.test(text);
  return { ready: hasTitle && hasShellSection, text: text.slice(0, 400) };
})()"""

_PANEL_RUNNING_JS = """(() => {
  const text = document.body?.innerText || '';
  const hasRunning = /running|运行中/i.test(text);
  const hasShell = /Long-running tasks|耗时任务/i.test(text);
  return { ready: hasRunning && hasShell, text: text.slice(0, 500) };
})()"""

_BG_SPAWN_PROMPT = (
    "E2E_BACKGROUND_SHELL: Call bash_code_execute_tool exactly once with:\n"
    '- command: python3 -c "import time; time.sleep(120)"\n'
    "- run_in_background: true\n"
    "- reason: live agent background shell e2e\n"
    "Then reply with ONLY the numeric pid from tool metadata."
)


def _ensure_ui_healthy(client, page) -> None:
    """Reload once if Next error boundary is showing (common under parallel E2E load)."""
    from tests.support.chrome_mcp_e2e import _coerce_evaluate_result

    deadline = time.monotonic() + 90.0
    reloaded = False
    probe_js = """(() => {
      const text = document.body?.innerText || '';
      const broken = /应用出错了|unexpected error|Application error/i.test(text);
      if (broken) {
        window.location.reload();
        return { ready: false, reloaded: true };
      }
      return {
        ready: !!document.querySelector('[data-testid="app-layout"]'),
        reloaded: false,
      };
    })()"""
    last: dict[str, object] = {}
    while time.monotonic() < deadline:
        raw = client.evaluate(page, probe_js, timeout_sec=15.0)
        last = _coerce_evaluate_result(raw)
        if last.get("ready") is True:
            return
        if last.get("reloaded") and not reloaded:
            reloaded = True
            time.sleep(2.0)
            continue
        time.sleep(0.5)
    raise AssertionError(f"UI did not recover from error boundary: {last}")


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
        "security_overrides": {"yoloModeEnabled": True},
    }
    resp = client.post(f"{api_base}/api/v1/user-agents", json=payload, timeout=60.0)
    resp.raise_for_status()
    body = resp.json()
    agent_id = body.get("data", {}).get("id") or body.get("id")
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _stream_background_spawn(client: httpx.Client, api_base: str, agent_id: str, chat_id: str) -> None:
    request_data: dict[str, object] = {
        "messageId": f"bg-shell-{uuid.uuid4().hex[:10]}",
        "chatId": chat_id,
        "query": _BG_SPAWN_PROMPT,
        "modelSelection": resolve_working_base_selection(backend_url=api_base),
        "actionMode": "agent",
        "agentId": agent_id,
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    with client.stream(
        "POST",
        f"{api_base}/api/v1/agents/agent-stream",
        json=request_data,
        timeout=600.0,
    ) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if line == "data: [DONE]":
                break


def _wait_for_running_shell(api_base: str, chat_id: str, timeout_sec: float = 120.0) -> str:
    deadline = time.monotonic() + timeout_sec
    while time.monotonic() < deadline:
        payload = http_json("GET", f"{api_base}/api/v1/background-tasks")
        assert isinstance(payload, dict)
        for row in payload.get("tasks", []):
            if not isinstance(row, dict):
                continue
            if row.get("kind") != "shell":
                continue
            if row.get("chat_id") == chat_id and row.get("status") == "running":
                task_id = row.get("task_id")
                if isinstance(task_id, str) and task_id.startswith("shell:"):
                    return task_id
                job_id = row.get("job_id")
                if isinstance(job_id, str) and job_id:
                    return f"shell:{job_id}"
        time.sleep(1.0)
    raise AssertionError(f"No running shell task for chat_id={chat_id} within {timeout_sec}s")


@pytest.mark.chrome_e2e(lane="LIVE_AGENT", private_backend=False)
@pytest.mark.timeout(600)
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY") or not os.environ.get("LITE_API_KEY"),
    reason="Requires BASIC_API_KEY and LITE_API_KEY from .env.test",
)
def test_live_agent_background_shell_visible_in_panel() -> None:
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

    warm_ui_route("/")
    with open_mcp_page(get_e2e_ui_url(), timeout_ms=120_000) as (client, page):
        _ensure_ui_healthy(client, page)
        opened = wait_for_state(client, page, _OPEN_PANEL_JS, timeout_sec=30.0)
        assert opened.get("clicked") is True, opened
        panel = wait_for_state(client, page, _PANEL_READY_JS, timeout_sec=30.0)
        assert panel.get("ready") is True, panel
        running_row = wait_for_state(client, page, _PANEL_RUNNING_JS, timeout_sec=90.0)
        assert running_row.get("ready") is True, running_row
