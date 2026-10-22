"""Pydantic V2 schemas for Cross-Surface Agent Activity Conversation Bridge (Item 49).

[INPUT]
- IngestActivityRequest, BatchIngestActivityRequest, PruneStalePresencesRequest.

[OUTPUT]
- IngressActivityItemDTO, SurfacePresenceSummaryDTO, CrossSurfaceProjectionResponseDTO,
  PruneStalePresencesResponseDTO.

[POS]
- Server-side typed DTO schemas for cross-surface activity bridge.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class SurfaceOriginEnum(enum.StrEnum):
    """Origin surface of the external agent activity."""

    TAURI_DESKTOP = "tauri_desktop"
    CLI_TOOL = "cli_tool"
    CRON_JOB = "cron_job"
    REMOTE_OFFICE_CLONE = "remote_office_clone"


class ActivityKindEnum(enum.StrEnum):
    """Categorized lifecycle or streaming event kind."""

    TURN_START = "turn_start"
    THINKING_PULSE = "thinking_pulse"
    TOOL_CALL = "tool_call"
    TOOL_RESULT = "tool_result"
    TURN_COMPLETE = "turn_complete"
    HEARTBEAT = "heartbeat"


class PresenceStatusEnum(enum.StrEnum):
    """Status of the external surface presence session."""

    ACTIVE = "active"
    IDLE = "idle"
    COMPLETED = "completed"


class IngressActivityItemDTO(BaseModel):
    """DTO representing a single projected external activity item."""

    model_config = ConfigDict(frozen=True)

    activity_id: str = Field(..., description="Unique activity event identifier")
    session_key: str = Field(..., description="External session / thread identifier")
    source_surface: SurfaceOriginEnum = Field(..., description="Originating surface environment")
    agent_id: str = Field(..., description="External agent or tool identifier")
    activity_kind: ActivityKindEnum = Field(..., description="Kind of event")
    preview_text: str = Field(..., max_length=256, description="Bounded human-readable preview summary")
    metadata: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Redacted scalar metadata"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO timestamp of activity event",
    )


class IngestActivityRequest(BaseModel):
    """Request payload to ingress a single external agent activity."""

    activity_id: str = Field(..., description="Activity identifier")
    session_key: str = Field(..., description="External session key")
    source_surface: SurfaceOriginEnum = Field(
        default=SurfaceOriginEnum.TAURI_DESKTOP, description="Origin surface"
    )
    agent_id: str = Field(..., description="Agent or runner ID")
    activity_kind: ActivityKindEnum = Field(
        default=ActivityKindEnum.TOOL_CALL, description="Event kind"
    )
    preview_text: str = Field(..., description="Brief activity summary")
    metadata: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Optional metadata key-values"
    )


class BatchIngestActivityRequest(BaseModel):
    """Request payload to ingress multiple external activities atomically."""

    activities: list[IngestActivityRequest] = Field(
        ..., min_length=1, description="List of activities to ingress"
    )


class SurfacePresenceSummaryDTO(BaseModel):
    """DTO describing the read-only presence state of an external surface."""

    model_config = ConfigDict(frozen=True)

    session_key: str = Field(..., description="External session key")
    source_surface: SurfaceOriginEnum = Field(..., description="Source surface")
    agent_id: str = Field(..., description="Active agent ID")
    status: PresenceStatusEnum = Field(..., description="Current presence status")
    last_active_at: str = Field(..., description="ISO timestamp of last activity")
    recent_activities_count: int = Field(
        ..., description="Number of recent activities recorded"
    )


class CrossSurfaceProjectionResponseDTO(BaseModel):
    """DTO representing the aggregated Fleet Canvas projection snapshot."""

    model_config = ConfigDict(frozen=True)

    chat_id: str = Field(..., description="Target chat/canvas session ID")
    active_presences: list[SurfacePresenceSummaryDTO] = Field(
        default_factory=list, description="External surface presences"
    )
    total_ingressed_activities: int = Field(
        ..., description="Monotonically increasing count of ingressed events"
    )
    bounded_recent_activities: list[IngressActivityItemDTO] = Field(
        default_factory=list, description="Bounded recent activity waterfall"
    )
    last_ingressed_at: str | None = Field(
        default=None, description="ISO timestamp of newest ingressed event"
    )


class PruneStalePresencesRequest(BaseModel):
    """Request payload to prune idle or completed presences."""

    max_idle_seconds: float = Field(
        default=300.0, ge=10.0, description="Inactivity threshold in seconds"
    )


class PruneStalePresencesResponseDTO(BaseModel):
    """Response payload detailing pruned presences."""

    model_config = ConfigDict(frozen=True)

    pruned_count: int = Field(..., description="Number of sessions pruned or marked idle")
    updated_snapshot: CrossSurfaceProjectionResponseDTO = Field(
        ..., description="Updated projection snapshot"
    )
