"""The ``cron_manage`` tool reads every wall-clock time in one zone and says which; a schedule edit keeps the task's zone.

A time the model types without an offset (an ``at``, an ISO ``expires_after``, a cron expression, the active window)
means the requester's local time: the explicit ``tz``, else the task's own zone on an edit, else the zone the request
carries, else UTC. A time with an offset keeps it, a local time that daylight saving skips is refused, a repeated
one is the earlier, and every refusal comes back as text. A task created for ``Asia/Shanghai`` fires at the local
hour its owner named: an update that names only a new expression must not move it to UTC. These scenarios drive the
real tool over the real manager and the in-memory store.
"""

from __future__ import annotations

import json
from collections.abc import Iterator
from datetime import UTC, datetime

import pytest

from myrm_agent_harness.core.context_vars import user_timezone_var
from myrm_agent_harness.toolkits.cron.blueprint_job_spec import BlueprintJobSpec
from myrm_agent_harness.toolkits.cron.cron_agent_tools import create_cron_tools
from myrm_agent_harness.toolkits.cron.types import CronJob, Schedule, ScheduleKind
from tests.support.cron_manager_stack import ManagerStack, make_manager_stack

SHANGHAI = "Asia/Shanghai"
NEW_YORK = "America/New_York"
# Far enough ahead that a one-time task is always in the future, on a day with no daylight-saving change.
MEETING = "2031-06-15T09:00:00"
MEETING_UTC = datetime(2031, 6, 15, 1, 0, tzinfo=UTC)
MIN_GAP_MESSAGE = "cron_expr fires every {} min; the minimum is 5 min. For one-time tasks use 'at' instead."


@pytest.fixture
def stack() -> ManagerStack:
    return make_manager_stack()


@pytest.fixture
def requested_in_shanghai() -> Iterator[None]:
    token = user_timezone_var.set(SHANGHAI)
    yield
    user_timezone_var.reset(token)


async def _call(stack: ManagerStack, **args: object) -> str:
    tool = create_cron_tools(stack.manager, current_model="m", chat_id="c")[0]
    return str(await tool.ainvoke(args))


async def _only_job(stack: ManagerStack) -> CronJob:
    (job,) = await stack.store.list_jobs()
    return job


async def _add_daily_report(stack: ManagerStack, *, tz: str) -> CronJob:
    await _call(
        stack,
        action="add",
        prompt="daily report",
        cron_expr="0 9 * * *",
        tz=tz,
        recurring_confirmed=True,
        name="report",
    )
    return next(job for job in await stack.store.list_jobs() if job.name == "report")


class TestScheduleUpdateKeepsTheTimezone:
    async def test_a_new_expression_without_tz_keeps_the_jobs_timezone(self, stack: ManagerStack) -> None:
        job = await _add_daily_report(stack, tz=SHANGHAI)

        await _call(stack, action="update", job_id=job.id, cron_expr="0 10 * * *")

        updated = await stack.stored(job.id)
        assert updated.schedule.tz == SHANGHAI
        assert updated.next_run_at is not None
        assert (updated.next_run_at.hour, updated.next_run_at.minute) == (2, 0)  # 10:00 in Shanghai is 02:00 UTC

    async def test_an_explicit_tz_replaces_the_jobs_timezone(self, stack: ManagerStack) -> None:
        job = await _add_daily_report(stack, tz=SHANGHAI)

        await _call(stack, action="update", job_id=job.id, cron_expr="0 10 * * *", tz="UTC")

        updated = await stack.stored(job.id)
        assert updated.schedule.tz == "UTC"
        assert updated.next_run_at is not None
        assert (updated.next_run_at.hour, updated.next_run_at.minute) == (10, 0)

    async def test_a_job_without_a_timezone_stays_without_one(self, stack: ManagerStack) -> None:
        job = await _add_daily_report(stack, tz="")

        await _call(stack, action="update", job_id=job.id, cron_expr="0 10 * * *")

        assert (await stack.stored(job.id)).schedule.tz is None

    async def test_a_job_without_a_timezone_takes_the_requesters_on_an_edit(
        self, stack: ManagerStack, requested_in_shanghai: None
    ) -> None:
        job = await stack.create("report", Schedule(kind=ScheduleKind.CRON, expr="0 9 * * *"))
        assert job.schedule.tz is None

        await _call(stack, action="update", job_id=job.id, cron_expr="0 10 * * *")

        assert (await stack.stored(job.id)).schedule.tz == SHANGHAI

    async def test_switching_to_an_interval_succeeds_and_carries_no_timezone(self, stack: ManagerStack) -> None:
        job = await _add_daily_report(stack, tz=SHANGHAI)

        out = await _call(stack, action="update", job_id=job.id, every_minutes=30)

        assert '"status": "success"' in out
        updated = await stack.stored(job.id)
        assert updated.schedule.kind == ScheduleKind.INTERVAL
        assert updated.schedule.tz is None

    async def test_an_unknown_job_is_still_reported_as_not_found(self, stack: ManagerStack) -> None:
        assert await _call(stack, action="update", job_id="nope", cron_expr="0 10 * * *") == "Task nope not found."


