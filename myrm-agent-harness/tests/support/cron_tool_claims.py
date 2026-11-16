"""What a model gets from the ``cron_manage`` tool, one check per promise its description makes.

[INPUT]
- core.context_vars::user_timezone_var (POS: the zone the request carries)
- toolkits.cron.blueprint_job_spec::BlueprintFiller, BlueprintJobSpec (POS: the blueprint a model may name)
- toolkits.cron.cron_agent_tools::create_cron_tools (POS: the tool under test)
- tests.support.cron_manager_stack::ManagerStack, make_manager_stack (POS: a real manager over the in-memory store)

[OUTPUT]
- World: the tool a model calls and the store it writes to, with `call`, `add`, `accepted_job` and `refused`
- OkRunner: a runner whose every run succeeds
- one check coroutine per promise (`one_schedule`, `cron_gap_floor`, `run_is_a_trial`, ...): runs the behavior the
  sentence promises and asserts it
- SHANGHAI / NEW_YORK / MEETING / MEETING_UTC / MODEL / ACTIONS: the values the checks and the claim table share

[POS]
Behavior half of the description contract: ``test_cron_tool_description_contract.py`` holds the sentences and pins them
in both languages, this module holds what each sentence must be true of.
"""

from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import UTC, datetime

from myrm_agent_harness.core.context_vars import user_timezone_var
from myrm_agent_harness.toolkits.cron.blueprint_job_spec import BlueprintFiller, BlueprintJobSpec
from myrm_agent_harness.toolkits.cron.cron_agent_tools import create_cron_tools
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    JobResult,
    JobStatus,
    JobType,
    Schedule,
    ScheduleKind,
    SessionTarget,
)
from tests.support.cron_manager_stack import ManagerStack

MODEL = "test/model"
SHANGHAI = "Asia/Shanghai"
NEW_YORK = "America/New_York"
# Far enough ahead that a one-time task is always in the future, on a day with no daylight-saving change.
MEETING = "2031-06-15T09:00:00"
MEETING_UTC = datetime(2031, 6, 15, 1, 0, tzinfo=UTC)  # the same wall clock read in Shanghai
ACTIONS = {"add", "list", "update", "remove", "run", "pause", "resume", "blueprints"}
_SUCCESS = '"status": "success"'
_RECURRING = {"recurring_confirmed": True}
_DAILY = {"cron_expr": "0 9 * * *", **_RECURRING}
_POLL_URL = "https://example.com/data"


class OkRunner:
    async def run(self, job: CronJob, *, context: str = "") -> JobResult:
        return JobResult(success=True, output="ok")


@dataclass
class World:
    """The tool a model calls and the store it writes to."""

    stack: ManagerStack
    filler: BlueprintFiller | None = None

    async def call(self, **args: object) -> str:
        tool = create_cron_tools(self.stack.manager, current_model=MODEL, chat_id="c", blueprint_filler=self.filler)[0]
        return str(await tool.ainvoke(args))

    async def add(self, **args: object) -> str:
        return await self.call(**{"action": "add", "prompt": "p", **args})

    async def accepted_job(self, **args: object) -> CronJob:
        """Add a task, assert the tool accepted it and return it as stored."""
        out = await self.add(**args)
        assert _SUCCESS in out, out
        return await self.stack.stored(json.loads(out)["job_id"])

    async def refused(self, **args: object) -> str:
        """Add a task, assert the tool refused it and stored nothing; return the refusal."""
        before = len(await self.stack.store.list_jobs())
        out = await self.add(**args)
        assert _SUCCESS not in out and len(await self.stack.store.list_jobs()) == before, out
        return out


async def one_schedule(w: World) -> None:
    assert "ONE schedule param" in await w.refused(cron_expr="0 9 * * *", every_minutes=30, **_RECURRING)


async def recurring_needs_confirmation(w: World) -> None:
    for schedule in ({"cron_expr": "0 9 * * *"}, {"every_minutes": 30}):
        await w.refused(**schedule)
        await w.accepted_job(**schedule, **_RECURRING)


async def command_excludes_prompt(w: World) -> None:
    await w.refused(command="echo hi", **_DAILY)


async def reminder_takes_a_prompt_only(w: World) -> None:
    await w.refused(reminder=True, command="echo hi", at=MEETING)
    assert (await w.accepted_job(reminder=True, at=MEETING)).job_type == JobType.REMINDER


async def blueprint_brings_its_schedule(w: World) -> None:
    schedule = Schedule(kind=ScheduleKind.CRON, expr="0 8 * * *")
    w.filler = lambda blueprint_id, values, tz: BlueprintJobSpec(schedule=schedule, prompt="brief", name="brief")
    assert "sets its own schedule" in await w.refused(blueprint="morning", every_minutes=30, **_RECURRING)
    assert (await w.accepted_job(blueprint="morning", **_RECURRING)).schedule.expr == "0 8 * * *"


async def event_trigger_needs_no_schedule(w: World) -> None:
    for trigger in ({"stream_url": "wss://example.com/feed"}, {"poll_url": _POLL_URL}):
        job = await w.accepted_job(**trigger)
        assert (job.schedule.kind, job.schedule.interval_ms) == (ScheduleKind.INTERVAL, 5 * 60_000)


async def every_minutes_floor(w: World) -> None:
    await w.refused(every_minutes=4, **_RECURRING)
    assert (await w.accepted_job(every_minutes=5, **_RECURRING)).schedule.interval_ms == 5 * 60_000


async def cron_gap_floor(w: World) -> None:
    for too_fast in ("* * * * *", "*/4 * * * *", "0,3 * * * *"):
        await w.refused(cron_expr=too_fast, **_RECURRING)
    await w.accepted_job(cron_expr="*/5 * * * *", **_RECURRING)


