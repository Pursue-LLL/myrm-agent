"""Editing a task's schedule through the ``cron_manage`` tool keeps the timezone the task already has.

A task created for ``Asia/Shanghai`` fires at the local hour its owner named. An update that names only a new
expression must not move it to UTC: the tool reads the task's own timezone when the call does not repeat one, an
explicit ``tz`` replaces it, and a switch to an interval carries none. These scenarios drive the real tool over the
real manager and the in-memory store.
"""

from __future__ import annotations

import pytest

from myrm_agent_harness.toolkits.cron.cron_agent_tools import create_cron_tools
from myrm_agent_harness.toolkits.cron.types import CronJob, ScheduleKind
from tests.support.cron_manager_stack import ManagerStack, make_manager_stack

SHANGHAI = "Asia/Shanghai"


@pytest.fixture
def stack() -> ManagerStack:
    return make_manager_stack()


async def _call(stack: ManagerStack, **args: object) -> str:
    tool = create_cron_tools(stack.manager, current_model="m", chat_id="c")[0]
    return str(await tool.ainvoke(args))


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

    async def test_switching_to_an_interval_succeeds_and_carries_no_timezone(self, stack: ManagerStack) -> None:
        job = await _add_daily_report(stack, tz=SHANGHAI)

        out = await _call(stack, action="update", job_id=job.id, every_minutes=30)

        assert '"status": "success"' in out
        updated = await stack.stored(job.id)
        assert updated.schedule.kind == ScheduleKind.INTERVAL
        assert updated.schedule.tz is None

    async def test_an_unknown_job_is_still_reported_as_not_found(self, stack: ManagerStack) -> None:
        assert await _call(stack, action="update", job_id="nope", cron_expr="0 10 * * *") == "Task nope not found."
