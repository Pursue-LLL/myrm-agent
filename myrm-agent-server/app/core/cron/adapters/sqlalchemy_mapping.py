"""ORM <-> Domain mapping for cron models.

Bidirectional conversion between SQLAlchemy ORM models and
framework domain objects (CronJob, CronRunRecord, MonitorState).
"""

from __future__ import annotations

from datetime import timezone
from typing import cast

from myrm_agent_harness.infra.incremental.types import MonitorConfig, MonitorState, MonitorType, ResetReason
from myrm_agent_harness.toolkits.cron.triggers import (
    dict_to_trigger_config,
    trigger_config_to_dict,
)
from myrm_agent_harness.toolkits.cron.types import (
    CronJob,
    CronRunRecord,
    DeliveryConfig,
    DeliveryStatus,
    JobStatus,
    JobType,
    RunStatus,
    SessionTarget,
    active_hours_to_dict,
    delivery_to_dict,
    dict_to_active_hours,
    dict_to_delivery,
    dict_to_failure_alert,
    dict_to_schedule,
    failure_alert_to_dict,
    schedule_to_dict,
)

from app.database.models import CronJobModel, CronRunModel, MonitorStateModel


def run_to_domain(r: CronRunModel) -> CronRunRecord:
    """Map an ORM CronRunModel to a domain CronRunRecord."""
    return CronRunRecord(
        id=r.id,
        job_id=r.job_id,
        started_at=r.started_at,
        finished_at=r.finished_at,
        duration_ms=r.duration_ms,
        status=RunStatus(r.status),
        output=r.output,
        error=r.error,
        model=r.model,
        usage_input_tokens=r.usage_input_tokens,
        usage_output_tokens=r.usage_output_tokens,
        usage_total_tokens=r.usage_total_tokens,
        trigger_source=getattr(r, "trigger_source", None),
        delivery_status=DeliveryStatus(r.delivery_status) if r.delivery_status else None,
        delivery_error=r.delivery_error,
        metadata=r.metadata_json,
        integrity_hash=r.integrity_hash or "",
        prev_hash=r.prev_hash or "",
    )


def _int_from_cfg(val: object, default: int) -> int:
    if isinstance(val, int):
        return val
    if isinstance(val, float):
        return int(val)
    if isinstance(val, str):
        try:
            return int(val, 10)
        except ValueError:
            return default
    return default


def dict_to_monitor_config(d: dict[str, object] | None) -> MonitorConfig | None:
    if not d:
        return None
    return MonitorConfig(
        monitor_type=cast(MonitorType, d.get("monitor_type", "set")),
        ttl_days=_int_from_cfg(d.get("ttl_days", 30), 30),
        enabled=bool(d.get("enabled", True)),
    )


def monitor_config_to_dict(cfg: MonitorConfig | None) -> dict[str, object] | None:
    if not cfg:
        return None
    return {
        "monitor_type": cfg.monitor_type,
        "ttl_days": cfg.ttl_days,
        "enabled": cfg.enabled,
    }


def job_to_domain(m: CronJobModel) -> CronJob:
    """Map an ORM model to a domain CronJob."""
    schedule = dict_to_schedule(m.schedule)
    delivery = dict_to_delivery(getattr(m, "delivery", None)) or DeliveryConfig()
    failure_delivery = dict_to_delivery(getattr(m, "failure_delivery", None))
    active_hours = dict_to_active_hours(getattr(m, "active_hours", None))
    monitor_config = dict_to_monitor_config(getattr(m, "monitor_config", None))
    triggers = dict_to_trigger_config(getattr(m, "triggers", None))
    failure_alert = dict_to_failure_alert(getattr(m, "failure_alert", None))

    raw_session = getattr(m, "session_target", "isolated") or "isolated"
    session_target = SessionTarget(raw_session) if raw_session in SessionTarget.__members__.values() else SessionTarget.ISOLATED

    return CronJob(
        id=m.id,
        user_id=str(getattr(m, "user_id", "default") or "default"),
        name=m.name,
        job_type=JobType(m.job_type),
        schedule=schedule,
        status=JobStatus(m.status),
        prompt=m.prompt,
        model=m.model,
        chat_id=m.chat_id,
        agent_id=getattr(m, "agent_id", None),
        command=m.command,
        delivery=delivery,
        failure_delivery=failure_delivery,
        failure_alert=failure_alert,
        active_hours=active_hours,
        max_retries=m.max_retries,
        retry_backoff_ms=m.retry_backoff_ms,
        timeout_seconds=getattr(m, "timeout_seconds", 300) or 300,
        misfire_grace_seconds=getattr(m, "misfire_grace_seconds", 300) or 300,
        cooldown_seconds=getattr(m, "cooldown_seconds", 0) or 0,
        max_fires=getattr(m, "max_fires", None),
        expires_at=getattr(m, "expires_at", None),
        fire_count=getattr(m, "fire_count", 0) or 0,
        session_target=session_target,
        required_capabilities=tuple(m.required_capabilities) if m.required_capabilities else (),
        allowed_roots=tuple(m.allowed_roots) if m.allowed_roots else (),
        delete_after_run=m.delete_after_run,
        run_retention_days=getattr(m, "run_retention_days", 30) or 30,
        deduplicate=getattr(m, "deduplicate", False) or False,
        skip_if_active=getattr(m, "skip_if_active", False) or False,
        last_output_hash=getattr(m, "last_output_hash", None),
        monitor_config=monitor_config,
        context_from=tuple(getattr(m, "context_from", None) or []),
        pre_condition_script=getattr(m, "pre_condition_script", None),
        triggers=triggers,
        next_run_at=m.next_run_at,
        last_run_at=m.last_run_at,
        last_status=RunStatus(m.last_status) if m.last_status else None,
        last_error=m.last_error,
        consecutive_failures=m.consecutive_failures,
        last_failure_alert_at=m.last_failure_alert_at,
        created_at=m.created_at,
        updated_at=m.updated_at,
    )