class TestAWallClockTimeIsReadInTheRequestersZone:
    async def test_an_at_without_an_offset(self, stack: ManagerStack, requested_in_shanghai: None) -> None:
        await _call(stack, action="add", prompt="meeting", at=MEETING)

        assert (await _only_job(stack)).schedule.run_at == MEETING_UTC

    async def test_a_cron_expression_and_its_active_window(
        self, stack: ManagerStack, requested_in_shanghai: None
    ) -> None:
        await _call(
            stack,
            action="add",
            prompt="report",
            cron_expr="0 9 * * *",
            recurring_confirmed=True,
            active_start="08:00",
            active_end="20:00",
        )

        job = await _only_job(stack)
        assert job.schedule.tz == SHANGHAI
        assert job.active_hours is not None and job.active_hours.tz == SHANGHAI
        assert job.next_run_at is not None and job.next_run_at.hour == 1

    async def test_an_expiry_time_without_an_offset(self, stack: ManagerStack, requested_in_shanghai: None) -> None:
        await _call(
            stack, action="add", prompt="report", every_minutes=60, recurring_confirmed=True, expires_after=MEETING
        )

        assert (await _only_job(stack)).expires_at == MEETING_UTC

    async def test_a_blueprints_schedule(self, stack: ManagerStack, requested_in_shanghai: None) -> None:
        zones: list[str | None] = []

        def fill(blueprint_id: str, values: dict[str, str], tz: str | None) -> BlueprintJobSpec:
            zones.append(tz)
            return BlueprintJobSpec(
                schedule=Schedule(kind=ScheduleKind.CRON, expr="0 8 * * *", tz=tz), prompt="brief", name="brief"
            )

        tool = create_cron_tools(stack.manager, current_model="m", blueprint_filler=fill)[0]
        await tool.ainvoke({"action": "add", "blueprint": "morning", "recurring_confirmed": True})

        assert zones == [SHANGHAI]
        assert (await _only_job(stack)).schedule.tz == SHANGHAI

    async def test_an_explicit_zone_beats_the_requesters(
        self, stack: ManagerStack, requested_in_shanghai: None
    ) -> None:
        await _call(
            stack, action="add", prompt="meeting", at=MEETING, tz=NEW_YORK, active_start="08:00", active_end="10:00"
        )

        job = await _only_job(stack)
        assert job.schedule.run_at == datetime(2031, 6, 15, 13, 0, tzinfo=UTC)  # 09:00 EDT
        assert job.active_hours is not None and job.active_hours.tz == NEW_YORK

    async def test_an_offset_in_the_text_beats_every_zone(
        self, stack: ManagerStack, requested_in_shanghai: None
    ) -> None:
        await _call(stack, action="add", prompt="meeting", at="2031-06-15T09:00:00+02:00", tz=NEW_YORK)

        assert (await _only_job(stack)).schedule.run_at == datetime(2031, 6, 15, 7, 0, tzinfo=UTC)

    async def test_an_edited_at_is_read_in_the_requesters_zone_too(
        self, stack: ManagerStack, requested_in_shanghai: None
    ) -> None:
        await _call(stack, action="add", prompt="meeting", at=MEETING)
        job = await _only_job(stack)

        await _call(stack, action="update", job_id=job.id, at="2031-06-15T10:00:00")

        assert (await stack.stored(job.id)).schedule.run_at == datetime(2031, 6, 15, 2, 0, tzinfo=UTC)

    async def test_without_any_zone_it_is_utc(self, stack: ManagerStack) -> None:
        await _call(stack, action="add", prompt="meeting", at=MEETING)

        assert (await _only_job(stack)).schedule.run_at == datetime(2031, 6, 15, 9, 0, tzinfo=UTC)

    async def test_a_zone_the_request_carries_but_does_not_exist_counts_as_none(self, stack: ManagerStack) -> None:
        token = user_timezone_var.set("Not/AZone")
        try:
            await _call(stack, action="add", prompt="meeting", at=MEETING)
        finally:
            user_timezone_var.reset(token)

        assert (await _only_job(stack)).schedule.run_at == datetime(2031, 6, 15, 9, 0, tzinfo=UTC)


