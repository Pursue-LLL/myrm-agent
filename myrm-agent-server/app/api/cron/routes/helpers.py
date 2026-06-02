from __future__ import annotations

from typing import TYPE_CHECKING, Literal

from myrm_agent_harness.infra.incremental.types import MonitorConfig, MonitorState
from myrm_agent_harness.toolkits.cron import (
    DeliveryConfig,
    FailureAlertConfig,
    Schedule,
    ScheduleKind,
)
from myrm_agent_harness.toolkits.cron.triggers import (
    EventTrigger,
    SystemEventTrigger,
    TriggerConfig,
    WebhookTrigger,
)
from myrm_agent_harness.toolkits.cron.types import ActiveHours, CronJob, CronRunRecord

from app.api.cron.schemas import (
    ActiveHoursCreate,
    ActiveHoursResponse,
    CronJobResponse,
    CronRunResponse,
    DeliveryCreate,
    DeliveryResponse,
    EventTriggerResponse,
    FailureAlertCreate,
    FailureAlertResponse,
    MonitorConfigCreate,
    MonitorConfigResponse,
    ScheduleCreate,
    ScheduleResponse,
    SystemEventTriggerResponse,
    TriggerConfigCreate,
    TriggerConfigResponse,
    WebhookTriggerResponse,
)

if TYPE_CHECKING:
    from myrm_agent_harness.toolkits.cron.engine.scheduler import CronScheduler
    from myrm_agent_harness.toolkits.cron.manager import CronManager

def _get_manager() -> CronManager:
    from app.core.cron.adapters.setup import get_cron_manager

    return get_cron_manager()

def _to_response(job: CronJob, monitor_state: MonitorState | None = None) -> CronJobResponse:
    return CronJobResponse(
        id=job.id,
        user_id="default",
        name=job.name,
        job_type=job.job_type,
        status=job.status,
        schedule=ScheduleResponse(
            kind=job.schedule.kind,
            expr=job.schedule.expr,
            tz=job.schedule.tz,
            interval_ms=job.schedule.interval_ms,
            run_at=job.schedule.run_at,
            stagger_ms=job.schedule.stagger_ms,
        ),
        prompt=job.prompt,
        model=job.model,
        chat_id=job.chat_id,
        agent_id=job.agent_id,
        command=job.command,
        delivery=_delivery_to_response(job.delivery),
        failure_delivery=_delivery_to_response(job.failure_delivery) if job.failure_delivery else None,
        failure_alert=_failure_alert_to_response(job.failure_alert),
        active_hours=_active_hours_to_response(job.active_hours),
        required_capabilities=list(job.required_capabilities) if job.required_capabilities else [],
        allowed_roots=list(job.allowed_roots) if job.allowed_roots else [],
        triggers=_trigger_config_to_response(job.triggers),
        context_from=list(job.context_from) if job.context_from else [],
        pre_condition_script=job.pre_condition_script,
        max_retries=job.max_retries,
        retry_backoff_ms=job.retry_backoff_ms,
        timeout_seconds=job.timeout_seconds,
        misfire_grace_seconds=job.misfire_grace_seconds,
        cooldown_seconds=job.cooldown_seconds,
        max_fires=job.max_fires,
        expires_at=job.expires_at,
        fire_count=job.fire_count,
        session_target=job.session_target,
        delete_after_run=job.delete_after_run,
        run_retention_days=job.run_retention_days,
        deduplicate=job.deduplicate,
        monitor_config=_monitor_config_to_response(job.monitor_config, monitor_state),
        next_run_at=job.next_run_at,
        last_run_at=job.last_run_at,
        last_status=job.last_status,
        last_error=job.last_error,
        consecutive_failures=job.consecutive_failures,
        last_failure_alert_at=job.last_failure_alert_at,
        created_at=job.created_at,
        updated_at=job.updated_at,
    )

def _active_hours_to_response(ah: ActiveHours | None) -> ActiveHoursResponse | None:
    if ah is None:
        return None
    return ActiveHoursResponse(start=ah.start, end=ah.end, tz=ah.tz)

def _active_hours_from_request(ah: ActiveHoursCreate | None) -> ActiveHours | None:
    if ah is None:
        return None
    return ActiveHours(start=ah.start, end=ah.end, tz=ah.tz)

