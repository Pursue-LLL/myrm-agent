"""Pydantic schemas for the cron API.

1. 本文件的 INPUT/OUTPUT/POS 注释
2. 所属文件夹的 _ARCH.md

[INPUT]
- core.cron.types::JobStatus, JobType, RunStatus, ScheduleKind (POS: 领域类型定义层)
- myrm_agent_harness.infra.incremental.types::MonitorType, ResetReason (POS: 增量监控 Literal 类型)

[OUTPUT]
- MonitorConfigCreate, MonitorConfigResponse: 增量监控配置模型
- ScheduleCreate, CronJobCreate, CronJobUpdate: 请求模型
- EventTriggerDispatchRequest, SystemEventTriggerDispatchRequest: Trigger dispatch 请求模型
- ScheduleResponse, CronJobResponse, CronRunResponse: 响应模型
- CronJobsListResponse, CronRunsListResponse: 分页列表响应模型
- HeartbeatEnableRequest, HeartbeatStatusResponse: 心跳 API 模型（支持 interval/cron 调度）

[POS]
定时任务 API 数据模型。定义 HTTP 请求/响应的 Pydantic schema，
提供字段校验（name 长度、retries 范围、monitor_type 枚举等）。
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from myrm_agent_harness.infra.incremental.types import MonitorType, ResetReason
from myrm_agent_harness.toolkits.cron import JobStatus, JobType, RunStatus, ScheduleKind, SessionTarget
from pydantic import BaseModel, Field, field_validator, model_validator

# ---------------------------------------------------------------------------
# Request schemas
# ---------------------------------------------------------------------------


class DeliveryCreate(BaseModel):
    channel: str = "chat"
    target: str | None = None

    @model_validator(mode="after")
    def validate_webhook_url(self) -> "DeliveryCreate":
        if self.channel == "webhook":
            url = (self.target or "").strip()
            if not url:
                raise ValueError("Webhook channel requires a target URL")
            if not url.startswith(("http://", "https://")):
                raise ValueError("Webhook URL must start with http:// or https://")
            self.target = url
        return self


class MonitorConfigCreate(BaseModel):
    monitor_type: MonitorType = "set"
    ttl_days: int = Field(default=30, ge=1, le=365)
    enabled: bool = True


class ActiveHoursCreate(BaseModel):
    start: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    end: str = Field(..., pattern=r"^([01]\d|2[0-3]):[0-5]\d$")
    tz: str = "UTC"


class FailureAlertCreate(BaseModel):
    enabled: bool = True
    after: int = Field(default=3, ge=1, le=100)
    cooldown_seconds: int = Field(default=300, ge=0, le=86400)
    delivery: DeliveryCreate | None = None


class ScheduleCreate(BaseModel):
    kind: ScheduleKind
    expr: str | None = None
    tz: str | None = None
    interval_ms: int | None = None
    run_at: datetime | None = None
    stagger_ms: int | None = Field(default=None, ge=0, le=3_600_000)


class EventTriggerCreate(BaseModel):
    pattern: str = Field(..., min_length=1, max_length=500)
    channel: str | None = None

    @field_validator("pattern")
    @classmethod
    def validate_pattern(cls, v: str) -> str:
        import re

        try:
            re.compile(v)
        except re.error as exc:
            raise ValueError(f"Invalid regex pattern: {exc}") from exc
        return v


class SystemEventTriggerCreate(BaseModel):
    source: str = Field(..., min_length=1, max_length=100)
    event_type: str = Field(..., min_length=1, max_length=100)
    filters: dict[str, str] = Field(default_factory=dict)


class WebhookTriggerCreate(BaseModel):
    """Path and secret are auto-generated if omitted."""

    pass


class TriggerConfigCreate(BaseModel):
    webhooks: list[WebhookTriggerCreate] = Field(default_factory=list, max_length=5)
    events: list[EventTriggerCreate] = Field(default_factory=list, max_length=10)
    system_events: list[SystemEventTriggerCreate] = Field(default_factory=list, max_length=10)


class CronJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    job_type: JobType = JobType.AGENT
    schedule: ScheduleCreate

    prompt: str | None = None
    model: str | None = None
    chat_id: str | None = None
    agent_id: str | None = None
    command: str | None = None

    delivery: DeliveryCreate | None = None
    failure_delivery: DeliveryCreate | None = None
    active_hours: ActiveHoursCreate | None = None
    required_capabilities: list[str] | None = None
    allowed_roots: list[str] | None = None
    triggers: TriggerConfigCreate | None = None

    max_retries: int = Field(default=2, ge=0, le=10)
    retry_backoff_ms: int = Field(default=30000, ge=1000, le=3_600_000)
    timeout_seconds: int = Field(default=300, ge=10, le=3600)
    misfire_grace_seconds: int = Field(default=300, ge=0, le=86400)
    cooldown_seconds: int = Field(default=0, ge=0, le=86400)
    max_fires: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    session_target: SessionTarget = SessionTarget.ISOLATED
    delete_after_run: bool | None = None
    run_retention_days: int = Field(default=30, ge=1, le=365)
    deduplicate: bool = False
    skip_if_active: bool = False
    failure_alert: FailureAlertCreate | Literal[False] | None = None
    monitor_config: MonitorConfigCreate | None = None
    context_from: list[str] = Field(default_factory=list, max_length=10)
    pre_condition_script: str | None = Field(
        default=None, max_length=10000, description="Python script to evaluate before running the job"
    )

    @field_validator("name", mode="before")
    @classmethod
    def strip_name(cls, v: str) -> str:
        stripped = v.strip() if isinstance(v, str) else v
        if isinstance(stripped, str) and len(stripped) == 0:
            raise ValueError("Name must not be blank")
        if isinstance(stripped, str) and stripped.startswith("__"):
            raise ValueError("Names starting with '__' are reserved for system use")
        return stripped


class CronJobUpdate(BaseModel):
    name: str | None = None
    status: JobStatus | None = None
    schedule: ScheduleCreate | None = None

    prompt: str | None = None
    model: str | None = None
    agent_id: str | None = None
    command: str | None = None

    delivery: DeliveryCreate | None = None
    failure_delivery: DeliveryCreate | None = None
    active_hours: ActiveHoursCreate | None = None
    required_capabilities: list[str] | None = None
    allowed_roots: list[str] | None = None
    triggers: TriggerConfigCreate | None = None

    max_retries: int | None = Field(default=None, ge=0, le=10)
    retry_backoff_ms: int | None = Field(default=None, ge=1000, le=3_600_000)
    timeout_seconds: int | None = Field(default=None, ge=10, le=3600)
    misfire_grace_seconds: int | None = Field(default=None, ge=0, le=86400)
    cooldown_seconds: int | None = Field(default=None, ge=0, le=86400)
    max_fires: int | None = Field(default=None, ge=1)
    expires_at: datetime | None = None
    session_target: SessionTarget | None = None
    chat_id: str | None = None
    delete_after_run: bool | None = None
    run_retention_days: int | None = Field(default=None, ge=1, le=365)
    deduplicate: bool | None = None
    skip_if_active: bool | None = None
    failure_alert: FailureAlertCreate | Literal[False] | None = None
    monitor_config: MonitorConfigCreate | None = None
    context_from: list[str] | None = None
    pre_condition_script: str | None = Field(
        default=None, max_length=10000, description="Python script to evaluate before running the job"
    )


# ---------------------------------------------------------------------------
# Response schemas
# ---------------------------------------------------------------------------


class DeliveryResponse(BaseModel):
    channel: str = "chat"
    target: str | None = None
    secret: str | None = None


class ScheduleResponse(BaseModel):
    kind: ScheduleKind
    expr: str | None = None
    tz: str | None = None
    interval_ms: int | None = None
    run_at: datetime | None = None
    stagger_ms: int | None = None


class MonitorConfigResponse(BaseModel):
    monitor_type: MonitorType = "set"
    ttl_days: int = 30
    enabled: bool = True
    last_reset_at: datetime | None = None
    last_reset_reason: ResetReason | None = None


class ActiveHoursResponse(BaseModel):
    start: str
    end: str
    tz: str = "UTC"


class FailureAlertResponse(BaseModel):
    enabled: bool = True
    after: int = 3
    cooldown_seconds: int = 300
    delivery: DeliveryResponse | None = None


class EventTriggerResponse(BaseModel):
    pattern: str
    channel: str | None = None


class SystemEventTriggerResponse(BaseModel):
    source: str
    event_type: str
    filters: dict[str, str] = Field(default_factory=dict)


class WebhookTriggerResponse(BaseModel):
    path: str | None = None
    secret: str | None = None


class TriggerConfigResponse(BaseModel):
    webhooks: list[WebhookTriggerResponse] = Field(default_factory=list)
    events: list[EventTriggerResponse] = Field(default_factory=list)
    system_events: list[SystemEventTriggerResponse] = Field(default_factory=list)


class CronJobResponse(BaseModel):
    id: str
    user_id: str
    name: str
    job_type: JobType
    status: JobStatus
    schedule: ScheduleResponse

    prompt: str | None = None
    model: str | None = None
    chat_id: str | None = None
    agent_id: str | None = None
    command: str | None = None

    delivery: DeliveryResponse = DeliveryResponse()
    failure_delivery: DeliveryResponse | None = None
    failure_alert: FailureAlertResponse | Literal[False] | None = None
    active_hours: ActiveHoursResponse | None = None
    required_capabilities: list[str] = []
    allowed_roots: list[str] = []
    triggers: TriggerConfigResponse | None = None
    context_from: list[str] = Field(default_factory=list)
    pre_condition_script: str | None = None

    max_retries: int
    retry_backoff_ms: int
    timeout_seconds: int
    misfire_grace_seconds: int
    cooldown_seconds: int = 0
    max_fires: int | None = None
    expires_at: datetime | None = None
    fire_count: int = 0
    session_target: SessionTarget = SessionTarget.ISOLATED
    delete_after_run: bool
    run_retention_days: int = 30
    deduplicate: bool = False
    skip_if_active: bool = False
    monitor_config: MonitorConfigResponse | None = None

    next_run_at: datetime | None = None
    last_run_at: datetime | None = None
    last_status: RunStatus | None = None
    last_error: str | None = None
    consecutive_failures: int
    last_failure_alert_at: datetime | None = None

    created_at: datetime
    updated_at: datetime


class CronRunResponse(BaseModel):
    id: str
    job_id: str
    started_at: datetime
    finished_at: datetime
    duration_ms: int
    status: RunStatus
    output: str | None = None
    error: str | None = None
    model: str | None = None
    usage_input_tokens: int | None = None
    usage_output_tokens: int | None = None
    usage_total_tokens: int | None = None
    trigger_source: str | None = None
    delivery_status: str | None = None
    delivery_error: str | None = None
    metadata: dict[str, object] | None = None
    integrity_hash: str | None = None
    job_name: str | None = None


class ChainBreakResponse(BaseModel):
    run_id: str
    kind: str
    expected: str
    actual: str


class IntegrityVerifyResponse(BaseModel):
    job_id: str
    total_runs: int
    verified_runs: int
    intact: bool
    breaks: list[ChainBreakResponse]


class CronJobsListResponse(BaseModel):
    items: list[CronJobResponse]
    total: int
    offset: int
    limit: int
    has_more: bool


class CronRunsListResponse(BaseModel):
    items: list[CronRunResponse]
    total: int
    offset: int
    limit: int
    has_more: bool


# ---------------------------------------------------------------------------
# Usage stats schemas
# ---------------------------------------------------------------------------


class UsageSummary(BaseModel):
    total_runs: int
    success_runs: int
    total_input_tokens: int
    total_output_tokens: int
    total_tokens: int
    avg_tokens_per_run: int


class UsageByDay(BaseModel):
    date: str
    input_tokens: int
    output_tokens: int
    total_tokens: int
    runs: int


class UsageByJob(BaseModel):
    job_id: str
    job_name: str
    total_tokens: int
    runs: int


class UsageByModel(BaseModel):
    model: str
    total_tokens: int
    runs: int


class UsageStatsResponse(BaseModel):
    summary: UsageSummary
    by_day: list[UsageByDay]
    by_job: list[UsageByJob]
    by_model: list[UsageByModel]


# ---------------------------------------------------------------------------
# Trigger dispatch schemas
# ---------------------------------------------------------------------------


class EventTriggerDispatchRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=100_000)
    channel: str = ""


class SystemEventTriggerDispatchRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=200)
    event_type: str = Field(..., min_length=1, max_length=200)
    payload: dict[str, object] = Field(default_factory=dict)


# ---------------------------------------------------------------------------
# Heartbeat schemas
# ---------------------------------------------------------------------------


class HeartbeatEnableRequest(BaseModel):
    interval_ms: int = Field(default=1_800_000, ge=300_000, le=86_400_000)
    schedule_kind: str | None = Field(
        default=None,
        description="'interval' (default) or 'cron' for time-of-day scheduling",
    )
    cron_expr: str | None = Field(
        default=None,
        description="Cron expression when schedule_kind='cron', e.g. '0 9 * * *'",
    )
    timezone: str | None = Field(
        default=None,
        description="IANA timezone for cron schedule, e.g. 'Asia/Shanghai'",
    )
    prompt: str | None = None
    model: str | None = None


class HeartbeatStatusResponse(BaseModel):
    enabled: bool
    interval_ms: int | None = None
    schedule_kind: str | None = None
    cron_expr: str | None = None
    timezone: str | None = None
    schedule_description: str | None = None
    prompt: str | None = None
    model: str | None = None
    last_run_at: datetime | None = None
    last_status: str | None = None
    next_run_at: datetime | None = None
    fire_count: int = 0
