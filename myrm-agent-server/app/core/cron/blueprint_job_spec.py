"""Turn a filled blueprint into the job it defines.

Every consumer of a blueprint (the agent tool, Second Brain onboarding, read-it-later hygiene)
creates its jobs from the harness ``BlueprintJobSpec`` built here, so a field a blueprint
declares reaches the stored job on every path.

[INPUT]
- app.core.cron.blueprints::BlueprintFillResult, fill_blueprint (POS: blueprint SSOT and its filled result)
- myrm_agent_harness.toolkits.cron::BlueprintJobSpec (POS: complete job definition of a blueprint)
- app.core.cron.adapters.entitlement_guarded_manager::EntitlementGuardedCronManager (POS: cron manager used for creation)

[OUTPUT]
- to_job_spec: Convert a BlueprintFillResult into a BlueprintJobSpec.
- fill_job_spec: Fill a blueprint by id and return its BlueprintJobSpec (the agent tool's blueprint filler).
- create_blueprint_job: Create the job a BlueprintJobSpec defines, with the caller's own name, schedule, agent and roots.

[POS]
Single conversion and creation point from a blueprint fill to a stored cron job.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from myrm_agent_harness.infra.incremental.types import MonitorConfig
from myrm_agent_harness.toolkits.cron import BlueprintJobSpec
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    FailureAlertConfig,
    JobType,
    Schedule,
    ScheduleKind,
    SessionTarget,
)

from app.core.cron.blueprints import (
    BlueprintFillError,
    BlueprintFillResult,
    BlueprintScheduleResult,
    fill_blueprint,
)

if TYPE_CHECKING:
    from app.core.cron.adapters.entitlement_guarded_manager import EntitlementGuardedCronManager


def _to_schedule(result: BlueprintScheduleResult) -> Schedule:
    if result.kind == "cron":
        return Schedule(kind=ScheduleKind.CRON, expr=result.expr, tz=result.tz)
    if result.kind == "interval":
        return Schedule(kind=ScheduleKind.INTERVAL, interval_ms=result.interval_ms)
    raise ValueError(f"A '{result.kind}' blueprint schedule cannot create a job")


def to_job_spec(fill: BlueprintFillResult) -> BlueprintJobSpec:
    """Convert a filled blueprint, field for field, into the harness job spec.

    A blank pre-condition script means "none".
    """
    monitor = fill.monitor_config
    alert = fill.failure_alert
    return BlueprintJobSpec(
        schedule=_to_schedule(fill.schedule),
        prompt=fill.prompt,
        name=fill.name,
        required_capabilities=fill.required_capabilities,
        tools_allowed=fill.tools_allowed,
        skill_ids=fill.skill_ids,
        job_type=JobType(fill.job_type),
        session_target=SessionTarget(fill.session_target),
        deduplicate=fill.deduplicate,
        skip_if_active=fill.skip_if_active,
        timeout_seconds=fill.timeout_seconds,
        monitor_config=(
            MonitorConfig(monitor_type=monitor.monitor_type, ttl_days=monitor.ttl_days, enabled=monitor.enabled)
            if monitor
            else None
        ),
        failure_alert=(
            FailureAlertConfig(enabled=alert.enabled, after=alert.after, cooldown_seconds=alert.cooldown_seconds)
            if alert
            else None
        ),
        pre_condition_script=fill.pre_condition_script or None,
        command=fill.command,
    )


def fill_job_spec(blueprint_id: str, values: dict[str, str], *, locale: str, tz: str | None) -> BlueprintJobSpec | None:
    """Fill a blueprint by id; None when the id is unknown, ValueError when a slot value is invalid."""
    try:
        fill = fill_blueprint(blueprint_id, values, locale=locale, tz=tz)
    except BlueprintFillError as exc:
        raise ValueError(str(exc)) from exc
    return to_job_spec(fill) if fill else None


async def create_blueprint_job(
    manager: EntitlementGuardedCronManager,
    user_id: str,
    spec: BlueprintJobSpec,
    *,
    default_timeout_seconds: int,
    name: str | None = None,
    schedule: Schedule | None = None,
    agent_id: str | None = None,
    allowed_roots: tuple[str, ...] = (),
) -> CronJob:
    """Create the job ``spec`` defines. The caller supplies what a blueprint cannot: owner binding and roots.

    ``name`` and ``schedule`` replace the blueprint's when the caller keeps its own (an existing job being
    rebuilt); ``default_timeout_seconds`` applies when the blueprint declares no timeout.
    """
    return await manager.create_job(
        user_id,
        name or spec.name,
        spec.job_type,
        schedule or spec.schedule,
        prompt=spec.prompt,
        command=spec.command,
        agent_id=agent_id,
        required_capabilities=spec.required_capabilities,
        tools_allowed=spec.tools_allowed,
        skill_ids=spec.skill_ids,
        allowed_roots=allowed_roots,
        session_target=spec.session_target,
        deduplicate=spec.deduplicate,
        skip_if_active=spec.skip_if_active,
        timeout_seconds=spec.timeout_seconds or default_timeout_seconds,
        monitor_config=spec.monitor_config,
        failure_alert=spec.failure_alert,
        pre_condition_script=spec.pre_condition_script,
    )
