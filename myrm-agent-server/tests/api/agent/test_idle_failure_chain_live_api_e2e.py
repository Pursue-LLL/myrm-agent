"""Live-stack E2E: a real tool failure schedules only the supported idle tasks.

Task flow: a real agent turn runs a shell command that fails, the turn ends, and the
post-run idle chain is persisted in the isolated runtime's ``idle_tasks.db``.
Asserts the registry holds only the supported task types and that they complete.
"""

from __future__ import annotations

import json
import os
import sqlite3
import time
import uuid
from pathlib import Path

import httpx
import pytest

from tests.support.bash_compressor_e2e import (
    _backend_runtime_data_dir,
    resolve_working_base_selection,
)
from tests.support.verify_api_base import resolve_verify_api_base

SUPPORTED_IDLE_TASKS = frozenset({"cognitive_consolidation", "context_compaction", "cognitive_subsumption"})
IDLE_CHAIN_TIMEOUT_S = 300.0

FAILING_PROMPT = (
    "E2E_IDLE_FAILURE: use bash_code_execute_tool to run exactly `cat /nonexistent/e2e_idle_probe.txt`, "
    "then tell me in one sentence what error the shell reported."
)


def _create_agent(client: httpx.Client, backend_url: str) -> str:
    payload = {
        "name": f"Idle Failure Live {uuid.uuid4().hex[:6]}",
        "description": "Live idle chain E2E",
        "system_prompt": "You MUST use bash_code_execute_tool for shell commands and follow the user's steps exactly.",
        "skill_ids": [],
        "mcp_ids": [],
        "security_overrides": {"yoloModeEnabled": True},
    }
    resp = client.post(f"{backend_url}/api/v1/user-agents", json=payload, timeout=60.0)
    resp.raise_for_status()
    body = resp.json()
    agent_id = body.get("data", {}).get("id") or body.get("id")
    assert isinstance(agent_id, str) and agent_id
    return agent_id


def _run_turn(client: httpx.Client, backend_url: str, agent_id: str, chat_id: str) -> tuple[list[str], str]:
    """Stream one agent turn; returns (event types seen, assistant text)."""
    request_data: dict[str, object] = {
        "messageId": f"live-idle-{uuid.uuid4().hex[:10]}",
        "chatId": chat_id,
        "query": FAILING_PROMPT,
        "modelSelection": resolve_working_base_selection(backend_url=backend_url),
        "actionMode": "agent",
        "agentId": agent_id,
        "memoryRequireConfirmation": False,
        "enableMemoryAutoExtraction": False,
    }
    event_types: list[str] = []
    text_parts: list[str] = []
    with client.stream("POST", f"{backend_url}/api/v1/agents/agent-stream", json=request_data, timeout=600.0) as response:
        response.raise_for_status()
        for line in response.iter_lines():
            if not line.startswith("data: "):
                continue
            payload = line[6:]
            if payload == "[DONE]":
                continue  # keep reading: the server schedules idle tasks only after the stream is drained
            try:
                event = json.loads(payload)
            except json.JSONDecodeError:
                continue
            if not isinstance(event, dict):
                continue
            event_types.append(str(event.get("type")))
            if event.get("type") == "message" and isinstance(event.get("data"), str):
                text_parts.append(event["data"])
    return event_types, "".join(text_parts)


def _idle_rows(data_dir: Path, since: float) -> list[tuple[str, str]]:
    """(task_type, status) rows from every idle_tasks.db written by this run."""
    rows: list[tuple[str, str]] = []
    for db_path in data_dir.rglob("idle_tasks.db"):
        if db_path.stat().st_mtime < since:
            continue
        with sqlite3.connect(f"file:{db_path}?mode=ro", uri=True) as conn:
            rows.extend(conn.execute("SELECT task_type, status FROM idle_tasks").fetchall())
    return rows


@pytest.mark.e2e
@pytest.mark.timeout(900)
@pytest.mark.skipif(
    not os.environ.get("BASIC_API_KEY") or not os.environ.get("LITE_API_KEY"),
    reason="Requires BASIC_API_KEY and LITE_API_KEY",
)
def test_failed_tool_turn_schedules_only_supported_idle_tasks() -> None:
    backend_url = os.environ.get("BACKEND_URL", "").rstrip("/") or resolve_verify_api_base()
    data_dir = _backend_runtime_data_dir(backend_url)
    if data_dir is None:
        pytest.skip(f"{backend_url} is not an isolated runtime; refusing to read a shared backend's data dir")

    started = time.time()
    with httpx.Client() as client:
        agent_id = _create_agent(client, backend_url)
        event_types, reply = _run_turn(client, backend_url, agent_id, f"e2e-idle-{uuid.uuid4().hex[:10]}")

    assert reply.strip(), f"agent produced no reply; events={event_types[:20]}"
    assert any("tool" in event_type for event_type in event_types), f"no tool event in stream: {event_types[:20]}"

    rows: list[tuple[str, str]] = []
    deadline = time.time() + IDLE_CHAIN_TIMEOUT_S
    while time.time() < deadline:
        rows = _idle_rows(data_dir, since=started)
        if rows and all(status in ("completed", "failed") for _, status in rows):
            break
        time.sleep(5)

    assert rows, "no idle task was scheduled after the turn"
    task_types = {task_type for task_type, _ in rows}
    assert task_types <= SUPPORTED_IDLE_TASKS, f"unexpected idle task types: {sorted(task_types - SUPPORTED_IDLE_TASKS)}"
    assert "cognitive_consolidation" in task_types, rows
    assert all(status == "completed" for _, status in rows), rows
