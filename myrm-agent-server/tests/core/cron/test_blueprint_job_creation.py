"""Contract: every job created from a blueprint carries everything the blueprint defines.

The agent tool and the preset/hygiene creator both build their job from the blueprint fill, so each
declared field (job type, command, overlap policy, timeout, monitoring, failure alerting, pre-condition
script, ...) must reach the stored job on every path, for every built-in blueprint.
"""

from __future__ import annotations

import json
from dataclasses import fields

import pytest
from myrm_agent_harness.infra.incremental.types import MonitorConfig
from myrm_agent_harness.toolkits import create_cron_tools
from myrm_agent_harness.toolkits.cron import BlueprintJobSpec, CronConfig, CronManager, CronScheduler
from myrm_agent_harness.toolkits.cron.stores import InMemoryCronStore
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    FailureAlertConfig,
    JobType,
    Schedule,
    ScheduleKind,
    SessionTarget,
)

from app.core.cron.adapters.entitlement_guarded_manager import EntitlementGuardedCronManager
from app.core.cron.blueprint_job_spec import create_blueprint_job, fill_job_spec, to_job_spec
from app.core.cron.blueprints import (
    BUILTIN_BLUEPRINTS,
    BlueprintFailureAlertDefaults,
    BlueprintFillResult,
    BlueprintMonitorDefaults,
    BlueprintScheduleResult,
    CronBlueprint,
    fill_blueprint,
)

_USER = "blueprint-user"
_DEFAULT_TIMEOUT = 300


class _NoDelivery:
    async def deliver(self, job: object, result: object) -> None:
        pass


def _manager() -> tuple[InMemoryCronStore, CronManager]:
    store = InMemoryCronStore()
    scheduler = CronScheduler(store=store, runners={}, delivery=_NoDelivery(), config=CronConfig())
    return store, CronManager(store, scheduler, shell_enabled=True)


def _slot_values(blueprint: CronBlueprint) -> dict[str, str]:
    """Values for the slots a blueprint cannot default (the rest keep their defaults)."""
    return {slot.name: "sample" for slot in blueprint.slots if not slot.optional and not slot.default}


def _declared(fill: BlueprintFillResult) -> dict[str, object]:
    """What the blueprint declares, keyed by BlueprintFillResult field, in the shape a stored job reports it.

    An empty ``tools_allowed`` means "no restriction", the same as None, so both compare as None.
    """
    monitor, alert = fill.monitor_config, fill.failure_alert
    declared: dict[str, object] = {
        "schedule": (fill.schedule.kind, fill.schedule.expr, fill.schedule.tz),
        "prompt": fill.prompt,
        "name": fill.name,
        "required_capabilities": fill.required_capabilities,
        "tools_allowed": fill.tools_allowed or None,
        "skill_ids": fill.skill_ids,
        "job_type": fill.job_type,
        "session_target": fill.session_target,
        "deduplicate": fill.deduplicate,
        "skip_if_active": fill.skip_if_active,
        "timeout_seconds": fill.timeout_seconds or _DEFAULT_TIMEOUT,
        "monitor_config": (monitor.monitor_type, monitor.ttl_days, monitor.enabled) if monitor else None,
        "failure_alert": (alert.enabled, alert.after, alert.cooldown_seconds) if alert else None,
        "pre_condition_script": fill.pre_condition_script or None,
        "command": fill.command,
    }
    assert set(declared) == {f.name for f in fields(BlueprintFillResult)}, "a BlueprintFillResult field is not checked"
    return declared


def _stored(job: CronJob) -> dict[str, object]:
    monitor, alert = job.monitor_config, job.failure_alert
    assert alert is None or isinstance(alert, FailureAlertConfig)
    return {
        "schedule": (job.schedule.kind.value, job.schedule.expr, job.schedule.tz),
        "prompt": job.prompt,
        "name": job.name,
        "required_capabilities": job.required_capabilities,
        "tools_allowed": job.tools_allowed or None,
        "skill_ids": job.skill_ids,
        "job_type": job.job_type.value,
        "session_target": job.session_target.value,
        "deduplicate": job.deduplicate,
        "skip_if_active": job.skip_if_active,
        "timeout_seconds": job.timeout_seconds,
        "monitor_config": (monitor.monitor_type, monitor.ttl_days, monitor.enabled) if monitor else None,
        "failure_alert": (alert.enabled, alert.after, alert.cooldown_seconds) if alert else None,
        "pre_condition_script": job.pre_condition_script,
        "command": job.command,
    }


@pytest.mark.parametrize("blueprint", BUILTIN_BLUEPRINTS, ids=lambda bp: bp.id)
async def test_agent_tool_creates_the_job_the_blueprint_defines(blueprint: CronBlueprint) -> None:
    values = _slot_values(blueprint)
    fill = fill_blueprint(blueprint.id, values, locale="en")
    assert fill is not None
    store, manager = _manager()
    tool = create_cron_tools(
        manager,
        _USER,
        current_model="model",
        blueprint_filler=lambda bp_id, slot_values, tz: fill_job_spec(bp_id, slot_values, locale="en", tz=tz),
    )[0]

    result = await tool.ainvoke(
        {
            "action": "add",
            "blueprint": blueprint.id,
            "blueprint_values": json.dumps(values),
            "recurring_confirmed": True,
        }
    )

    assert '"status": "success"' in result, result
    (job,) = await store.list_jobs()
    assert _stored(job) == _declared(fill)


