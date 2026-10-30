"""The ``cron_manage`` list line tells the model how often a job runs, when it last ran and why it failed."""

from __future__ import annotations

from datetime import UTC, datetime

import pytest

from myrm_agent_harness.toolkits.cron import job_listing
from myrm_agent_harness.toolkits.cron.cron_agent_tools import create_cron_tools
from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
from myrm_agent_harness.toolkits.cron.job_listing import format_job_line
from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronConfig,
    CronJob,
    JobType,
    RunStatus,
    Schedule,
    ScheduleKind,
)

USER_ID = "listing-user"
LAST_RUN = datetime(2026, 10, 30, 9, 5, tzinfo=UTC)
SECRET = "sk-" + "A1b2C3d4" * 5


def _job(**overrides: object) -> CronJob:
    fields: dict[str, object] = {
        "id": "job-1",
        "user_id": USER_ID,
        "name": "daily-report",
        "job_type": JobType.AGENT,
        "schedule": Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *", tz="Asia/Shanghai"),
        "prompt": "write the report",
    }
    fields.update(overrides)
    return CronJob(**fields)  # type: ignore[arg-type]


class _NoDelivery:
    async def deliver(self, job: CronJob, result: object) -> None:
        pass


class TestLastRun:
    def test_job_that_never_ran_has_no_last_segment(self) -> None:
        assert "last:" not in format_job_line(_job())

    def test_successful_run_shows_time_and_status_only(self) -> None:
        line = format_job_line(_job(last_run_at=LAST_RUN, last_status=RunStatus.OK))

        assert line.endswith("| last: 10-30 09:05 ok")

    @pytest.mark.parametrize("status", [RunStatus.ERROR, RunStatus.CIRCUIT_BREAK])
    def test_failed_run_shows_the_reason(self, status: RunStatus) -> None:
        line = format_job_line(_job(last_run_at=LAST_RUN, last_status=status, last_error="upstream returned 503"))

        assert line.endswith(f"| last: 10-30 09:05 {status.value} - upstream returned 503")

    def test_skipped_run_hides_the_older_error_it_did_not_cause(self) -> None:
        line = format_job_line(_job(last_run_at=LAST_RUN, last_status=RunStatus.SKIPPED, last_error="old failure"))

        assert line.endswith("| last: 10-30 09:05 skipped")
        assert "old failure" not in line

    def test_failed_run_without_a_stored_reason_ends_after_the_status(self) -> None:
        line = format_job_line(_job(last_run_at=LAST_RUN, last_status=RunStatus.ERROR, last_error=None))

        assert line.endswith("| last: 10-30 09:05 error")


class TestFailureReason:
    def test_credentials_are_redacted(self) -> None:
        line = format_job_line(
            _job(last_run_at=LAST_RUN, last_status=RunStatus.ERROR, last_error=f"401 invalid key {SECRET}")
        )

        assert SECRET not in line
        assert "401 invalid key" in line

    def test_a_secret_cut_by_the_display_limit_is_redacted_first(self) -> None:
        # The secret starts before the 120-character display limit and ends after it: cutting first would leave
        # a prefix too short for the redactor to recognise.
        error = "x" * 108 + f" {SECRET}"
        line = format_job_line(_job(last_run_at=LAST_RUN, last_status=RunStatus.ERROR, last_error=error))

        assert "sk-A1b2" not in line

    def test_long_reason_is_cut_with_an_ellipsis(self) -> None:
        line = format_job_line(_job(last_run_at=LAST_RUN, last_status=RunStatus.ERROR, last_error="e" * 500))
        reason = line.split(" - ", 1)[1]

        assert len(reason) == 120
        assert reason.endswith("…")

    def test_multi_line_traceback_stays_on_one_line(self) -> None:
        traceback = 'Traceback (most recent call last):\n  File "a.py", line 1\nValueError: bad input'
        line = format_job_line(_job(last_run_at=LAST_RUN, last_status=RunStatus.ERROR, last_error=traceback))

        assert "\n" not in line
        assert line.endswith("ValueError: bad input")

    def test_only_a_bounded_prefix_is_scanned(self, monkeypatch: pytest.MonkeyPatch) -> None:
        # A stored error can be a whole traceback; the redaction cost must not grow with it.
        scanned: list[int] = []

        def spy(text: str) -> str:
            scanned.append(len(text))
            return text

        monkeypatch.setattr(job_listing, "redact_sensitive_text", spy)

        line = format_job_line(
            _job(last_run_at=LAST_RUN, last_status=RunStatus.ERROR, last_error="short " + "z" * 5_000_000)
        )

        assert scanned == [2000]
        assert len(line) < 400


class TestScheduleTag:
    def test_recurring_job_states_how_often_it_runs(self) -> None:
        assert "| active | cron: 0 9 * * * (Asia/Shanghai) | next:" in format_job_line(_job())

    def test_interval_job_states_its_interval(self) -> None:
        line = format_job_line(_job(schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=1_800_000)))

        assert "| active | every 30m | next:" in line

    def test_one_time_job_omits_what_next_already_says(self) -> None:
        run_at = datetime(2026, 11, 1, 8, 0, tzinfo=UTC)
        line = format_job_line(_job(schedule=Schedule(kind=ScheduleKind.ONCE, run_at=run_at), next_run_at=run_at))

        assert "| active | next: 11-01 08:00" in line
        assert "once at" not in line


@pytest.mark.asyncio
async def test_list_action_carries_the_last_failure_to_the_model() -> None:
    store = InMemoryCronStore()
    manager = CronManager(
        store,
        CronScheduler(store=store, runners={}, delivery=_NoDelivery(), config=CronConfig()),
        shell_enabled=True,
    )
    tool = create_cron_tools(manager, USER_ID, current_model="test-model")[0]
    job = await manager.create_job(
        user_id=USER_ID,
        name="nightly-sync",
        job_type=JobType.AGENT,
        schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=3_600_000),
        prompt="sync",
    )
    job.last_run_at = LAST_RUN
    job.last_status = RunStatus.ERROR
    job.last_error = f"auth failed for {SECRET}"
    await store.save_job(job)

    result = await tool.ainvoke({"action": "list"})

    assert "nightly-sync" in result
    assert "| every 1h |" in result
    assert "last: 10-30 09:05 error - auth failed for" in result
    assert SECRET not in result
