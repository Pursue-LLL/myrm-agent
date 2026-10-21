"""Pydantic V2 schemas for Zero-Token Fleet Runtime Event Mirror Contract (Item 48).

[INPUT]
- MirrorEventRequest, BatchMirrorEventRequest, LlmCallCheckRequest, SimulateViolationRequest.

[OUTPUT]
- ZeroTokenEventDTO, LlmCallCheckResponse, VizCallAuditRecordDTO, ZeroTokenAuditReportResponse.

[POS]
- Server-side typed DTO schemas enforcing zero-token visualization contract.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ZeroTokenEventSourceEnum(enum.StrEnum):
    """Source of runtime event."""

    RUNTIME_SSE = "runtime_sse"
    GATEWAY_WEBHOOK = "gateway_webhook"
    LIVENESS_HEARTBEAT = "liveness_heartbeat"
    KANBAN_WEBHOOK = "kanban_webhook"


class ZeroTokenEventTypeEnum(enum.StrEnum):
    """Event types mirrored deterministically to UI."""

    SUBAGENT_SPAWNED = "subagent_spawned"
    SUBAGENT_STATUS_UPDATE = "subagent_status_update"
    SUBAGENT_TERMINATED = "subagent_terminated"
    TOOL_START = "tool_start"
    TOOL_FINISH = "tool_finish"
    NODE_HEARTBEAT = "node_heartbeat"
    KANBAN_TRANSITION = "kanban_transition"


class ProtectedVizSurfaceEnum(enum.StrEnum):
    """UI Surfaces strictly forbidden from invoking LLMs directly."""

    FLEET_CANVAS = "fleet_canvas"
    THREE_D_OFFICE = "3d_office"
    PET_STATUS = "pet_status"
    AMBIENT_DISPLAY = "ambient_display"
    ACTIVE_NOW_BADGE = "active_now_badge"


class ZeroTokenEventDTO(BaseModel):
    """DTO representing a single mirrored runtime event."""

    model_config = ConfigDict(frozen=True)

    event_id: str = Field(..., description="Unique event identifier")
    source: ZeroTokenEventSourceEnum = Field(..., description="Source stream/webhook")
    event_type: ZeroTokenEventTypeEnum = Field(..., description="Domain event category")
    agent_id: str = Field(..., description="Identifier of the emitting agent or node")
    payload: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Deterministic event data payload"
    )
    timestamp: str = Field(
        default_factory=lambda: datetime.now(UTC).isoformat(),
        description="ISO timestamp of event occurrence",
    )


class MirrorEventRequest(BaseModel):
    """Request payload to mirror a single runtime event to visualization layer."""

    event_id: str = Field(..., description="Event identifier")
    source: ZeroTokenEventSourceEnum = Field(
        default=ZeroTokenEventSourceEnum.RUNTIME_SSE, description="Source of the event"
    )
    event_type: ZeroTokenEventTypeEnum = Field(
        default=ZeroTokenEventTypeEnum.SUBAGENT_STATUS_UPDATE, description="Type of event"
    )
    agent_id: str = Field(..., description="Agent or node identifier")
    payload: dict[str, str | int | float | bool] = Field(
        default_factory=dict, description="Event payload"
    )


class BatchMirrorEventRequest(BaseModel):
    """Request payload to mirror multiple runtime events atomically."""

    events: list[MirrorEventRequest] = Field(
        ..., min_length=1, description="List of events to mirror"
    )


class LlmCallCheckRequest(BaseModel):
    """Request payload to check/audit an LLM invocation request from any caller surface."""

    caller_surface: str = Field(
        ..., description="Identifier or name of the calling surface/module"
    )
    prompt: str = Field(..., description="Prompt content destined for LLM")


class LlmCallCheckResponse(BaseModel):
    """Response indicating whether LLM invocation was permitted or intercepted."""

    model_config = ConfigDict(frozen=True)

    allowed: bool = Field(..., description="True if caller is allowed to call LLM")
    intercepted: bool = Field(..., description="True if blocked by Zero-Token Doctor")
    reason: str | None = Field(
        default=None, description="Explanation or violation rationale"
    )


class VizCallAuditRecordDTO(BaseModel):
    """Audit record capturing an intercepted or allowed LLM call attempt."""

    model_config = ConfigDict(frozen=True)

    caller_surface: str = Field(..., description="Surface identifier")
    prompt_chars: int = Field(..., description="Character count of prompt")
    is_violation: bool = Field(..., description="True if call constituted a contract breach")
    intercepted_reason: str = Field(..., description="Audit detail or reason")
    timestamp: str = Field(..., description="ISO timestamp")


class ZeroTokenAuditReportResponse(BaseModel):
    """Audit snapshot response detailing zero-token guarantee metrics."""

    model_config = ConfigDict(frozen=True)

    chat_id: str = Field(..., description="Chat session ID")
    total_events_mirrored: int = Field(..., description="Count of mirrored runtime events")
    total_tokens_spent: int = Field(
        default=0, description="Tokens spent by visualization layer (guaranteed 0)"
    )
    saved_tokens_estimated: int = Field(
        ..., description="Estimated tokens saved by subscribing to runtime events"
    )
    violations_intercepted: int = Field(
        ..., description="Count of illegal viz-to-LLM calls successfully blocked"
    )
    is_compliant: bool = Field(
        ..., description="True if no unhandled violations occurred"
    )
    recent_violations: list[VizCallAuditRecordDTO] = Field(
        default_factory=list, description="Latest intercepted violation records"
    )
    last_mirrored_at: str | None = Field(
        default=None, description="ISO timestamp of latest mirrored event"
    )


class SimulateViolationRequest(BaseModel):
    """Request to trigger a synthetic violation test for contract verification."""

    caller_surface: str = Field(
        default="fleet_canvas", description="Surface name to test"
    )
    test_prompt: str = Field(
        default="Decide agent facial expression and movement in 3D canvas",
        description="Synthetic prompt to trigger Doctor intercept",
    )
