"""Pydantic V2 schemas for Adaptive Wakeup Driver (Item 29).

[INPUT]
- None (root DTOs)

[OUTPUT]
- WakeupBudgetStatusResponse, TriggerAdaptiveWakeupRequest, AdaptiveRoutingResponse, InjectedEventItem, InjectedEventsResponse

[POS]
- Defines API contracts for session-level autonomous wakeup budget monitoring,
  host activity state coordination, and settlement routing inspection.
"""

from __future__ import annotations

import enum
from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field


class WakeupChannelEnum(enum.StrEnum):
    """Channel selected by the adaptive wakeup driver."""

    INJECT = "inject"
    FOLLOWUP = "followup"
    SUPPRESS = "suppress"
    DEGRADE = "degrade"


class HostActivityStateEnum(enum.StrEnum):
    """Host execution activity status."""

    IDLE = "idle"
    BUSY = "busy"
    STOPPED = "stopped"


class WakeupSourceTypeEnum(enum.StrEnum):
    """Type of asynchronous settlement generator."""

    SUBAGENT = "subagent"
    BACKGROUND_JOB = "background_job"


class WakeupBudgetStatusResponse(BaseModel):
    """Response containing session wakeup budget and host activity."""

    model_config = ConfigDict(frozen=True)

    session_id: str = Field(..., description="Unique chat session identifier")
    consecutive_wakes: int = Field(..., description="Current count of consecutive autonomous wakes")
    max_consecutive_wakes: int = Field(..., description="Maximum allowed consecutive autonomous wakes")
    budget_remaining: int = Field(..., description="Remaining wake attempts before degradation")
    is_exhausted: bool = Field(..., description="Whether consecutive wake budget is exhausted")
    is_user_stopped: bool = False
    host_activity: HostActivityStateEnum = HostActivityStateEnum.IDLE
    last_wake_time: datetime | None = None
    last_human_reset_time: datetime | None = None


class TriggerAdaptiveWakeupRequest(BaseModel):
    """Request payload to manually or programmatically test settlement routing."""

    model_config = ConfigDict(frozen=True)

    source_type: WakeupSourceTypeEnum = Field(..., description="Source domain of the settlement")
    source_id: str = Field(..., min_length=1, description="Identifier of the task or job")
    success: bool = Field(..., description="Whether the background work succeeded")
    summary: str = Field(..., min_length=1, description="Human-readable completion summary")
    exit_code: int | None = None
    duration_seconds: float | None = None
    error: str | None = None
    details: dict[str, str] = Field(default_factory=dict)


class AdaptiveRoutingResponse(BaseModel):
    """Response returned upon routing a settlement event."""

    model_config = ConfigDict(frozen=True)

    channel: WakeupChannelEnum
    reason: str
    session_id: str
    source_id: str
    consecutive_wakes: int
    budget_remaining: int


class InjectedEventItem(BaseModel):
    """An injected asynchronous event queued for in-flight turn consumption."""

    model_config = ConfigDict(frozen=True)

    source_type: WakeupSourceTypeEnum
    source_id: str
    session_id: str
    success: bool
    summary: str
    exit_code: int | None = None
    duration_seconds: float | None = None
    error: str | None = None
    created_at: datetime


class InjectedEventsResponse(BaseModel):
    """Collection of queued injected events for a session."""

    model_config = ConfigDict(frozen=True)

    session_id: str
    events: list[InjectedEventItem]
    count: int