async def at_is_in_the_future(w: World) -> None:
    await w.refused(at="2020-01-01T10:00:00")
    await w.accepted_job(at=MEETING)


async def tz_reads_every_wall_clock_time(w: World) -> None:
    once = await w.accepted_job(at=MEETING, tz=SHANGHAI)
    assert once.schedule.run_at == MEETING_UTC
    with_offset = await w.accepted_job(at="2031-06-15T09:00:00+02:00", tz=SHANGHAI)
    assert with_offset.schedule.run_at == datetime(2031, 6, 15, 7, 0, tzinfo=UTC)
    recurring = await w.accepted_job(
        tz=SHANGHAI, active_start="08:00", active_end="20:00", expires_after=MEETING, **_DAILY
    )
    assert recurring.schedule.tz == SHANGHAI and recurring.expires_at == MEETING_UTC
    assert recurring.next_run_at is not None and recurring.next_run_at.astimezone(UTC).hour == 1


async def tz_falls_back(w: World) -> None:
    assert (await w.accepted_job(at=MEETING)).schedule.run_at == datetime(2031, 6, 15, 9, 0, tzinfo=UTC)
    token = user_timezone_var.set(SHANGHAI)
    try:
        assert (await w.accepted_job(at=MEETING)).schedule.run_at == MEETING_UTC
        new_yorker = await w.accepted_job(tz=NEW_YORK, **_DAILY)
        await w.call(action="update", job_id=new_yorker.id, cron_expr="0 10 * * *")
    finally:
        user_timezone_var.reset(token)
    assert (await w.stack.stored(new_yorker.id)).schedule.tz == NEW_YORK


async def active_window(w: World) -> None:
    assert (await w.accepted_job(active_start="09:00", **_DAILY)).active_hours is None
    both = await w.accepted_job(active_start="09:00", active_end="18:00", tz=SHANGHAI, **_DAILY)
    assert both.active_hours is not None and both.active_hours.tz == SHANGHAI
    own = await w.accepted_job(active_start="09:00", active_end="18:00", tz=SHANGHAI, active_tz=NEW_YORK, **_DAILY)
    assert own.active_hours is not None and own.active_hours.tz == NEW_YORK


async def max_fires(w: World) -> None:
    assert (await w.accepted_job(max_fires=0, **_DAILY)).max_fires is None
    limited = await w.accepted_job(max_fires=3, **_DAILY)
    await w.call(action="update", job_id=limited.id, max_fires=0)
    assert (await w.stack.stored(limited.id)).max_fires == 3


async def expires_after(w: World) -> None:
    for text, days in (("3d", 3), ("2w", 14), ("3m", 90)):
        job = await w.accepted_job(expires_after=text, **_DAILY)
        assert job.expires_at is not None
        assert abs((job.expires_at - datetime.now(UTC)).total_seconds() - days * 86_400) < 60
    assert (await w.accepted_job(expires_after="2031-06-15T09:00:00+08:00", **_DAILY)).expires_at == MEETING_UTC


async def run_is_a_trial(w: World) -> None:
    recurring = await w.accepted_job(max_fires=3, **_DAILY)
    one_time = await w.accepted_job(at=MEETING)
    for job in (recurring, one_time):
        assert await w.call(action="run", job_id=job.id) == f"Task {job.id} triggered."
        await w.stack.settle()
        after = await w.stack.stored(job.id)
        assert (after.status, after.next_run_at, after.fire_count) == (JobStatus.ACTIVE, job.next_run_at, 0)
        assert after.last_run_at is not None


async def session_modes(w: World) -> None:
    modes = {"isolated": SessionTarget.ISOLATED, "main": SessionTarget.MAIN, "daily": SessionTarget.DAILY}
    for mode, target in modes.items():
        assert (await w.accepted_job(session_mode=mode, **_DAILY)).session_target == target
    await w.refused(session_mode="weekly", **_DAILY)


async def names(w: World) -> None:
    assert (await w.accepted_job(prompt="Check the inbox", **_DAILY)).name.strip()
    await w.accepted_job(name="Backup DB", **_DAILY)
    for needle in ("backup", "BACKUP", "up D"):
        assert "Backup DB" in await w.call(action="list", name_filter=needle)
    assert "Backup DB" not in await w.call(action="list", name_filter="restore")


async def model(w: World) -> None:
    assert (await w.accepted_job(**_DAILY)).model == MODEL
    assert (await w.accepted_job(model="openai/gpt-4o-mini", **_DAILY)).model == "openai/gpt-4o-mini"


async def tools_allowed(w: World) -> None:
    job = await w.accepted_job(tools_allowed="web_search,memory", **_DAILY)
    assert tuple(job.tools_allowed or ()) == ("web_search", "memory")


async def poll_interval(w: World) -> None:
    await w.refused(poll_url=_POLL_URL, poll_interval_seconds=30)
    job = await w.accepted_job(poll_url=_POLL_URL)
    assert job.triggers is not None and job.triggers.polls[0].interval_seconds == 300


async def monitor(w: World) -> None:
    hashed = await w.accepted_job(monitor_enabled=True, monitor_type="hash", **_DAILY)
    assert hashed.monitor_config is not None and hashed.monitor_config.monitor_type == "hash"
    await w.refused(monitor_enabled=True, monitor_type="bogus", **_DAILY)
    watched = await w.accepted_job(monitor_enabled=True, **_DAILY)
    await w.call(action="update", job_id=watched.id, monitor_type="off")
    assert (await w.stack.stored(watched.id)).monitor_config is None


async def context_from(w: World) -> None:
    source = await w.accepted_job(**_DAILY)
    assert (await w.accepted_job(context_from=source.id, **_DAILY)).context_from == (source.id,)
    await w.refused(context_from="does-not-exist", **_DAILY)
