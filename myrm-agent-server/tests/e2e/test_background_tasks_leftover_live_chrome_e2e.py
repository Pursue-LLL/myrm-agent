"""Chrome LIVE E2E: a user asks in the chat for a command that leaves a program running, and stops it from the panel.

Real business flow, no API shortcut for the turn:

    user types the request in the composer and presses send -> the live model starts the command in the background with the bash tool
    -> the command ends and the program it started keeps running -> the background tasks panel of the same page says so
    -> user presses the stop button -> the program is gone from the process table and the panel no longer says so

Formal run::

    MYRM_E2E_LANE=LIVE_AGENT ./myrm-dev test --detach -m chrome_e2e \\
      myrm-agent/myrm-agent-server/tests/e2e/test_background_tasks_leftover_live_chrome_e2e.py
"""

from __future__ import annotations

import time
import uuid
from pathlib import Path

import pytest

from tests.support.chrome_approval_turn import run_one_turn
from tests.support.chrome_background_panel import (
    open_background_tasks_panel,
    stop_leftover_from_panel,
    wait_api_row,
    wait_for_leftover_hint,
    wait_marker_gone,
    wait_until_leftover_gone,
)
from tests.support.chrome_mcp_e2e import ChromeMcpClient, McpPage, get_e2e_api_url, http_json
from tests.support.chrome_skill_hooks_live_e2e import DONE_TOKEN, SkillChat
from tests.support.e2e_runtime_guard import E2EResourceLedger
from tests.support.marked_command_lines import leave_one_child_command, processes_with_marker

_CHILD_LIFETIME_SECONDS = 120
_RUN_WAIT_SECONDS = 240.0
_POLL_SECONDS = 1.0


def _request(marker: str) -> str:
    """What a user would type: the command, started in the background, then a fixed reply."""
    command = leave_one_child_command(marker, lifetime_seconds=_CHILD_LIFETIME_SECONDS)
    return (
        "Run this command with the bash tool in the background (run_in_background=true), exactly once, "
        f"copied exactly: {command} Run nothing else. When it has been started, reply with exactly: {DONE_TOKEN}"
    )


def _wait_for_leftover_task(api_base: str, chat_id: str) -> str:
    """The id of the finished shell job of this chat whose program is still running."""
    deadline = time.monotonic() + _RUN_WAIT_SECONDS
    rows: list[object] = []
    while time.monotonic() < deadline:
        payload = http_json("GET", f"{api_base}/api/v1/background-tasks")
        assert isinstance(payload, dict)
        rows = [row for row in payload.get("tasks", []) if isinstance(row, dict) and row.get("chat_id") == chat_id]
        for row in rows:
            leftover = row.get("leftover_processes")
            if row.get("kind") == "shell" and row.get("status") == "completed" and isinstance(leftover, int) and leftover > 0:
                return str(row["task_id"])
        time.sleep(_POLL_SECONDS)
    raise AssertionError(
        f"no finished shell job of chat {chat_id} left a program running within {_RUN_WAIT_SECONDS}s; rows={rows!r}"
    )


@pytest.mark.chrome_e2e(
    execution_mode="PRIVATE",
    access_scope="NAMESPACE_WRITE",
    workload="LIVE",
    private_reason="live_shpoib",
)
@pytest.mark.e2e_search_policy("empty")
@pytest.mark.integration
@pytest.mark.timeout(600)
def test_a_program_the_agent_left_running_is_stopped_from_the_panel(
    tmp_path: Path, e2e_resource_ledger: E2EResourceLedger
) -> None:
    api_base = get_e2e_api_url()
    marker = f"leftover-{uuid.uuid4().hex[:8]}"
    started: list[str] = []

    def stop_from_the_panel(client: ChromeMcpClient, page: McpPage, probe: SkillChat, chat_url: str) -> None:
        task_id = _wait_for_leftover_task(api_base, probe.chat_id)
        started.append(task_id)
        assert len(processes_with_marker(marker)) == 1, "the job reports a program left running, the process table has none"

        open_background_tasks_panel(client, page)
        wait_for_leftover_hint(client, page)
        stop_leftover_from_panel(client, page)

        wait_marker_gone(marker)
        wait_api_row(api_base, task_id, leftover=0)
        wait_until_leftover_gone(client, page)

    try:
        run_one_turn(tmp_path, e2e_resource_ledger, "bgleft", _request(marker), stop_from_the_panel, asks_approval=False)
    finally:
        for task_id in started:
            http_json(
                "POST",
                f"{api_base}/api/v1/background-tasks/{task_id}/cancel",
                expected_statuses=frozenset({200, 201, 400}),
            )
