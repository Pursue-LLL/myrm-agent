"""Unit tests for EntitlementGuardedCronManager."""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from app.core.cron.adapters.entitlement_guarded_manager import EntitlementGuardedCronManager
from app.platform_utils.sandbox.entitlements.entitlement_guard import EntitlementGuardError

_SLOT_FN = "app.platform_utils.sandbox.entitlements.entitlement_guard.require_cron_slot"


@pytest.mark.asyncio
async def test_create_job_enforces_slot_before_inner() -> None:
    inner = MagicMock()
    inner.count_jobs = AsyncMock(return_value=2)
    inner.create_job = AsyncMock(return_value=MagicMock(id="job-1"))
    mgr = EntitlementGuardedCronManager(inner)

    with patch(_SLOT_FN) as mock_slot:
        await mgr.create_job("user-1", name="t", job_type=MagicMock(), schedule=MagicMock())

    inner.count_jobs.assert_awaited_once_with("user-1")
    mock_slot.assert_called_once_with(2)
    inner.create_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_job_maps_entitlement_error_to_value_error() -> None:
    inner = MagicMock()
    inner.count_jobs = AsyncMock(return_value=0)
    mgr = EntitlementGuardedCronManager(inner)

    with patch(_SLOT_FN, side_effect=EntitlementGuardError("upgrade required")):
        with pytest.raises(ValueError, match="upgrade required") as exc_info:
            await mgr.create_job("user-1", name="t", job_type=MagicMock(), schedule=MagicMock())

    assert isinstance(exc_info.value.__cause__, EntitlementGuardError)
    inner.create_job.assert_not_called()


@pytest.mark.asyncio
async def test_create_job_passes_workflow_template_to_inner() -> None:
    inner = MagicMock()
    inner.count_jobs = AsyncMock(return_value=0)
    inner.create_job = AsyncMock(return_value=MagicMock(id="job-1"))
    mgr = EntitlementGuardedCronManager(inner)

    with patch(_SLOT_FN):
        await mgr.create_job(
            "user-1",
            name="t",
            job_type=MagicMock(),
            schedule=MagicMock(),
            workflow_template_id="wt-1",
            workflow_template_args={"branch": "main"},
        )

    call_kwargs = inner.create_job.await_args.kwargs
    assert call_kwargs["workflow_template_id"] == "wt-1"
    assert call_kwargs["workflow_template_args"] == {"branch": "main"}


@pytest.mark.asyncio
async def test_duplicate_job_delegates_after_slot_check() -> None:
    inner = MagicMock()
    inner.count_jobs = AsyncMock(return_value=1)
    inner.duplicate_job = AsyncMock(return_value=MagicMock(id="dup-1"))
    mgr = EntitlementGuardedCronManager(inner)

    with patch(_SLOT_FN):
        result = await mgr.duplicate_job("src-id", "user-1")

    assert result is not None
    inner.duplicate_job.assert_awaited_once_with("src-id", "user-1")


@pytest.mark.asyncio
async def test_duplicate_job_maps_entitlement_error_to_value_error() -> None:
    inner = MagicMock()
    inner.count_jobs = AsyncMock(return_value=0)
    mgr = EntitlementGuardedCronManager(inner)

    with patch(_SLOT_FN, side_effect=EntitlementGuardError("duplicate blocked")):
        with pytest.raises(ValueError, match="duplicate blocked"):
            await mgr.duplicate_job("src-id", "user-1")

    inner.duplicate_job.assert_not_called()


def test_getattr_delegates_to_inner() -> None:
    inner = MagicMock()
    inner.get_job = MagicMock(return_value="job-a")
    mgr = EntitlementGuardedCronManager(inner)

    assert mgr.get_job is inner.get_job


@pytest.mark.asyncio
async def test_update_job_clear_pre_condition_script_merges_for_lifecycle_guard() -> None:
    from myrm_agent_harness.toolkits.cron.types import CronJob, CronJobPatch, JobType, Schedule, ScheduleKind

    inner = MagicMock()
    existing = CronJob(
        id="job-1",
        user_id="user-1",
        name="Probe",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *"),
        prompt="Check inbox",
        pre_condition_script='print("ok")',
    )
    inner.get_job = AsyncMock(return_value=existing)
    inner.update_job = AsyncMock(return_value=existing)
    mgr = EntitlementGuardedCronManager(inner)

    await mgr.update_job(
        "job-1",
        "user-1",
        CronJobPatch(clear_pre_condition_script=True),
    )

    inner.update_job.assert_awaited_once()


@pytest.mark.asyncio
async def test_lookup_and_lifecycle_calls_delegate_with_their_arguments() -> None:
    inner = MagicMock()
    inner.list_jobs = AsyncMock(return_value=["job"])
    inner.pause_job = AsyncMock(return_value="paused")
    inner.resume_job = AsyncMock(return_value="resumed")
    inner.delete_job = AsyncMock(return_value=True)
    inner.trigger_now = AsyncMock(return_value=True)
    mgr = EntitlementGuardedCronManager(inner)

    assert await mgr.list_jobs("user-1", name_filter="x", limit=5, offset=2) == ["job"]
    assert await mgr.pause_job("j1", "user-1") == "paused"
    assert await mgr.resume_job("j1", "user-1") == "resumed"
    assert await mgr.delete_job("j1", "user-1") is True
    assert await mgr.trigger_now("j1", "user-1") is True

    inner.list_jobs.assert_awaited_once_with("user-1", name_filter="x", chat_id=None, project_id=None, limit=5, offset=2)
    inner.pause_job.assert_awaited_once_with("j1", "user-1")
    inner.resume_job.assert_awaited_once_with("j1", "user-1")
    inner.delete_job.assert_awaited_once_with("j1", "user-1")
    inner.trigger_now.assert_awaited_once_with("j1", "user-1")
    inner.count_jobs.assert_not_called()


@pytest.mark.asyncio
async def test_create_job_forwards_every_harness_field() -> None:
    """The wrapper must accept whatever ``CronManager.create_job`` accepts, or REST/agent callers fail with TypeError."""
    import inspect

    from myrm_agent_harness.toolkits.cron.manager import CronManager

    wrapper_params = set(inspect.signature(EntitlementGuardedCronManager.create_job).parameters)
    harness_params = set(inspect.signature(CronManager.create_job).parameters)

    assert harness_params <= wrapper_params, sorted(harness_params - wrapper_params)

    inner = MagicMock()
    inner.count_jobs = AsyncMock(return_value=0)
    inner.create_job = AsyncMock(return_value=MagicMock(id="job-1"))
    mgr = EntitlementGuardedCronManager(inner)
    with patch(_SLOT_FN):
        await mgr.create_job("user-1", name="t", job_type=MagicMock(), schedule=MagicMock(), project_id="p1", skill_ids=("s1",))
    kwargs = inner.create_job.await_args.kwargs
    assert kwargs["project_id"] == "p1" and kwargs["skill_ids"] == ("s1",)