def _monitor_config_to_response(mc: MonitorConfig | None, state: MonitorState | None = None) -> MonitorConfigResponse | None:
    if mc is None:
        return None

    return MonitorConfigResponse(
        monitor_type=mc.monitor_type,
        ttl_days=mc.ttl_days,
        enabled=mc.enabled,
        last_reset_at=state.last_reset_at if state else None,
        last_reset_reason=state.last_reset_reason if state else None,
    )

def _monitor_config_from_request(mc: MonitorConfigCreate | None) -> MonitorConfig | None:
    if mc is None:
        return None

    return MonitorConfig(
        monitor_type=mc.monitor_type,
        ttl_days=mc.ttl_days,
        enabled=mc.enabled,
    )

def _delivery_to_response(dc: DeliveryConfig) -> DeliveryResponse:
    return DeliveryResponse(channel=dc.channel, target=dc.target, secret=dc.secret)

def _delivery_from_request(d: DeliveryCreate | None) -> DeliveryConfig:
    if not d:
        return DeliveryConfig()
    if d.channel not in ("chat", "silent", "none") and not d.target:
        raise ValueError(f'Delivery target is required for channel "{d.channel}"')
    secret = None
    if d.channel == "webhook":
        import secrets as _secrets

        secret = _secrets.token_hex(32)
    return DeliveryConfig(channel=d.channel, target=d.target, secret=secret)

def _failure_alert_to_response(
    fa: FailureAlertConfig | bool | None,
) -> FailureAlertResponse | Literal[False] | None:
    if fa is None:
        return None
    if isinstance(fa, bool):
        return False
    return FailureAlertResponse(
        enabled=fa.enabled,
        after=fa.after,
        cooldown_seconds=fa.cooldown_seconds,
        delivery=_delivery_to_response(fa.delivery) if fa.delivery else None,
    )

def _failure_alert_from_request(
    fa: FailureAlertCreate | bool | None,
) -> FailureAlertConfig | Literal[False] | None:
    if fa is None:
        return None
    if isinstance(fa, bool):
        return False
    return FailureAlertConfig(
        enabled=fa.enabled,
        after=fa.after,
        cooldown_seconds=fa.cooldown_seconds,
        delivery=_delivery_from_request(fa.delivery) if fa.delivery else None,
    )

def _trigger_config_to_response(tc: TriggerConfig | None) -> TriggerConfigResponse | None:
    if tc is None:
        return None
    return TriggerConfigResponse(
        webhooks=[WebhookTriggerResponse(path=w.path, secret=w.secret) for w in tc.webhooks],
        events=[EventTriggerResponse(pattern=e.pattern, channel=e.channel) for e in tc.events],
        system_events=[
            SystemEventTriggerResponse(source=s.source, event_type=s.event_type, filters=s.filters) for s in tc.system_events
        ],
    )

def _trigger_config_from_request(tc: TriggerConfigCreate | None) -> TriggerConfig | None:
    if tc is None:
        return None
    webhooks = tuple(WebhookTrigger() for _ in tc.webhooks)
    events = tuple(EventTrigger(pattern=e.pattern, channel=e.channel) for e in tc.events)
    system_events = tuple(
        SystemEventTrigger(source=s.source, event_type=s.event_type, filters=s.filters) for s in tc.system_events
    )
    if not webhooks and not events and not system_events:
        return None
    return TriggerConfig(webhooks=webhooks, events=events, system_events=system_events)

def _build_schedule(s: ScheduleCreate) -> Schedule:
    return Schedule(
        kind=ScheduleKind(s.kind),
        expr=s.expr,
        tz=s.tz,
        interval_ms=s.interval_ms,
        run_at=s.run_at,
        stagger_ms=s.stagger_ms,
    )

def _run_to_response(r: CronRunRecord, *, job_name: str | None = None) -> CronRunResponse:
    return CronRunResponse(
        id=r.id,
        job_id=r.job_id,
        started_at=r.started_at,
        finished_at=r.finished_at,
        duration_ms=r.duration_ms,
        status=r.status,
        output=r.output,
        error=r.error,
        model=r.model,
        usage_input_tokens=r.usage_input_tokens,
        usage_output_tokens=r.usage_output_tokens,
        usage_total_tokens=r.usage_total_tokens,
        trigger_source=r.trigger_source,
        delivery_status=r.delivery_status,
        delivery_error=r.delivery_error,
        metadata=r.metadata,
        integrity_hash=r.integrity_hash or None,
        job_name=job_name,
    )

def _get_scheduler() -> "CronScheduler":
    from app.core.cron.adapters.setup import get_cron_scheduler

    return get_cron_scheduler()