class TestDaylightSaving:
    async def test_a_local_time_the_clocks_skip_is_refused_and_nothing_is_stored(self, stack: ManagerStack) -> None:
        out = await _call(stack, action="add", prompt="meeting", at="2030-03-10T02:30:00", tz=NEW_YORK)

        assert "does not exist in America/New_York" in out and "choose a different time" in out
        assert await stack.store.list_jobs() == []

    async def test_a_repeated_local_time_is_the_earlier_instant(self, stack: ManagerStack) -> None:
        await _call(stack, action="add", prompt="meeting", at="2030-11-03T01:30:00", tz=NEW_YORK)

        run_at = (await _only_job(stack)).schedule.run_at
        assert run_at is not None
        # An aware time inside a repeated hour never compares equal across clocks (PEP 495), so compare the instant.
        assert run_at.astimezone(UTC) == datetime(
            2030, 11, 3, 5, 30, tzinfo=UTC
        )  # 01:30 EDT, before the clocks fall back

    async def test_the_hour_after_the_gap_is_accepted(self, stack: ManagerStack) -> None:
        await _call(stack, action="add", prompt="meeting", at="2030-03-10T03:30:00", tz=NEW_YORK)

        assert (await _only_job(stack)).schedule.run_at == datetime(2030, 3, 10, 7, 30, tzinfo=UTC)


class TestARefusalIsTextNeverAnException:
    async def test_an_at_that_is_not_a_date_time(self, stack: ManagerStack) -> None:
        out = await _call(stack, action="add", prompt="meeting", at="tomorrow at nine")

        assert out.startswith("Invalid at 'tomorrow at nine'") and "ISO 8601" in out
        assert await stack.store.list_jobs() == []

    @pytest.mark.parametrize("field", ["tz", "active_tz"])
    async def test_an_unknown_zone_on_add(self, stack: ManagerStack, field: str) -> None:
        args = {
            "action": "add",
            "prompt": "report",
            "cron_expr": "0 9 * * *",
            "recurring_confirmed": True,
            field: "Mars/Base",
        }
        if field == "active_tz":
            args |= {"active_start": "08:00", "active_end": "20:00"}

        out = await _call(stack, **args)

        assert out.startswith("Unknown timezone 'Mars/Base'")
        assert await stack.store.list_jobs() == []

    async def test_an_unknown_zone_on_update(self, stack: ManagerStack) -> None:
        job = await _add_daily_report(stack, tz=SHANGHAI)

        out = await _call(stack, action="update", job_id=job.id, cron_expr="0 10 * * *", tz="Mars/Base")

        assert out.startswith("Unknown timezone 'Mars/Base'")
        assert (await stack.stored(job.id)).schedule.expr == "0 9 * * *"


