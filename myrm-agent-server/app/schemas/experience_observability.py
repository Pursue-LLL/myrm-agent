"""Schemas for Zero-Refactor Host Lifecycle Plugin and Experience Observability Suite.

[INPUT]
- pydantic::{BaseModel, ConfigDict, Field} (POS: validated request and response models)

[OUTPUT]
- ExperienceObservabilityMetricDTO, SessionTraceEvidenceDTO, ObservabilityDashboardResponseDTO: per-experience metrics, session trace evidence and the dashboard
- HostPluginConfigDTO, UpdatePluginConfigRequest: host lifecycle plugin configuration
- RecordRecallEventRequest, RecordEffectEventRequest: recall and effect event payloads

[POS]
API contracts of experience observability and the host lifecycle plugin, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExperienceObservabilityMetricDTO(BaseModel):
    """Telemetry metric for an experience item."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(..., description="Unique experience procedure entry ID")
    name: str = Field(..., description="Experience title or descriptor")
    source_session_id: str = Field(..., description="Originating session identifier")
    access_channel: str = Field(..., description="Access channel (plugin, mcp, skill)")
    recall_count: int = Field(..., description="Cumulative recall hits")
    injection_count: int = Field(..., description="Cumulative injections into prompt")
    success_count: int = Field(..., description="Successful tasks following injection")
    dispute_count: int = Field(..., description="User disputed or rejected experiences")
    success_rate: float = Field(..., description="Success ratio between 0.0 and 1.0")
    effect_status: str = Field(..., description="Impact category: effective, neutral, adverse")
    last_observed_at: str | None = Field(default=None, description="ISO timestamp of last activity")


class SessionTraceEvidenceDTO(BaseModel):
    """Traceable provenance linking an experience to originating session evidence."""

    model_config = ConfigDict(extra="forbid")

    session_id: str = Field(..., description="Source session identifier")
    title: str = Field(..., description="Session summary title")
    trajectory_summary: str = Field(..., description="High-level narrative of the session")
    key_evidence_snippets: list[str] = Field(default_factory=list, description="Raw quote or evidence snippets")
    agent_role: str = Field(..., description="Role of the agent in originating session")
    timestamp: str = Field(..., description="ISO timestamp of evidence capture")


class HostPluginConfigDTO(BaseModel):
    """Configuration state for the zero-refactor host plugin."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool = Field(..., description="Whether lifecycle hooks are active")
    active_channel: str = Field(..., description="Current access channel (plugin/mcp/skill)")
    auto_warmup: bool = Field(..., description="Whether to warm up experiences on session start")
    auto_capture: bool = Field(..., description="Whether to passively buffer turns")
    auto_commit: bool = Field(..., description="Whether to trigger 2-phase commit on completion")
    monitored_host: str = Field(..., description="Target host identifier")


class UpdatePluginConfigRequest(BaseModel):
    """Request payload to mutate host plugin runtime configuration."""

    model_config = ConfigDict(extra="forbid")

    enabled: bool | None = Field(default=None, description="Toggle plugin enabled")
    active_channel: str | None = Field(default=None, description="Update channel")
    auto_warmup: bool | None = Field(default=None, description="Toggle auto warmup")
    auto_capture: bool | None = Field(default=None, description="Toggle auto capture")
    auto_commit: bool | None = Field(default=None, description="Toggle auto commit")
    monitored_host: str | None = Field(default=None, description="Update target host name")


class RecordRecallEventRequest(BaseModel):
    """Request payload to manually or externally record an experience recall hit."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(..., description="Recalled experience identifier")
    channel: str = Field(default="plugin", description="Channel via which recall occurred")


class RecordEffectEventRequest(BaseModel):
    """Request payload to record task outcome following experience injection."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str = Field(..., description="Injected experience identifier")
    is_success: bool = Field(..., description="Whether task completed successfully")
    is_dispute: bool = Field(default=False, description="Whether user disputed or corrected the output")


class ObservabilityDashboardResponseDTO(BaseModel):
    """Full dashboard triad view aggregating experience list, effect distribution, and plugin state."""

    model_config = ConfigDict(extra="forbid")

    status: str = Field(default="ok")
    total_experiences_tracked: int = Field(..., description="Total tracked experience items")
    overall_success_rate: float = Field(..., description="Average success rate across tracked experiences")
    total_recalls: int = Field(..., description="Sum of all recall events")
    total_injections: int = Field(..., description="Sum of all injection events")
    plugin_config: HostPluginConfigDTO = Field(..., description="Active host plugin configuration")
    metrics: list[ExperienceObservabilityMetricDTO] = Field(default_factory=list, description="All experience telemetry metrics")