@pytest.mark.parametrize("blueprint", BUILTIN_BLUEPRINTS, ids=lambda bp: bp.id)
async def test_blueprint_job_creator_creates_the_job_the_blueprint_defines(blueprint: CronBlueprint) -> None:
    fill = fill_blueprint(blueprint.id, _slot_values(blueprint), locale="en")
    assert fill is not None
    store, manager = _manager()

    await create_blueprint_job(
        EntitlementGuardedCronManager(manager), _USER, to_job_spec(fill), default_timeout_seconds=_DEFAULT_TIMEOUT
    )

    (job,) = await store.list_jobs()
    assert _stored(job) == _declared(fill)


def test_job_spec_mirrors_the_blueprint_fill_field_for_field() -> None:
    assert [f.name for f in fields(BlueprintJobSpec)] == [f.name for f in fields(BlueprintFillResult)]


def test_to_job_spec_carries_every_field_of_a_fully_declared_fill() -> None:
    fill = BlueprintFillResult(
        schedule=BlueprintScheduleResult(kind="cron", expr="30 8 * * 1", tz="Asia/Shanghai"),
        prompt="p",
        name="n",
        required_capabilities=("cap",),
        tools_allowed=("tool",),
        skill_ids=("skill",),
        job_type="router",
        session_target="daily",
        deduplicate=True,
        skip_if_active=True,
        timeout_seconds=45,
        monitor_config=BlueprintMonitorDefaults(monitor_type="hash", ttl_days=7, enabled=False),
        failure_alert=BlueprintFailureAlertDefaults(enabled=False, after=5, cooldown_seconds=60),
        pre_condition_script="echo 1",
        command="cmd",
    )

    assert to_job_spec(fill) == BlueprintJobSpec(
        schedule=Schedule(kind=ScheduleKind.CRON, expr="30 8 * * 1", tz="Asia/Shanghai"),
        prompt="p",
        name="n",
        required_capabilities=("cap",),
        tools_allowed=("tool",),
        skill_ids=("skill",),
        job_type=JobType.ROUTER,
        session_target=SessionTarget.DAILY,
        deduplicate=True,
        skip_if_active=True,
        timeout_seconds=45,
        monitor_config=MonitorConfig(monitor_type="hash", ttl_days=7, enabled=False),
        failure_alert=FailureAlertConfig(enabled=False, after=5, cooldown_seconds=60),
        pre_condition_script="echo 1",
        command="cmd",
    )


def test_to_job_spec_treats_a_blank_pre_condition_script_as_none() -> None:
    fill = BlueprintFillResult(
        schedule=BlueprintScheduleResult(kind="cron", expr="0 6 * * *"), prompt="p", name="n", pre_condition_script=""
    )

    assert to_job_spec(fill).pre_condition_script is None


def test_to_job_spec_keeps_an_interval_schedule() -> None:
    fill = BlueprintFillResult(schedule=BlueprintScheduleResult(kind="interval", interval_ms=600_000), prompt="p", name="n")

    assert to_job_spec(fill).schedule == Schedule(kind=ScheduleKind.INTERVAL, interval_ms=600_000)


def test_to_job_spec_refuses_a_schedule_kind_that_cannot_create_a_job() -> None:
    fill = BlueprintFillResult(schedule=BlueprintScheduleResult(kind="once"), prompt="p", name="n")

    with pytest.raises(ValueError, match="cannot create a job"):
        to_job_spec(fill)


def test_fill_job_spec_returns_none_for_an_unknown_blueprint() -> None:
    assert fill_job_spec("no_such_blueprint", {}, locale="en", tz=None) is None


def test_fill_job_spec_reports_an_invalid_slot_value_as_value_error() -> None:
    with pytest.raises(ValueError, match="missing required value"):
        fill_job_spec("custom_reminder", {}, locale="en", tz=None)


async def test_creator_applies_the_callers_own_name_schedule_agent_roots_and_timeout_fallback() -> None:
    store, manager = _manager()
    spec = BlueprintJobSpec(schedule=Schedule(kind=ScheduleKind.CRON, expr="0 6 * * *"), prompt="p", name="Blueprint name")
    own_schedule = Schedule(kind=ScheduleKind.CRON, expr="15 4 * * *")

    await create_blueprint_job(
        EntitlementGuardedCronManager(manager),
        _USER,
        spec,
        default_timeout_seconds=120,
        name="Own name",
        schedule=own_schedule,
        agent_id="agent-1",
        allowed_roots=("/vault",),
    )

    (job,) = await store.list_jobs()
    assert (job.name, job.schedule.expr, job.agent_id, job.allowed_roots, job.timeout_seconds) == (
        "Own name",
        "15 4 * * *",
        "agent-1",
        ("/vault",),
        120,
    )


async def test_creator_prefers_the_blueprints_declared_timeout_over_the_fallback() -> None:
    store, manager = _manager()
    spec = BlueprintJobSpec(
        schedule=Schedule(kind=ScheduleKind.CRON, expr="0 6 * * *"), prompt="p", name="n", timeout_seconds=900
    )

    await create_blueprint_job(EntitlementGuardedCronManager(manager), _USER, spec, default_timeout_seconds=120)

    (job,) = await store.list_jobs()
    assert job.timeout_seconds == 900
