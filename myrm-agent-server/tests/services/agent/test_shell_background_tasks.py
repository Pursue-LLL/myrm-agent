"""Tests for shell background task server facade."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.services.agent.shell_background_tasks import (
    cancel_shell_background_task,
    list_shell_background_tasks,
)
from myrm_agent_harness.agent.meta_tools.bash._background_types import BackgroundProcessInfo


def test_list_shell_background_tasks_maps_registry_rows() -> None:
    info = BackgroundProcessInfo(
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
    assert rows[0].task_id == "shell:99"
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