class TestTheResultNamesTheZone:
    async def test_add_update_and_resume_give_the_zone_and_the_next_run_on_its_clock(self, stack: ManagerStack) -> None:
        added = json.loads(
            await _call(
                stack, action="add", prompt="report", cron_expr="0 9 * * *", tz=SHANGHAI, recurring_confirmed=True
            )
        )
        job_id = added["job_id"]
        updated = json.loads(await _call(stack, action="update", job_id=job_id, cron_expr="0 10 * * *"))
        await _call(stack, action="pause", job_id=job_id)
        resumed = json.loads(await _call(stack, action="resume", job_id=job_id))

        for result, hour in ((added, 9), (updated, 10), (resumed, 10)):
            assert result["timezone"] == SHANGHAI
            assert result["next_run_local"].endswith("+08:00")
            assert datetime.fromisoformat(result["next_run_local"]).hour == hour

    async def test_a_one_time_task_reports_the_zone_its_time_was_read_in(
        self, stack: ManagerStack, requested_in_shanghai: None
    ) -> None:
        explicit = json.loads(await _call(stack, action="add", prompt="meeting", at=MEETING, tz=NEW_YORK))
        requested = json.loads(await _call(stack, action="add", prompt="meeting", at=MEETING))
        edited = json.loads(await _call(stack, action="update", job_id=explicit["job_id"], at="2031-06-15T10:00:00"))

        assert (explicit["timezone"], explicit["next_run_local"]) == (NEW_YORK, "2031-06-15T09:00:00-04:00")
        assert (requested["timezone"], requested["next_run_local"]) == (SHANGHAI, "2031-06-15T09:00:00+08:00")
        assert (edited["timezone"], edited["next_run_local"]) == (SHANGHAI, "2031-06-15T10:00:00+08:00")

    async def test_a_task_without_any_zone_reports_utc(self, stack: ManagerStack) -> None:
        added = json.loads(await _call(stack, action="add", prompt="meeting", at=MEETING))

        assert added["timezone"] == "UTC"
        assert added["next_run"] == "2031-06-15 09:00 UTC" and added["next_run_local"] == "2031-06-15T09:00:00+00:00"

    async def test_the_expiry_is_reported_in_utc_whatever_zone_it_was_given_in(self, stack: ManagerStack) -> None:
        added = json.loads(
            await _call(
                stack,
                action="add",
                prompt="report",
                every_minutes=60,
                recurring_confirmed=True,
                expires_after="2031-06-15T09:00:00+08:00",
            )
        )

        assert added["expires_at"] == "2031-06-15 01:00 UTC"


class TestACronExpressionKeepsTheMinimumGap:
    @pytest.mark.parametrize(("expr", "gap"), [("* * * * *", 1), ("*/4 * * * *", 4), ("0,3 * * * *", 3)])
    async def test_a_faster_expression_is_refused_on_add_and_on_update(
        self, stack: ManagerStack, expr: str, gap: int
    ) -> None:
        refused = MIN_GAP_MESSAGE.format(gap)
        added = await _call(stack, action="add", prompt="spam", cron_expr=expr, recurring_confirmed=True)
        job = await _add_daily_report(stack, tz="")
        updated = await _call(stack, action="update", job_id=job.id, cron_expr=expr)

        assert (added, updated) == (refused, refused)
        assert [j.name for j in await stack.store.list_jobs()] == ["report"]
        assert (await stack.stored(job.id)).schedule.expr == "0 9 * * *"

    @pytest.mark.parametrize("expr", ["*/5 * * * *", "0 9 * * 1-5", "0,10,20 * * * *"])
    async def test_an_expression_at_or_above_the_minimum_is_accepted(self, stack: ManagerStack, expr: str) -> None:
        out = await _call(stack, action="add", prompt="ok", cron_expr=expr, recurring_confirmed=True)

        assert '"status": "success"' in out

    async def test_every_minutes_keeps_its_own_message(self, stack: ManagerStack) -> None:
        out = await _call(stack, action="add", prompt="spam", every_minutes=1, recurring_confirmed=True)

        assert out == "every_minutes must be >= 5. For one-time tasks use 'at' instead."
