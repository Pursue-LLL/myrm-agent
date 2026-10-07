"""Pydantic V2 DTO schemas for onboarding insight sampling and first-encounter reporting.

[INPUT]
- typing: List, Optional, Literal
- pydantic: BaseModel, Field, ConfigDict

[OUTPUT]
- ScanAgentSourcesRequest, OnboardingAgentSourceInfo, OnboardingScanSummaryResponse
- GenerateFirstEncounterReportRequest, ExtractedInsightFactDTO, FirstEncounterReportResponse
- ConfirmInsightIngestRequest, ConfirmInsightIngestResponse

[POS]
Server data transfer layer for agent onboarding discovery, report generation,
and one-click preference ingestion into persistent memory.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class ScanAgentSourcesRequest(BaseModel):
    """Request payload for probing host agent sources."""

    model_config = ConfigDict(extra="forbid")

    custom_search_paths: list[str] = Field(
        default_factory=list,
        description="Optional list of custom filesystem directories to probe for sessions.",
    )


class OnboardingAgentSourceInfo(BaseModel):
    """Information summary of an individual agent source."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., description="Unique identifier of the agent source.")
    display_name: str = Field(..., description="Human-readable display name.")
    detected: bool = Field(..., description="Whether this agent source is active on host.")
    recent_sessions_count: int = Field(default=0, description="Number of recent session files found.")


class OnboardingScanSummaryResponse(BaseModel):
    """Scan response listing available external agent sources."""

    model_config = ConfigDict(extra="forbid")

    sources: list[OnboardingAgentSourceInfo] = Field(
        default_factory=list,
        description="List of probed agent sources.",
    )
    total_detected: int = Field(..., description="Total count of active agent sources.")


class GenerateFirstEncounterReportRequest(BaseModel):
    """Request payload to generate a first-encounter insight report."""

    model_config = ConfigDict(extra="forbid")

    target_sources: list[str] = Field(
        default_factory=list,
        description="Target source IDs to sample (empty for all detected sources).",
    )
    max_sessions_per_source: int = Field(
        default=6,
        ge=1,
        le=30,
        description="Maximum recent session files to sample per source.",
    )
    enable_entropy_inspection: bool = Field(
        default=True,
        description="Whether to enable Shannon entropy inspection for un-prefixed secrets.",
    )


class ExtractedInsightFactDTO(BaseModel):
    """Extracted insight item categorized into tech stack, lesson, or active goal."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(..., description="Unique fact item identifier.")
    category: Literal["tech_stack_preference", "hard_learned_lesson", "active_project_goal"] = Field(
        ...,
        description="Fact categorization category.",
    )
    summary: str = Field(..., description="Concise structured summary of the insight.")
    source_agent: str = Field(..., description="Source agent where this insight was mined.")
    confidence: float = Field(..., description="Confidence score between 0.0 and 1.0.")
    fingerprint: str = Field(..., description="SHA-256 content deduplication fingerprint.")
    origin_conversation_id: str = Field(..., description="Original session or file identifier.")
    raw_quote: str = Field(default="", description="Original quote snippet supporting this fact.")


class FirstEncounterReportResponse(BaseModel):
    """Response payload containing generated first encounter report and candidate facts."""

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(..., description="Unique report identifier.")
    generated_at: str = Field(..., description="ISO 8601 generation timestamp.")
    probed_sources: list[str] = Field(default_factory=list, description="Agent source IDs sampled.")
    scanned_session_count: int = Field(..., description="Total sessions scanned.")
    total_messages_sampled: int = Field(..., description="Total conversation messages sampled.")
    facts: list[ExtractedInsightFactDTO] = Field(
        default_factory=list,
        description="List of extracted insight facts ready for user review.",
    )
    warnings: list[str] = Field(default_factory=list, description="Non-fatal warnings encountered.")


class ConfirmInsightIngestRequest(BaseModel):
    """Request payload confirming user acceptance of specific insight facts."""

    model_config = ConfigDict(extra="forbid")

    report_id: str = Field(..., description="Report identifier containing the facts.")
    selected_fact_ids: list[str] = Field(
        default_factory=list,
        description="List of fact IDs user selected for ingestion (empty accepts all).",
    )
    target_agent_id: str | None = Field(
        default=None,
        description="Target agent ID (None denotes default or global shared memory).",
    )


class ConfirmInsightIngestResponse(BaseModel):
    """Response confirming batch ingestion of selected insight facts."""

    model_config = ConfigDict(extra="forbid")

    ingested_count: int = Field(..., description="Number of facts successfully ingested.")
    skipped_count: int = Field(..., description="Number of facts skipped or deduplicated.")
    target_agent_id: str | None = Field(default=None, description="Agent receiving memories.")
    status: str = Field(default="ok", description="Status confirmation string.")
