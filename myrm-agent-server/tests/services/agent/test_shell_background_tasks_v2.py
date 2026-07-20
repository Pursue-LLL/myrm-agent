"""Unit tests for shell background task DTO facade."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from myrm_agent_harness.agent.meta_tools.bash._background_types import BackgroundProcessInfo

from app.services.agent.shell_background_tasks import (
    _redact_preview,
    cancel_shell_background_task,
    list_shell_background_tasks,
    shell_registry_is_ephemeral,
)


def test_shell_dto_includes_exit_code_and_error_category() -> None:
    info = BackgroundProcessInfo(
        job_id="job-42",
        pid=42,
        command="npm test",
        session_id="chat-1",
        started_at=1.0,
        status="exited",
        exit_code=1,
        error_category="nonzero_exit",
        last_stdout_tail=["failed test"],
    )

    class _FakeRegistry:
        def list_processes(self) -> list[BackgroundProcessInfo]:
            return [info]

    with patch(
        "myrm_agent_harness.api.hooks.get_background_registry",
        return_value=_FakeRegistry(),
    ):
        rows = list_shell_background_tasks()

    assert len(rows) == 1
    row = rows[0]
    assert row.exit_code == 1
    assert row.error_category == "nonzero_exit"
    assert row.result_preview is not None
    assert "failed test" in row.result_preview


def test_shell_registry_is_ephemeral() -> None:
    assert shell_registry_is_ephemeral() is True


def test_redact_preview_strips_secrets() -> None:
    secret = "Authorization: Bearer sk-live-abcdefghijklmnopqrstuvwxyz"
    redacted = _redact_preview(secret)
    assert redacted is not None
    assert "sk-live-abcdefghijklmnopqrstuvwxyz" not in redacted


def test_redact_preview_none_returns_none() -> None:
    assert _redact_preview(None) is None
    assert _redact_preview("") is None


def test_list_shell_maps_killed_status_and_stderr_preview() -> None:
    info = BackgroundProcessInfo(
        job_id="job-88",
        pid=88,
        command="npm run dev",
        session_id="chat-killed",
        started_at=1.0,
        status="killed",
        last_stderr_tail=["terminated"],
    )
    fake_registry = MagicMock()
    fake_registry.list_processes.return_value = [info]

    with patch(
        "myrm_agent_harness.api.hooks.get_background_registry",
        return_value=fake_registry,
    ):
        rows = list_shell_background_tasks()

    assert rows[0].status == "cancelled"
    assert rows[0].result_preview == "terminated"


def test_list_shell_running_includes_stdout_preview() -> None:
    info = BackgroundProcessInfo(
        job_id="job-run",
        pid=99,
        command="npm run build",
        session_id="chat-run",
        started_at=1.0,
        status="running",
        last_stdout_tail=["Compiling page 3/12"],
    )
    fake_registry = MagicMock()
    fake_registry.list_processes.return_value = [info]

    with patch(
        "myrm_agent_harness.api.hooks.get_background_registry",
        return_value=fake_registry,
    ):
        rows = list_shell_background_tasks()

    assert rows[0].status == "running"
    assert rows[0].result_preview == "Compiling page 3/12"


@pytest.mark.asyncio
async def test_cancel_shell_background_task_returns_false_when_unknown() -> None:
    fake_registry = MagicMock()
    fake_registry.kill = AsyncMock(return_value=False)

    with patch(
        "myrm_agent_harness.api.hooks.get_background_registry",
        return_value=fake_registry,
    ):
        ok = await cancel_shell_background_task(404)

    assert ok is False
