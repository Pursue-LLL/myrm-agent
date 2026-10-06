"""
[POS] app/schemas/memory_dual_track.py
[INPUT] pydantic
[OUTPUT] ExtractDualTrackRequestDTO, ExtractedProceduralRuleDTO, ExtractedUserFactDTO, ExtractionDestinyReportDTO, ProceduralRuleQueryResponseDTO, FactQueryResponseDTO

Pydantic DTOs for Dual-Track Memory Extraction Routing and Anti-Silent-Drop Gateway.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ExtractDualTrackRequestDTO(BaseModel):
    """Payload to request dual-track adaptive memory extraction."""

    model_config = ConfigDict(extra="forbid")

    text: str = Field(..., min_length=1, description="Raw interaction text, message, or instruction")
    domain: str = Field(default="general", description="Operational domain (e.g. devops, golang, general)")
    auto_persist: bool = Field(
        default=True,
        description="Whether to automatically register and persist extracted rules and facts in server memory stores",
    )


class ExtractedProceduralRuleDTO(BaseModel):
    """DTO representing an extracted actionable procedural instruction."""

    model_config = ConfigDict(extra="forbid")

    rule_id: str = Field(..., description="Unique deterministic or random procedural rule identifier")
    name: str = Field(..., description="Rule human-readable identifier or brief name")
    trigger_condition: str = Field(..., description="Triggering pattern or condition")
    action_guideline: str = Field(..., description="Actionable operational directive")
    domain: str = Field(default="general", description="Rule operational domain")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence score")
    raw_source: str = Field(..., description="Original raw snippet that yielded the rule")


class ExtractedUserFactDTO(BaseModel):
    """DTO representing an extracted user profile or declarative fact."""

    model_config = ConfigDict(extra="forbid")

    fact_id: str = Field(..., description="Unique fact record identifier")
    entity: str = Field(..., description="Subject entity identifier")
    attribute: str = Field(..., description="Extracted attribute name")
    value: str = Field(..., description="Extracted attribute value")
    confidence: float = Field(..., ge=0.0, le=1.0, description="Extraction confidence score")
    raw_source: str = Field(..., description="Original raw text snippet")


class ExtractionDestinyReportDTO(BaseModel):
    """Complete destiny report of incoming text through the extraction gateway."""

    model_config = ConfigDict(extra="forbid")

    destiny: str = Field(
        ...,
        description="Final destination: stored_semantic, stored_procedural, stored_dual, or discarded_no_signal",
    )
    track: str = Field(..., description="Assessed track kind: procedural, fact_profile, dual_track, or no_signal")
    discard_reason: str = Field(
        default="",
        description="Transparent explanation if discarded, eliminating silent drops",
    )
    raw_input_text: str = Field(..., description="Original raw input text evaluated")
    processed_at: str = Field(..., description="ISO 8601 processing timestamp")
    extracted_facts: list[ExtractedUserFactDTO] = Field(
        default_factory=list,
        description="List of extracted declarative user/world facts",
    )
    extracted_rules: list[ExtractedProceduralRuleDTO] = Field(
        default_factory=list,
        description="List of extracted actionable procedural rules",
    )


class ProceduralRuleQueryResponseDTO(BaseModel):
    """Response containing list of stored procedural rules."""

    model_config = ConfigDict(extra="forbid")

    rules: list[ExtractedProceduralRuleDTO] = Field(default_factory=list, description="Stored rules")
    total: int = Field(..., ge=0, description="Total number of stored rules")


class FactQueryResponseDTO(BaseModel):
    """Response containing list of stored facts."""

    model_config = ConfigDict(extra="forbid")

    facts: list[ExtractedUserFactDTO] = Field(default_factory=list, description="Stored facts")
    total: int = Field(..., ge=0, description="Total number of stored facts")
