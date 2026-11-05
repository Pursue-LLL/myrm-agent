"""[INPUT]
- pydantic::BaseModel (POS: schema base)

[OUTPUT]
- MonitorConfigCreate, ActiveHoursCreate, FailureAlertCreate, ScheduleCreate, EventTriggerCreate, SystemEventTriggerCreate, WebhookTriggerCreate, TriggerConfigCreate, ScheduleResponse, MonitorConfigResponse, ActiveHoursResponse, FailureAlertResponse, EventTriggerResponse, SystemEventTriggerResponse, WebhookTriggerResponse, TriggerConfigResponse, EventTriggerDispatchRequest, SystemEventTriggerDispatchRequest

[POS]
Cron API schemas: schedule/monitor/trigger creation requests and responses.
"""

from __future__ import annotations

from datetime import datetime

from myrm_agent_harness.infra.incremental.types import MonitorType, ResetReason
from myrm_agent_harness.toolkits.cron import ScheduleKind
from pydantic import BaseModel, Field, field_validator

from .delivery import DeliveryCreate, DeliveryResponse


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


class EventTriggerDispatchRequest(BaseModel):
    message: str = Field(..., min_length=1, max_length=100_000)
    channel: str = ""


class SystemEventTriggerDispatchRequest(BaseModel):
    source: str = Field(..., min_length=1, max_length=200)
    event_type: str = Field(..., min_length=1, max_length=200)
    payload: dict[str, object] = Field(default_factory=dict)
