"""Unit tests for CronManager job creation: new-job fields, create-time validation and `context_from` handling."""

from __future__ import annotations

from datetime import UTC, datetime
from unittest.mock import AsyncMock

import pytest

from myrm_agent_harness.toolkits.cron.serialization import failure_alert_to_dict
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronJobPatch,
    FailureAlertConfig,
    JobType,
    Schedule,
    ScheduleKind,
    SessionTarget,
)
from tests.support.cron_manager_mocks import make_job, make_manager, make_schedule

# ---------------------------------------------------------------------------
# create_job — new fields
# ---------------------------------------------------------------------------


class TestCreateJobNewFields:
    @pytest.mark.asyncio
    async def test_defaults(self):
        mgr = make_manager()
        job = await mgr.create_job("Test", JobType.AGENT, make_schedule(), prompt="hello")
        assert job.cooldown_seconds == 0
        assert job.max_fires is None
        assert job.expires_at is None
        assert job.session_target == SessionTarget.ISOLATED
        assert job.run_retention_days == 30
        assert job.failure_alert is None

    @pytest.mark.asyncio
    async def test_custom_values(self):
        dt = datetime(2026, 12, 31, tzinfo=UTC)
        fa = FailureAlertConfig(after=5, cooldown_seconds=600)
        mgr = make_manager()
        job = await mgr.create_job(
            "Test",
            JobType.AGENT,
            make_schedule(),
            prompt="hello",
            cooldown_seconds=60,
            max_fires=100,
            expires_at=dt,
            session_target=SessionTarget.MAIN,
            run_retention_days=90,
            failure_alert=fa,
        )
        assert job.cooldown_seconds == 60
        assert job.max_fires == 100
        assert job.expires_at == dt
        assert job.session_target == SessionTarget.MAIN
        assert job.run_retention_days == 90
        assert job.failure_alert == fa

    @pytest.mark.asyncio
    async def test_failure_alert_true_is_stored_as_the_global_default(self):
        """``True`` has no per-job config to keep; a stored bool would break serialisation."""
        mgr = make_manager()
        job = await mgr.create_job("Test", JobType.AGENT, make_schedule(), prompt="hello", failure_alert=True)
        assert job.failure_alert is None
        assert failure_alert_to_dict(job.failure_alert) is None

    @pytest.mark.asyncio
    async def test_failure_alert_false_stays_disabled(self):
        mgr = make_manager()
        job = await mgr.create_job("Test", JobType.AGENT, make_schedule(), prompt="hello", failure_alert=False)
        assert job.failure_alert is False
        assert failure_alert_to_dict(job.failure_alert) is False


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------


class TestValidation:
    def test_agent_requires_prompt(self) -> None:
        mgr = make_manager()
        with pytest.raises(ValueError, match=r"(?i)agent job requires a non-empty"):
            mgr._validate_create(JobType.AGENT, make_schedule(), None, None)

    def test_shell_requires_command(self) -> None:
        mgr = make_manager()
        with pytest.raises(ValueError, match=r"(?i)shell job requires a non-empty"):
            mgr._validate_create(JobType.SHELL, make_schedule(), None, None)

    def test_shell_disabled(self) -> None:
        mgr = make_manager(shell_enabled=False)
        with pytest.raises(ValueError, match="shell jobs are not enabled"):
            mgr._validate_create(JobType.SHELL, make_schedule(), None, "echo hi")

    def test_invalid_cron_expr(self) -> None:
        mgr = make_manager()
        bad_schedule = make_schedule(expr="not-valid")
        with pytest.raises(ValueError, match="invalid cron expression"):
            mgr._validate_create(JobType.AGENT, bad_schedule, "prompt", None)

    def test_invalid_timezone(self) -> None:
        mgr = make_manager()
        tz_schedule = Schedule(kind=ScheduleKind.CRON, expr="0 * * * *", tz="Fake/Zone")
        with pytest.raises(ValueError, match="unknown timezone"):
            mgr._validate_create(JobType.AGENT, tz_schedule, "prompt", None)


# ---------------------------------------------------------------------------
# context_from validation & CRUD
# ---------------------------------------------------------------------------


class TestContextFrom:
    """Tests for context_from validation and CRUD integration."""

    @pytest.mark.asyncio
    async def test_validate_context_from_self_reference_rejected(self) -> None:
        """Self-referencing context_from must raise ValueError."""
        mgr = make_manager()
        with pytest.raises(ValueError, match="must not reference the job itself"):
            await mgr._validate_context_from("job-1", ("job-1",))

    @pytest.mark.asyncio
    async def test_validate_context_from_nonexistent_rejected(self) -> None:
        """Referencing a non-existent job must raise ValueError."""
        mgr = make_manager()
        mgr._store.get_job = AsyncMock(return_value=None)
        with pytest.raises(ValueError, match="non-existent job"):
            await mgr._validate_context_from("job-1", ("does-not-exist",))

    @pytest.mark.asyncio
    async def test_validate_context_from_valid(self) -> None:
        """Valid references should not raise."""
        mgr = make_manager()
        ref_job = make_job(id="ref-1")
        mgr._store.get_job = AsyncMock(return_value=ref_job)
        await mgr._validate_context_from("job-1", ("ref-1",))

    @pytest.mark.asyncio
    async def test_create_job_with_context_from(self) -> None:
        """Creating a job with context_from should persist the field."""
        mgr = make_manager()
        ref_job = make_job(id="ref-1")
        mgr._store.get_job = AsyncMock(return_value=ref_job)

        job = await mgr.create_job(
            name="Analyzer",
            job_type=JobType.AGENT,
            schedule=make_schedule(),
            prompt="analyze data",
            context_from=("ref-1",),
        )
        assert job.context_from == ("ref-1",)

    @pytest.mark.asyncio
    async def test_create_job_with_invalid_context_from_rejected(self) -> None:
        """Creating a job with non-existent context_from should fail."""
        mgr = make_manager()
        mgr._store.get_job = AsyncMock(return_value=None)

        with pytest.raises(ValueError, match="non-existent job"):
            await mgr.create_job(
                name="Bad Ref",
                job_type=JobType.AGENT,
                schedule=make_schedule(),
                prompt="test",
                context_from=("ghost-job",),
            )

    @pytest.mark.asyncio
    async def test_update_job_set_context_from(self) -> None:
        """Updating context_from should validate and persist."""
        mgr = make_manager()
        existing = make_job(context_from=())
        ref_job = make_job(id="ref-1")

        async def mock_get(job_id: str) -> CronJob | None:
            if job_id == "job-1":
                return existing
            if job_id == "ref-1":
                return ref_job
            return None

        mgr._store.get_job = AsyncMock(side_effect=mock_get)
        result = await mgr.update_job("job-1", CronJobPatch(context_from=("ref-1",)))
        assert result is not None
        assert result.context_from == ("ref-1",)

    @pytest.mark.asyncio
    async def test_update_job_clear_context_from(self) -> None:
        """clear_context_from should empty the field."""
        mgr = make_manager()
        existing = make_job(context_from=("ref-1",))
        mgr._store.get_job = AsyncMock(return_value=existing)
        result = await mgr.update_job("job-1", CronJobPatch(clear_context_from=True))
        assert result is not None
        assert result.context_from == ()
