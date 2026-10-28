"""The roots a cron run may work in are judged again at run time, whatever the gate let in when they were stored."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace
from unittest.mock import AsyncMock, patch

import pytest
from myrm_agent_harness.toolkits.cron.types import CronJob, JobType, Schedule, ScheduleKind

from app.core.cron.adapters.agent_runner import _resolve_effective_allowed_roots
from app.services.workspace.workspace_path_policy import WorkspacePathIssue, WorkspacePathValidationError

HOME = str(Path.home())
_GET_PROJECT_TARGET = "app.services.project.project_service.ProjectService.get_project"


def _job(**overrides: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "job-1",
        "user_id": "default",
        "name": "digest",
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000),
        "prompt": "summarize",
    }
    defaults.update(overrides)
    return CronJob(**defaults)  # type: ignore[arg-type]


async def test_ordinary_roots_are_used_as_stored(tmp_path: Path) -> None:
    job = _job(allowed_roots=("~/Documents", str(tmp_path)))

    assert await _resolve_effective_allowed_roots(job) == ["~/Documents", str(tmp_path)]


@pytest.mark.parametrize("stored", [HOME, "/", "~"])
async def test_a_stored_root_containing_protected_locations_fails_the_run(stored: str) -> None:
    with pytest.raises(WorkspacePathValidationError) as refusal:
        await _resolve_effective_allowed_roots(_job(allowed_roots=("/tmp", stored)))

    assert refusal.value.issue is WorkspacePathIssue.TOO_BROAD
    assert "job-1" in str(refusal.value)
    assert repr(stored) in str(refusal.value)


async def test_a_project_workspace_stands_in_for_missing_roots(tmp_path: Path) -> None:
    project = SimpleNamespace(workspace_path=str(tmp_path))

    with patch(_GET_PROJECT_TARGET, AsyncMock(return_value=project)):
        assert await _resolve_effective_allowed_roots(_job(project_id="p1")) == [str(tmp_path)]


async def test_a_project_workspace_that_became_too_broad_fails_the_run() -> None:
    project = SimpleNamespace(workspace_path=HOME)

    with (
        patch(_GET_PROJECT_TARGET, AsyncMock(return_value=project)),
        pytest.raises(WorkspacePathValidationError),
    ):
        await _resolve_effective_allowed_roots(_job(project_id="p1"))


async def test_a_job_without_roots_or_project_has_none() -> None:
    assert await _resolve_effective_allowed_roots(_job()) == []
