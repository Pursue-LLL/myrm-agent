"""Tests for shell background task server facade."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.shell_background_tasks import (
    _command_preview,
    _map_shell_status,
    _progress_from_info,
    cancel_shell_background_task,
    list_shell_background_tasks,
)
from myrm_agent_harness.agent.meta_tools.bash._background_types import BackgroundProcessInfo


def test_list_shell_background_tasks_maps_registry_rows() -> None:
    info = BackgroundProcessInfo(
        job_id="job-99",
        pid=99,
        command="npm install",
        session_id="chat-abc",
        started_at=1_700_000_000.0,
        status="running",
        last_progress={"progress": 42},
    )
    fake_registry = MagicMock()
    fake_registry.list_processes.return_value = [info]

    with patch(
        "myrm_agent_harness.api.hooks.get_background_registry",
        return_value=fake_registry,
    ):
        rows = list_shell_background_tasks()

    assert len(rows) == 1
    assert rows[0].task_id == "shell:job-99"
    assert rows[0].chat_id == "chat-abc"
    assert rows[0].status == "running"
    assert rows[0].progress_percent == 42


@pytest.mark.asyncio
async def test_cancel_shell_background_task_delegates_to_registry() -> None:
    fake_registry = MagicMock()
    fake_registry.kill = AsyncMock(return_value=True)

    with patch(
        "myrm_agent_harness.api.hooks.get_background_registry",
        return_value=fake_registry,
    ):
        ok = await cancel_shell_background_task(77)

    assert ok is True
    fake_registry.kill.assert_awaited_once_with(77, force=False)


def test_map_shell_status_covers_terminal_states() -> None:
    assert _map_shell_status("running", None) == "running"
    assert _map_shell_status("killed", None) == "cancelled"
    assert _map_shell_status("exited", 0) == "completed"
    assert _map_shell_status("exited", 1) == "failed"
    assert _map_shell_status("unknown", None) == "failed"


def test_command_preview_truncates_long_commands() -> None:
    short = _command_preview("npm install")
    assert short == "npm install"
    long_cmd = "x" * 200
    preview = _command_preview(long_cmd)
    assert preview.endswith("...")
    assert len(preview) == 120


def test_progress_from_info_handles_missing_or_invalid() -> None:
    assert _progress_from_info(None) is None
    assert _progress_from_info({"progress": "n/a"}) is None
    assert _progress_from_info({"progress": 75.5}) == 75


def test_list_shell_background_tasks_maps_completed_and_preview() -> None:
    info = BackgroundProcessInfo(
        job_id="job-101",
        pid=101,
        command="npm run build",
        session_id="chat-done",
        started_at=1_700_000_000.0,
        status="exited",
        exit_code=0,
        last_stdout_tail=["build succeeded"],
        last_progress={"progress": 100, "updated_at": 1_700_000_120.0},
    )
    fake_registry = MagicMock()
    fake_registry.list_processes.return_value = [info]

    with patch(
        "myrm_agent_harness.api.hooks.get_background_registry",
        return_value=fake_registry,
    ):
        rows = list_shell_background_tasks()

    assert rows[0].status == "completed"
    assert rows[0].completed_at == 1_700_000_120.0
    assert rows[0].result_preview == "build succeeded"
