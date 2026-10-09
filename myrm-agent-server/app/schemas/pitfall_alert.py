"""Data transfer objects for proactive pitfall alert and decision assist API.

[POS]
Pydantic contracts for shadow intent evaluation, causal triad seeding,
session muting, and proactive alert delivery.

[INPUT]
- typing, pydantic

[OUTPUT]
- EvaluateInputRequest, MuteSubjectRequest, UnmuteSubjectRequest, SeedTriadRequest
- PitfallAlertCardDTO, PitfallEvaluationResponse, PitfallAlertStatusResponse
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class EvaluateInputRequest(BaseModel):
    """Payload for evaluating user query against historical decision pitfalls."""

    user_input: str = Field(min_length=1, description="Raw query from the user")
    session_id: str = Field(default="default", description="Conversation session identifier")
    current_runtime_version: str = Field(
        default="", description="Optional runtime version (e.g. Python 3.12, Redis 7.2)"
    )


class MuteSubjectRequest(BaseModel):
    """Payload for muting a technical subject in the current session."""

    session_id: str = Field(min_length=1, description="Conversation session identifier")
    subject: str = Field(min_length=1, description="Technical topic to suppress alerts for")


class UnmuteSubjectRequest(BaseModel):
    """Payload for unmuting a technical subject in the current session."""

    session_id: str = Field(min_length=1, description="Conversation session identifier")
    subject: str = Field(min_length=1, description="Technical topic to restore alerts for")


class SeedTriadRequest(BaseModel):
    """Payload to register a historical causal triad postmortem into the engine."""

    subject: str = Field(min_length=1, description="Core technical topic (e.g. redis, mongodb)")
    approach: str = Field(min_length=1, description="Specific architecture or library decision attempted")
    pitfall_lesson: str = Field(min_length=1, description="Root failure cause, incident details, and impact")
    validated_alternative: str = Field(min_length=1, description="Proven resolution or verified alternative")
    severity: Literal["critical", "warning", "info"] = Field(
        default="warning", description="Severity category of the historical incident"
    )
    incident_date: str = Field(default="", description="Incident date or reference id")
    version_context: str = Field(default="", description="Technical runtime context when incident occurred")


class PitfallAlertCardDTO(BaseModel):
    """Structured proactive advice card presented when architectural pitfall is detected."""

    alert_id: str = Field(description="Unique alert identifier")
    subject: str = Field(description="Target technical subject")
    intent_summary: str = Field(description="Synthesized summary of detected decision intent")
    historical_pitfall: str = Field(description="Concrete historical failure lesson")
    recommended_action: str = Field(description="Pre-validated alternative architectural solution")
    severity: str = Field(description="Alert severity (critical, warning, info)")
    source_ref: str = Field(description="Historical incident reference or timestamp")
    drift_warning: str = Field(description="Advisory note if runtime versions have evolved")
    dispatch_channel: str = Field(description="Target channel: frontend_callout, shadow_thought_only, silent")
    is_muted: bool = Field(default=False, description="Whether alert was muted by session configuration")


class PitfallEvaluationResponse(BaseModel):
    """Telemetry and proactive alert result returned to agent frontend or runtime loop."""

    evaluation_id: str = Field(description="Unique evaluation trace id")
    intent_detected: bool = Field(description="Whether a decision intent was captured")
    intent_level: str = Field(description="Intent classification level: commitment or inquiry")
    triad_matched: bool = Field(description="Whether a matching negative postmortem was found")
    alert_generated: bool = Field(description="Whether an alert card was actively dispatched")
    dispatched_channel: str = Field(description="Final channel selected for alert")
    latency_ms: float = Field(ge=0.0, description="End-to-end evaluation latency in milliseconds")
    alert_card: PitfallAlertCardDTO | None = Field(default=None, description="Dispatched alert card, if any")


class PitfallAlertStatusResponse(BaseModel):
    """Operational telemetry report of the pitfall alert engine."""

    active: bool = Field(default=True, description="Whether the proactive alert service is operational")
    seeded_triads_count: int = Field(ge=0, description="Total count of registered postmortems")
    muted_sessions_count: int = Field(ge=0, description="Total count of active muted session scopes")
