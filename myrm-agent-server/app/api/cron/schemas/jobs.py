"""[INPUT]
- pydantic::BaseModel (POS: schema base)

[OUTPUT]
- CronJobCreate, CronJobUpdate, CronJobResponse, CronRunResponse, ChainBreakResponse, IntegrityVerifyResponse, CronJobsListResponse, CronRunsListResponse

[POS]
Cron API schemas: cron job create/update, response and list models.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from myrm_agent_harness.toolkits.cron import JobStatus, JobType, RunStatus, SessionTarget
from pydantic import BaseModel, Field, field_validator

from .delivery import DeliveryCreate, DeliveryResponse
from .triggers import (
    ActiveHoursCreate,
    ActiveHoursResponse,
    FailureAlertCreate,
    FailureAlertResponse,
    MonitorConfigCreate,
    MonitorConfigResponse,
    ScheduleCreate,
    ScheduleResponse,
    TriggerConfigCreate,
    TriggerConfigResponse,
)


class CronJobCreate(BaseModel):
    name: str = Field(..., min_length=1, max_length=200)
    job_type: JobType = JobType.AGENT
    schedule: ScheduleCreate

    prompt: str | None = None
    model: str | None = None
    chat_id: str | None = None
    agent_id: str | None = None
    project_id: str | None = None
    workflow_template_id: str | None = Field(default=None, max_length=64)
    workflow_template_args: dict[str, str] | None = None
    command: str | None = None

    delivery: DeliveryCreate | None = None
    failure_delivery: DeliveryCreate | None = None
    active_hours: ActiveHoursCreate | None = None
    required_capabilities: list[str] | None = None
    tools_allowed: list[str] | None = None
    skill_ids: list[str] | None = None
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
        default=None,
        max_length=10000,
        description="Python script to evaluate before running the job",
    )
    acceptance_criteria: list[dict[str, object]] | None = Field(
        default=None,
        max_length=20,
        description="Structured acceptance criteria for post-run verification",
    )
    override_prerequisite: bool = Field(
        default=False,
        description="Explicit override flag for manual success prerequisite gate",
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
    project_id: str | None = None
    command: str | None = None

    delivery: DeliveryCreate | None = None
    failure_delivery: DeliveryCreate | None = None
    active_hours: ActiveHoursCreate | None = None
    required_capabilities: list[str] | None = None
    tools_allowed: list[str] | None = None
    skill_ids: list[str] | None = None
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
        default=None,
        max_length=10000,
        description="Python script to evaluate before running the job",
    )
    acceptance_criteria: list[dict[str, object]] | None = Field(
        default=None,
        max_length=20,
        description="Structured acceptance criteria for post-run verification",
    )
    workflow_template_id: str | None = Field(default=None, max_length=64)
    workflow_template_args: dict[str, str] | None = None


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
    project_id: str | None = None
    workflow_template_id: str | None = Field(default=None, max_length=64)
    workflow_template_args: dict[str, str] | None = None
    workflow_template_display_name: str | None = None
    command: str | None = None

    delivery: DeliveryResponse = DeliveryResponse()
    failure_delivery: DeliveryResponse | None = None
    failure_alert: FailureAlertResponse | Literal[False] | None = None
    active_hours: ActiveHoursResponse | None = None
    required_capabilities: list[str] = []
    tools_allowed: list[str] = []
    skill_ids: list[str] = []
    allowed_roots: list[str] = []
    triggers: TriggerConfigResponse | None = None
    context_from: list[str] = Field(default_factory=list)
    pre_condition_script: str | None = None
    acceptance_criteria: list[dict[str, object]] | None = None

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
