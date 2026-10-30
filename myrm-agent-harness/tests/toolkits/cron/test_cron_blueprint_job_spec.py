"""A blueprint fill creates exactly the job it defines through cron_manage_tool add."""

from __future__ import annotations

import inspect
import json
from dataclasses import MISSING, fields

import pytest

from myrm_agent_harness.infra.incremental.types import MonitorConfig
from myrm_agent_harness.toolkits.cron.blueprint_job_spec import DEFAULT_JOB_TIMEOUT_SECONDS, BlueprintJobSpec
from myrm_agent_harness.toolkits.cron.cron_agent_tools import create_cron_tools
from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
from myrm_agent_harness.toolkits.cron.manager import CronManager
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronConfig,
    CronJob,
    FailureAlertConfig,
    JobType,
    Schedule,
    ScheduleKind,
    SessionTarget,
)

_USER = "spec-user"


class _NoDelivery:
    async def deliver(self, job: object, result: object) -> None:
        pass


def _full_spec() -> BlueprintJobSpec:
    """A spec whose every field differs from the dataclass default."""
    return BlueprintJobSpec(
        schedule=Schedule(kind=ScheduleKind.CRON, expr="30 8 * * 1-5", tz="Asia/Shanghai"),
        prompt="relay the digest",
        name="Weekday digest",
        required_capabilities=("web_search_tool",),
        tools_allowed=("web_search",),
        skill_ids=("digest-skill",),
        job_type=JobType.ROUTER,
        session_target=SessionTarget.DAILY,
        deduplicate=True,
        skip_if_active=True,
        timeout_seconds=45,
        monitor_config=MonitorConfig(monitor_type="hash", ttl_days=7, enabled=True),
        failure_alert=FailureAlertConfig(enabled=True, after=2, cooldown_seconds=900),
        pre_condition_script="echo '{\"ok\": true}'",
        command="wiki.source_sync",
    )


class _Harness:
    def __init__(self, spec: BlueprintJobSpec | None) -> None:
        self.store = InMemoryCronStore()
        scheduler = CronScheduler(store=self.store, runners={}, delivery=_NoDelivery(), config=CronConfig())
        manager = CronManager(self.store, scheduler, shell_enabled=True)
        self.requests: list[tuple[str, dict[str, str], str | None]] = []

        def filler(bp_id: str, values: dict[str, str], tz: str | None) -> BlueprintJobSpec | None:
            self.requests.append((bp_id, values, tz))
            return spec

        self.tool = create_cron_tools(manager, _USER, current_model="m", blueprint_filler=filler)[0]

    async def add(self, **args: object) -> str:
        args.setdefault("blueprint", "bp")
        args.setdefault("recurring_confirmed", True)
        result: str = await self.tool.ainvoke({"action": "add", **args})
        return result

    async def only_job(self) -> CronJob:
        jobs = await self.store.list_jobs()
        assert len(jobs) == 1
        return jobs[0]


def test_full_spec_leaves_no_field_at_its_default() -> None:
    spec = _full_spec()
    for spec_field in fields(BlueprintJobSpec):
        if spec_field.default is not MISSING:
            assert getattr(spec, spec_field.name) != spec_field.default, spec_field.name


async def test_every_spec_field_reaches_the_created_job() -> None:
    spec = _full_spec()
    harness = _Harness(spec)

    result = json.loads(await harness.add())

    job = await harness.only_job()
    assert result["status"] == "success"
    assert result["job_type"] == "Router"
    for spec_field in fields(BlueprintJobSpec):
        if spec_field.name == "schedule":
            continue
        assert getattr(job, spec_field.name) == getattr(spec, spec_field.name), spec_field.name
    assert (job.schedule.kind, job.schedule.expr, job.schedule.tz) == (
        ScheduleKind.CRON,
        "30 8 * * 1-5",
        "Asia/Shanghai",
    )


async def test_filler_receives_blueprint_id_values_and_timezone() -> None:
    harness = _Harness(_full_spec())

    await harness.add(blueprint=" bp ", blueprint_values='{"time": "08:30"}', tz="Asia/Tokyo")

    assert harness.requests == [("bp", {"time": "08:30"}, "Asia/Tokyo")]


async def test_unknown_blueprint_is_reported_and_creates_nothing() -> None:
    harness = _Harness(None)

    assert "unknown blueprint" in await harness.add()
    assert await harness.store.list_jobs() == []


async def test_explicit_session_mode_beats_the_blueprint_default() -> None:
    harness = _Harness(_full_spec())

    await harness.add(session_mode="main")

    assert (await harness.only_job()).session_target == SessionTarget.MAIN


async def test_blank_session_mode_uses_the_blueprint_default() -> None:
    harness = _Harness(_full_spec())

    await harness.add(session_mode="  ")

    assert (await harness.only_job()).session_target == SessionTarget.DAILY


async def test_explicit_monitor_beats_the_blueprint_monitor() -> None:
    harness = _Harness(_full_spec())

    await harness.add(monitor_type="set", monitor_enabled=True)

    monitor = (await harness.only_job()).monitor_config
    assert monitor is not None and monitor.monitor_type == "set"


