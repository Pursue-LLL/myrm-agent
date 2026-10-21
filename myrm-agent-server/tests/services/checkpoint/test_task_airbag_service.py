"""Baseline idempotency of TaskAirbagService.arm_airbag.

An unattended task's stream starts many times (loop restarts, wait resumes); the airbag baseline must stay the
task's first start until the airbag is rolled back or dismissed.
"""

from __future__ import annotations

import subprocess
from pathlib import Path

import pytest
from myrm_agent_harness.api.security import TaskAirbagStatus

from app.services.checkpoint.task_airbag_service import TaskAirbagService

_INITIAL = "console.log('init');\n"


def _init_git_repo(path: Path) -> Path:
    """Create an initialized Git repository with one committed file."""
    path.mkdir(parents=True, exist_ok=True)
    for args in (
        ["git", "init"],
        ["git", "config", "user.email", "tester@myrm.ai"],
        ["git", "config", "user.name", "Tester"],
    ):
        subprocess.run(args, cwd=str(path), check=True, capture_output=True)
    (path / "index.js").write_text(_INITIAL, encoding="utf-8")
    subprocess.run(["git", "add", "index.js"], cwd=str(path), check=True, capture_output=True)
    subprocess.run(["git", "commit", "-m", "init"], cwd=str(path), check=True, capture_output=True)
    return path


@pytest.fixture
def workspace(tmp_path: Path) -> Path:
    return _init_git_repo(tmp_path / "workspace")


def _edit(workspace: Path, content: str) -> None:
    (workspace / "index.js").write_text(content, encoding="utf-8")


def _read(workspace: Path) -> str:
    return (workspace / "index.js").read_text(encoding="utf-8")


async def test_rearm_keeps_the_original_baseline(workspace: Path) -> None:
    service = TaskAirbagService()
    first = await service.arm_airbag("task-1", str(workspace))
    assert first is not None

    _edit(workspace, "console.log('after first run');\n")
    second = await service.arm_airbag("task-1", str(workspace))

    assert second == first
    assert await service.rollback_airbag("task-1") is True
    assert _read(workspace) == _INITIAL


@pytest.mark.parametrize("finish", ["rollback", "dismiss"])
async def test_rearm_after_the_airbag_is_finished_captures_a_fresh_baseline(workspace: Path, finish: str) -> None:
    service = TaskAirbagService()
    first = await service.arm_airbag("task-1", str(workspace))
    assert first is not None
    if finish == "rollback":
        assert await service.rollback_airbag("task-1") is True
    else:
        assert service.dismiss_airbag("task-1") is True

    next_run_start = "console.log('next run start');\n"
    _edit(workspace, next_run_start)
    second = await service.arm_airbag("task-1", str(workspace))

    assert second is not None
    assert second.status == TaskAirbagStatus.ARMED
    assert second.base_snapshot_id != first.base_snapshot_id
    _edit(workspace, "console.log('next run edit');\n")
    assert await service.rollback_airbag("task-1") is True
    assert _read(workspace) == next_run_start


async def test_rearm_after_service_restart_reuses_the_persisted_baseline(workspace: Path) -> None:
    first = await TaskAirbagService().arm_airbag("task-1", str(workspace))
    assert first is not None

    _edit(workspace, "console.log('after first run');\n")
    restarted = TaskAirbagService()
    second = await restarted.arm_airbag("task-1", str(workspace))

    assert second == first
    assert await restarted.rollback_airbag("task-1") is True
    assert _read(workspace) == _INITIAL


async def test_arm_in_another_workspace_captures_its_own_baseline(workspace: Path, tmp_path: Path) -> None:
    other = _init_git_repo(tmp_path / "other")
    service = TaskAirbagService()
    first = await service.arm_airbag("task-1", str(workspace))
    second = await service.arm_airbag("task-1", str(other))

    assert first is not None and second is not None
    assert second.workspace_path != first.workspace_path
    assert second.workspace_path == str(other.resolve())


async def test_session_effects_are_attributed_to_the_armed_task(workspace: Path) -> None:
    service = TaskAirbagService()
    await service.arm_airbag("task-1", str(workspace), session_id="chat-1")

    service.record_session_external_effects("chat-1", ["container_cloud", "publish"])
    service.record_session_external_effects("chat-1", ["publish", "database"])

    status = await service.get_airbag_status("task-1")
    assert status is not None
    assert list(status.external_effects) == ["container_cloud", "publish", "database"]


async def test_effects_of_unarmed_session_are_ignored(workspace: Path) -> None:
    service = TaskAirbagService()
    await service.arm_airbag("task-1", str(workspace), session_id="chat-1")

    service.record_session_external_effects("chat-other", ["database"])

    status = await service.get_airbag_status("task-1")
    assert status is not None
    assert list(status.external_effects) == []


async def test_effects_stop_being_recorded_once_the_airbag_is_closed(workspace: Path) -> None:
    service = TaskAirbagService()
    await service.arm_airbag("task-1", str(workspace), session_id="chat-1")
    assert service.dismiss_airbag("task-1") is True

    service.record_session_external_effects("chat-1", ["database"])

    assert service._active_manifests["task-1"].external_effects == ()
    assert "chat-1" not in service._task_by_session


async def test_rearm_for_a_new_task_in_the_same_session_takes_over_attribution(workspace: Path) -> None:
    service = TaskAirbagService()
    await service.arm_airbag("task-1", str(workspace), session_id="chat-1")
    await service.arm_airbag("task-2", str(workspace), session_id="chat-1")

    service.record_session_external_effects("chat-1", ["database"])

    assert service._active_manifests["task-2"].external_effects == ("database",)
    assert service._active_manifests["task-1"].external_effects == ()


async def test_rollback_notification_is_localized_without_internal_ids(workspace: Path) -> None:
    from unittest.mock import AsyncMock, MagicMock, patch

    service = TaskAirbagService()
    await service.arm_airbag("task-1", str(workspace), session_id="chat-1")
    _edit(workspace, "console.log('changed');\n")
    bus = MagicMock()

    with (
        patch("app.core.channel_bridge.locale_provider.resolve_user_locale", new=AsyncMock(return_value="zh-CN")),
        patch("app.services.event.app_event_bus.get_event_bus", return_value=bus),
    ):
        assert await service.rollback_airbag("task-1") is True

    data = bus.publish.call_args.args[0].data
    assert data["title"] == "改动已撤销"
    assert "task-1" not in data["message"]
    assert data["meta_data"]["kind"] == "airbag_rolled_back"
    assert "chat-1" not in service._task_by_session


async def test_dismissed_airbag_no_longer_reports_status(workspace: Path) -> None:
    service = TaskAirbagService()
    await service.arm_airbag("task-1", str(workspace))
    assert await service.get_airbag_status("task-1") is not None

    assert service.dismiss_airbag("task-1") is True

    assert await service.get_airbag_status("task-1") is None
    assert await TaskAirbagService().get_airbag_status("task-1", str(workspace)) is None