def job_to_model(job: CronJob) -> CronJobModel:
    """Map a domain CronJob to an ORM model for insertion."""
    return CronJobModel(
        id=job.id,
        name=job.name,
        job_type=job.job_type,
        status=job.status,
        schedule=schedule_to_dict(job.schedule),
        prompt=job.prompt,
        model=job.model,
        chat_id=job.chat_id,
        agent_id=job.agent_id,
        command=job.command,
        delivery=delivery_to_dict(job.delivery) or {"channel": "chat"},
        failure_delivery=delivery_to_dict(job.failure_delivery),
        failure_alert=failure_alert_to_dict(job.failure_alert),
        active_hours=active_hours_to_dict(job.active_hours),
        required_capabilities=list(job.required_capabilities) if job.required_capabilities else None,
        allowed_roots=list(job.allowed_roots) if job.allowed_roots else None,
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
        skip_if_active=job.skip_if_active,
        last_output_hash=job.last_output_hash,
        context_from=list(job.context_from) if job.context_from else None,
        pre_condition_script=job.pre_condition_script,
        monitor_config=monitor_config_to_dict(job.monitor_config),
        triggers=trigger_config_to_dict(job.triggers),
        next_run_at=job.next_run_at,
        last_run_at=job.last_run_at,
        last_status=job.last_status,
        last_error=job.last_error,
        consecutive_failures=job.consecutive_failures,
        last_failure_alert_at=job.last_failure_alert_at,
    )


def apply_job_to_model(m: CronJobModel, job: CronJob) -> None:
    """Apply domain CronJob fields to an existing ORM model (update)."""
    m.name = job.name
    m.job_type = job.job_type
    m.status = job.status
    m.schedule = schedule_to_dict(job.schedule)
    m.prompt = job.prompt
    m.model = job.model
    m.chat_id = job.chat_id
    m.agent_id = job.agent_id
    m.command = job.command
    m.delivery = delivery_to_dict(job.delivery) or {"channel": "chat"}
    m.failure_delivery = delivery_to_dict(job.failure_delivery)
    m.failure_alert = failure_alert_to_dict(job.failure_alert)
    m.active_hours = active_hours_to_dict(job.active_hours)
    m.required_capabilities = list(job.required_capabilities) if job.required_capabilities else None
    m.allowed_roots = list(job.allowed_roots) if job.allowed_roots else None
    m.max_retries = job.max_retries
    m.retry_backoff_ms = job.retry_backoff_ms
    m.timeout_seconds = job.timeout_seconds
    m.misfire_grace_seconds = job.misfire_grace_seconds
    m.cooldown_seconds = job.cooldown_seconds
    m.max_fires = job.max_fires
    m.expires_at = job.expires_at
    m.fire_count = job.fire_count
    m.session_target = job.session_target
    m.delete_after_run = job.delete_after_run
    m.run_retention_days = job.run_retention_days
    m.deduplicate = job.deduplicate
    m.skip_if_active = job.skip_if_active
    m.last_output_hash = job.last_output_hash
    m.context_from = list(job.context_from) if job.context_from else None
    m.monitor_config = monitor_config_to_dict(job.monitor_config)
    m.triggers = trigger_config_to_dict(job.triggers)
    m.next_run_at = job.next_run_at
    m.last_run_at = job.last_run_at
    m.last_status = job.last_status
    m.last_error = job.last_error
    m.consecutive_failures = job.consecutive_failures
    m.last_failure_alert_at = job.last_failure_alert_at
    m.updated_at = job.updated_at


def row_to_monitor_state(row: MonitorStateModel) -> MonitorState:
    """Convert a MonitorStateModel ORM row to a MonitorState domain object."""
    updated_at = row.updated_at
    if updated_at.tzinfo is None:
        updated_at = updated_at.replace(tzinfo=timezone.utc)

    last_failure_at = row.last_failure_at
    if last_failure_at and last_failure_at.tzinfo is None:
        last_failure_at = last_failure_at.replace(tzinfo=timezone.utc)

    last_reset_at = row.last_reset_at
    if last_reset_at and last_reset_at.tzinfo is None:
        last_reset_at = last_reset_at.replace(tzinfo=timezone.utc)

    return MonitorState(
        job_id=row.job_id,
        monitor_type=cast(MonitorType, row.monitor_type),
        data=row.data,
        updated_at=updated_at,
        failure_count=row.failure_count,
        last_failure_at=last_failure_at,
        ttl_days=row.ttl_days,
        last_reset_at=last_reset_at,
        last_reset_reason=cast(ResetReason | None, row.last_reset_reason),
    )
