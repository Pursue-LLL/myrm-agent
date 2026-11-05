"""[INPUT]
- pydantic::BaseModel (POS: schema base)

[OUTPUT]
- HeartbeatEnableRequest, HeartbeatStatusResponse, PrerequisiteCheckRequest, PrerequisiteCheckResponse, ConnectorHealthResponse, ConnectorsHealthListResponse

[POS]
Cron API schemas: heartbeat, prerequisite checks and connector health.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


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
    agent_id: str | None = None


class HeartbeatStatusResponse(BaseModel):
    enabled: bool
    interval_ms: int | None = None
    schedule_kind: str | None = None
    cron_expr: str | None = None
    timezone: str | None = None
    schedule_description: str | None = None
    prompt: str | None = None
    model: str | None = None
    agent_id: str | None = None
    last_run_at: datetime | None = None
    last_status: str | None = None
    next_run_at: datetime | None = None
    fire_count: int = 0


class PrerequisiteCheckRequest(BaseModel):
    prompt: str | None = None
    agent_id: str | None = None
    workflow_template_id: str | None = None
    command: str | None = None
    tools_allowed: list[str] | None = None
    chat_id: str | None = None
    threshold: int = 2


class PrerequisiteCheckResponse(BaseModel):
    fingerprint: str
    manual_success_count: int
    threshold: int
    is_satisfied: bool
    chat_verified_count: int
    kanban_verified_count: int
    override_allowed: bool = True


class ConnectorHealthResponse(BaseModel):
    target: str
    channel: str
    status: str
    total_deliveries: int
    failed_deliveries: int
    consecutive_failures: int
    last_status_code: int | None = None
    last_error_category: str | None = None
    last_error_message: str | None = None
    last_delivery_at: datetime | None = None
    last_failed_at: datetime | None = None
    fix_suggestion: str | None = None
    bound_job_ids: list[str] = Field(default_factory=list)


class ConnectorsHealthListResponse(BaseModel):
    items: list[ConnectorHealthResponse]
    total: int
    degraded_count: int
    down_count: int
