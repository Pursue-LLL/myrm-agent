"""Required-content rule shared by CronManager.create_job and CronManager.update_job."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock

import pytest

from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronJobPatch,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
)

_SCRIPT = "echo '{\"ok\": true}'"


def _schedule() -> Schedule:
    return Schedule(kind=ScheduleKind.CRON, expr="0 * * * *")


def _job(**kwargs: object) -> CronJob:
    defaults: dict[str, object] = {
        "id": "job-1",
        "user_id": "user-1",
        "name": "Rule job",
        "job_type": JobType.AGENT,
        "schedule": _schedule(),
        "status": JobStatus.ACTIVE,
        "prompt": "do the thing",
    }
    defaults.update(kwargs)
    return CronJob(**defaults)  # type: ignore[arg-type]


def _manager(stored: CronJob | None = None) -> tuple[CronManager, AsyncMock]:
    store = AsyncMock()
    store.save_job = AsyncMock(side_effect=lambda j: j)
    store.get_job = AsyncMock(return_value=stored)
    store.get_monitor_state = AsyncMock(return_value=None)
    store.delete_monitor_state = AsyncMock()
    store.list_jobs = AsyncMock(return_value=[])
    store.count_jobs = AsyncMock(return_value=0)
    scheduler = MagicMock()
    scheduler.notify_change = MagicMock()
    return CronManager(store=store, scheduler=scheduler, shell_enabled=True), store


class TestCreateContentRule:
    async def test_router_with_script_may_omit_prompt(self) -> None:
        job = await _manager()[0].create_job(
            "user-1", "Script", JobType.ROUTER, _schedule(), pre_condition_script=_SCRIPT
        )
        assert job.prompt is None
        assert job.pre_condition_script == _SCRIPT

    async def test_router_needs_prompt_or_script(self) -> None:
        with pytest.raises(ValueError, match="ROUTER job requires a non-empty 'prompt' or 'pre_condition_script'"):
            await _manager()[0].create_job("user-1", "Empty", JobType.ROUTER, _schedule())

    async def test_router_with_prompt_only_is_accepted(self) -> None:
        job = await _manager()[0].create_job("user-1", "Prompt", JobType.ROUTER, _schedule(), prompt="relay")
        assert job.prompt == "relay"

    async def test_script_does_not_replace_agent_prompt(self) -> None:
        with pytest.raises(ValueError, match="AGENT job requires a non-empty 'prompt'"):
            await _manager()[0].create_job("user-1", "Agent", JobType.AGENT, _schedule(), pre_condition_script=_SCRIPT)

    async def test_script_does_not_replace_shell_command(self) -> None:
        with pytest.raises(ValueError, match="SHELL job requires a non-empty 'command'"):
            await _manager()[0].create_job("user-1", "Shell", JobType.SHELL, _schedule(), pre_condition_script=_SCRIPT)


class TestUpdateContentRule:
    async def _update(self, stored: CronJob, patch: CronJobPatch) -> CronJob:
        result = await _manager(stored)[0].update_job(stored.id, stored.user_id, patch)
        assert result is not None
        return result

    async def test_agent_prompt_cannot_be_emptied(self) -> None:
        stored = _job()
        mgr, store = _manager(stored)
        with pytest.raises(ValueError, match="AGENT job requires a non-empty 'prompt'"):
            await mgr.update_job(stored.id, stored.user_id, CronJobPatch(prompt=""))
        assert stored.prompt == "do the thing"
        store.save_job.assert_not_awaited()

    async def test_shell_command_cannot_be_emptied(self) -> None:
        stored = _job(job_type=JobType.SHELL, prompt=None, command="echo hi")
        mgr, store = _manager(stored)
        with pytest.raises(ValueError, match="SHELL job requires a non-empty 'command'"):
            await mgr.update_job(stored.id, stored.user_id, CronJobPatch(command=""))
        assert stored.command == "echo hi"
        store.save_job.assert_not_awaited()

    async def test_script_job_cannot_clear_its_only_content(self) -> None:
        stored = _job(job_type=JobType.ROUTER, prompt=None, pre_condition_script=_SCRIPT)
        mgr, store = _manager(stored)
        with pytest.raises(ValueError, match="ROUTER job requires a non-empty 'prompt' or 'pre_condition_script'"):
            await mgr.update_job(stored.id, stored.user_id, CronJobPatch(clear_pre_condition_script=True))
        assert stored.pre_condition_script == _SCRIPT
        store.save_job.assert_not_awaited()

    async def test_clear_flag_wins_over_a_new_script_value(self) -> None:
        stored = _job(job_type=JobType.ROUTER, prompt=None, pre_condition_script=_SCRIPT)
        patch = CronJobPatch(pre_condition_script="echo other", clear_pre_condition_script=True)
        with pytest.raises(ValueError, match="ROUTER job requires"):
            await _manager(stored)[0].update_job(stored.id, stored.user_id, patch)

    async def test_script_job_may_clear_the_prompt_it_does_not_use(self) -> None:
        stored = _job(job_type=JobType.ROUTER, prompt="relay", pre_condition_script=_SCRIPT)
        result = await self._update(stored, CronJobPatch(prompt=""))
        assert result.pre_condition_script == _SCRIPT

    async def test_router_with_prompt_may_clear_its_script(self) -> None:
        stored = _job(job_type=JobType.ROUTER, prompt="relay", pre_condition_script=_SCRIPT)
        result = await self._update(stored, CronJobPatch(clear_pre_condition_script=True))
        assert result.pre_condition_script is None
        assert result.prompt == "relay"

    async def test_valid_content_change_is_applied(self) -> None:
        result = await self._update(_job(), CronJobPatch(prompt="new prompt"))
        assert result.prompt == "new prompt"

    async def test_unrelated_edit_does_not_recheck_stored_content(self) -> None:
        stored = _job(prompt=None)
        result = await self._update(stored, CronJobPatch(name="Renamed"))
        assert result.name == "Renamed"
