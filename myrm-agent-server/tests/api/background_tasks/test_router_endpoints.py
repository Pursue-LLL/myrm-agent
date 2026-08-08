"""Tests for background_tasks/router.py API endpoints.

Covers: list_background_tasks, get_background_task, cancel_background_task,
steer_background_task, shell_background_stdin.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from fastapi import HTTPException
from myrm_agent_harness.toolkits.kanban.types import TaskStatus


@dataclass
class _FakeTask:
    task_id: str
    board_id: str = "sys-bg"
    title: str = "task"
    description: str = "do something"
    status: str = TaskStatus.RUNNING
    error: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    created_at: datetime = field(default_factory=lambda: datetime.now(UTC))
    completed_at: datetime | None = None


@dataclass
class _FakeShellTask:
    task_id: str
    prompt: str = "ls -la"
    status: str = "running"
    created_at: float = 1700000000.0
    completed_at: float | None = None
    result_preview: str | None = None
    chat_id: str | None = None
    pid: int | None = 12345
    progress_percent: int | None = None
    exit_code: int | None = None
    error_category: str | None = None
    job_id: str | None = None
    vault_log_ref: str | None = None
    waiting_for_input: bool = False
    stdin_closed: bool = False


# ---------------------------------------------------------------------------
# list_background_tasks
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_list_merges_agent_and_shell() -> None:
    with (
        patch(
            "app.api.background_tasks.router._list_agent_tasks",
            new_callable=AsyncMock,
        ) as mock_list_agent,
        patch(
            "app.api.background_tasks.router.list_shell_background_tasks"
        ) as mock_list_shell,
        patch(
            "app.api.background_tasks.router.shell_registry_is_ephemeral",
            return_value=True,
        ),
    ):
        from app.api.background_tasks.router import BackgroundTaskResponse

        agent_resp = BackgroundTaskResponse(
            kind="agent", task_id="a1", prompt="research", status="running", created_at=1700000002.0
        )
        mock_list_agent.return_value = [agent_resp]
        mock_list_shell.return_value = [
            _FakeShellTask(task_id="s1", created_at=1700000001.0),
        ]

        from app.api.background_tasks.router import list_background_tasks

        resp = await list_background_tasks()
        assert len(resp.tasks) == 2
        assert resp.tasks[0].task_id == "a1"
        assert resp.tasks[1].task_id == "s1"
        assert resp.registry_ephemeral is True


# ---------------------------------------------------------------------------
# get_background_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_agent_task() -> None:
    fake = _FakeTask(task_id="t1", description="research papers")
    with (
        patch("app.api.background_tasks.router.get_background_task_handler") as mock_handler,
        patch("app.services.kanban.KanbanService.get_instance") as mock_svc,
    ):
        mock_handler.return_value = MagicMock()
        store = MagicMock()
        store.get_task = AsyncMock(return_value=fake)
        svc = MagicMock()
        svc.store = store
        mock_svc.return_value = svc

        from app.api.background_tasks.router import get_background_task

        result = await get_background_task("t1")
        assert result.task_id == "t1"
        assert result.kind == "agent"
        assert result.prompt == "research papers"


@pytest.mark.asyncio
async def test_get_shell_task() -> None:
    fake_shell = _FakeShellTask(task_id="shell:j1", prompt="npm build")
    with patch(
        "app.api.background_tasks.router.find_shell_background_task",
        return_value=fake_shell,
    ):
        from app.api.background_tasks.router import get_background_task

        result = await get_background_task("shell:j1")
        assert result.kind == "shell"
        assert result.prompt == "npm build"


@pytest.mark.asyncio
async def test_get_shell_task_invalid_id() -> None:
    from app.api.background_tasks.router import get_background_task

    with pytest.raises(HTTPException) as exc_info:
        await get_background_task("shell:")
    assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_shell_task_not_found() -> None:
    with patch(
        "app.api.background_tasks.router.find_shell_background_task",
        return_value=None,
    ):
        from app.api.background_tasks.router import get_background_task

        with pytest.raises(HTTPException) as exc_info:
            await get_background_task("shell:missing")
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_agent_task_no_handler() -> None:
    with patch(
        "app.api.background_tasks.router.get_background_task_handler",
        return_value=None,
    ):
        from app.api.background_tasks.router import get_background_task

        with pytest.raises(HTTPException) as exc_info:
            await get_background_task("task-uuid")
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_get_agent_task_not_found() -> None:
    with (
        patch("app.api.background_tasks.router.get_background_task_handler") as mock_handler,
        patch("app.services.kanban.KanbanService.get_instance") as mock_svc,
    ):
        mock_handler.return_value = MagicMock()
        store = MagicMock()
        store.get_task = AsyncMock(return_value=None)
        svc = MagicMock()
        svc.store = store
        mock_svc.return_value = svc

        from app.api.background_tasks.router import get_background_task

        with pytest.raises(HTTPException) as exc_info:
            await get_background_task("nonexistent")
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# cancel_background_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_cancel_agent_task() -> None:
    with patch("app.api.background_tasks.router.get_background_task_handler") as mock_get:
        handler = MagicMock()
        handler.cancel_background = AsyncMock(return_value=True)
        mock_get.return_value = handler

        from app.api.background_tasks.router import cancel_background_task

        result = await cancel_background_task("task-1")
        assert result["message"] == "Background task cancelled"


@pytest.mark.asyncio
async def test_cancel_agent_task_failed() -> None:
    with patch("app.api.background_tasks.router.get_background_task_handler") as mock_get:
        handler = MagicMock()
        handler.cancel_background = AsyncMock(return_value=False)
        mock_get.return_value = handler

        from app.api.background_tasks.router import cancel_background_task

        with pytest.raises(HTTPException) as exc_info:
            await cancel_background_task("task-1")
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_cancel_shell_task() -> None:
    fake = _FakeShellTask(task_id="shell:j1", pid=9999)
    with (
        patch("app.api.background_tasks.router.find_shell_background_task", return_value=fake),
        patch("app.api.background_tasks.router.cancel_shell_background_task", new_callable=AsyncMock, return_value=True),
    ):
        from app.api.background_tasks.router import cancel_background_task

        result = await cancel_background_task("shell:j1")
        assert "Shell" in result["message"]


@pytest.mark.asyncio
async def test_cancel_shell_invalid_id() -> None:
    from app.api.background_tasks.router import cancel_background_task

    with pytest.raises(HTTPException) as exc_info:
        await cancel_background_task("shell:")
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_cancel_no_handler() -> None:
    with patch("app.api.background_tasks.router.get_background_task_handler", return_value=None):
        from app.api.background_tasks.router import cancel_background_task

        with pytest.raises(HTTPException) as exc_info:
            await cancel_background_task("task-1")
        assert exc_info.value.status_code == 404


# ---------------------------------------------------------------------------
# steer_background_task
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_steer_agent_task() -> None:
    with patch("app.api.background_tasks.router.get_background_task_handler") as mock_get:
        handler = MagicMock()
        handler.steer_background = AsyncMock(return_value=True)
        mock_get.return_value = handler

        from app.api.background_tasks.router import SteerRequest, steer_background_task

        result = await steer_background_task("task-1", SteerRequest(instruction="focus on perf"))
        assert result["message"] == "Steering instruction sent"


@pytest.mark.asyncio
async def test_steer_shell_rejected() -> None:
    from app.api.background_tasks.router import SteerRequest, steer_background_task

    with pytest.raises(HTTPException) as exc_info:
        await steer_background_task("shell:j1", SteerRequest(instruction="whatever"))
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_steer_no_handler() -> None:
    with patch("app.api.background_tasks.router.get_background_task_handler", return_value=None):
        from app.api.background_tasks.router import SteerRequest, steer_background_task

        with pytest.raises(HTTPException) as exc_info:
            await steer_background_task("task-1", SteerRequest(instruction="test"))
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_steer_failed() -> None:
    with patch("app.api.background_tasks.router.get_background_task_handler") as mock_get:
        handler = MagicMock()
        handler.steer_background = AsyncMock(return_value=False)
        mock_get.return_value = handler

        from app.api.background_tasks.router import SteerRequest, steer_background_task

        with pytest.raises(HTTPException) as exc_info:
            await steer_background_task("task-1", SteerRequest(instruction="test"))
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# shell_background_stdin
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_stdin_not_shell() -> None:
    from app.api.background_tasks.router import ShellStdinRequest, shell_background_stdin

    with pytest.raises(HTTPException) as exc_info:
        await shell_background_stdin("agent-task", ShellStdinRequest(data="hello"))
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_stdin_invalid_id() -> None:
    from app.api.background_tasks.router import ShellStdinRequest, shell_background_stdin

    with pytest.raises(HTTPException) as exc_info:
        await shell_background_stdin("shell:", ShellStdinRequest(data="hello"))
    assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_stdin_not_found() -> None:
    with patch("app.api.background_tasks.router.find_shell_background_task", return_value=None):
        from app.api.background_tasks.router import ShellStdinRequest, shell_background_stdin

        with pytest.raises(HTTPException) as exc_info:
            await shell_background_stdin("shell:j1", ShellStdinRequest(data="hello"))
        assert exc_info.value.status_code == 404


@pytest.mark.asyncio
async def test_stdin_not_running() -> None:
    fake = _FakeShellTask(task_id="j1", status="completed", pid=123)
    with patch("app.api.background_tasks.router.find_shell_background_task", return_value=fake):
        from app.api.background_tasks.router import ShellStdinRequest, shell_background_stdin

        with pytest.raises(HTTPException) as exc_info:
            await shell_background_stdin("shell:j1", ShellStdinRequest(data="hello"))
        assert exc_info.value.status_code == 400


@pytest.mark.asyncio
async def test_stdin_success() -> None:
    fake = _FakeShellTask(task_id="j1", status="running", pid=123)
    with (
        patch("app.api.background_tasks.router.find_shell_background_task", return_value=fake),
        patch(
            "app.api.background_tasks.router.write_shell_background_stdin",
            new_callable=AsyncMock,
            return_value={"ok": True},
        ),
    ):
        from app.api.background_tasks.router import ShellStdinRequest, shell_background_stdin

        result = await shell_background_stdin("shell:j1", ShellStdinRequest(data="y\n", submit=True))
        assert result["message"] == "Shell stdin written"


@pytest.mark.asyncio
async def test_stdin_write_failed() -> None:
    fake = _FakeShellTask(task_id="j1", status="running", pid=123)
    with (
        patch("app.api.background_tasks.router.find_shell_background_task", return_value=fake),
        patch(
            "app.api.background_tasks.router.write_shell_background_stdin",
            new_callable=AsyncMock,
            return_value={"ok": False, "error": "pipe broken"},
        ),
    ):
        from app.api.background_tasks.router import ShellStdinRequest, shell_background_stdin

        with pytest.raises(HTTPException) as exc_info:
            await shell_background_stdin("shell:j1", ShellStdinRequest(data="y"))
        assert exc_info.value.status_code == 400


# ---------------------------------------------------------------------------
# _shell_row_to_response
# ---------------------------------------------------------------------------


def test_shell_row_to_response() -> None:
    from app.api.background_tasks.router import _shell_row_to_response

    row = _FakeShellTask(
        task_id="j1",
        prompt="npm test",
        status="running",
        pid=5678,
        chat_id="chat-1",
    )
    resp = _shell_row_to_response(row)
    assert resp.kind == "shell"
    assert resp.task_id == "j1"
    assert resp.pid == 5678
    assert resp.chat_id == "chat-1"