async def test_monitor_off_beats_the_blueprint_monitor() -> None:
    harness = _Harness(_full_spec())

    await harness.add(monitor_type="off")

    assert (await harness.only_job()).monitor_config is None


async def test_explicit_csv_params_beat_the_blueprint_lists() -> None:
    harness = _Harness(_full_spec())

    await harness.add(required_capabilities="net_fetch", tools_allowed="read_file", skill_ids="other-skill")

    job = await harness.only_job()
    assert (job.required_capabilities, job.tools_allowed, job.skill_ids) == (
        ("net_fetch",),
        ("read_file",),
        ("other-skill",),
    )


async def test_blueprint_command_is_not_a_prompt_and_command_conflict() -> None:
    harness = _Harness(_full_spec())

    result = json.loads(await harness.add())

    assert result["status"] == "success"


async def test_command_typed_by_the_model_still_conflicts_with_the_blueprint_prompt() -> None:
    harness = _Harness(_full_spec())

    result = await harness.add(command="echo hi")

    assert result == "Provide either prompt (agent task) or command (shell task), not both."
    assert await harness.store.list_jobs() == []


async def test_shell_blueprint_without_prompt_creates_a_shell_job() -> None:
    spec = BlueprintJobSpec(
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 6 * * *"),
        prompt="",
        name="Nightly sync",
        job_type=JobType.SHELL,
        command="echo sync",
    )
    harness = _Harness(spec)

    result = json.loads(await harness.add())

    job = await harness.only_job()
    assert (result["job_type"], job.job_type, job.command) == ("Shell", JobType.SHELL, "echo sync")


async def test_interval_schedule_keeps_its_exact_interval() -> None:
    spec = BlueprintJobSpec(
        schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=90 * 60_000),
        prompt="check",
        name="Every ninety minutes",
    )
    harness = _Harness(spec)

    await harness.add()

    job = await harness.only_job()
    assert (job.schedule.kind, job.schedule.interval_ms) == (ScheduleKind.INTERVAL, 90 * 60_000)


async def test_blueprint_interval_keeps_the_minimum_interval_rail() -> None:
    spec = BlueprintJobSpec(
        schedule=Schedule(kind=ScheduleKind.INTERVAL, interval_ms=60_000), prompt="check", name="Every minute"
    )
    harness = _Harness(spec)

    result = await harness.add()

    assert result == "A blueprint interval must be at least 5 minutes."
    assert await harness.store.list_jobs() == []


@pytest.mark.parametrize("schedule_arg", [{"every_minutes": 30}, {"at": "2030-01-01T09:00:00"}])
async def test_blueprint_rejects_a_schedule_param_it_would_ignore(schedule_arg: dict[str, object]) -> None:
    harness = _Harness(_full_spec())

    result = await harness.add(**schedule_arg)

    assert result == "A blueprint sets its own schedule; do not pass every_minutes or at with it."
    assert await harness.store.list_jobs() == []


async def test_blueprint_schedule_wins_over_an_explicit_cron_expr() -> None:
    # The tool description asks for one schedule parameter next to a blueprint, so a cron_expr is accepted.
    harness = _Harness(_full_spec())

    await harness.add(cron_expr="0 1 * * *")

    job = await harness.only_job()
    assert (job.schedule.kind, job.schedule.expr) == (ScheduleKind.CRON, "30 8 * * 1-5")


async def test_recurring_blueprint_still_needs_confirmation() -> None:
    harness = _Harness(_full_spec())

    result = await harness.add(recurring_confirmed=False)

    assert "(cron_expr, every_minutes or a blueprint) require recurring_confirmed=true" in result
    assert await harness.store.list_jobs() == []


async def test_spec_without_timeout_uses_the_job_default() -> None:
    spec = BlueprintJobSpec(
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 6 * * *"), prompt="check", name="Default timeout"
    )
    harness = _Harness(spec)

    await harness.add()

    assert (await harness.only_job()).timeout_seconds == DEFAULT_JOB_TIMEOUT_SECONDS


def test_default_timeout_matches_the_job_and_manager_defaults() -> None:
    job_default = next(f.default for f in fields(CronJob) if f.name == "timeout_seconds")
    manager_default = inspect.signature(CronManager.create_job).parameters["timeout_seconds"].default

    assert DEFAULT_JOB_TIMEOUT_SECONDS == job_default == manager_default


async def test_add_without_blueprint_is_unchanged() -> None:
    harness = _Harness(_full_spec())

    result = json.loads(await harness.add(blueprint="", prompt="plain task", cron_expr="0 9 * * *"))

    job = await harness.only_job()
    assert harness.requests == []
    assert (result["job_type"], job.job_type, job.session_target) == ("Agent", JobType.AGENT, SessionTarget.ISOLATED)
    assert (job.deduplicate, job.skip_if_active, job.failure_alert, job.pre_condition_script, job.command) == (
        False,
        False,
        None,
        None,
        None,
    )
    assert job.timeout_seconds == DEFAULT_JOB_TIMEOUT_SECONDS
