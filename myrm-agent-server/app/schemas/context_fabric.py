"""Pydantic schemas for Cross-Source Context Fabric and Project Entity Linker.

[INPUT]
- Multi-source work events, entity extraction payloads, project matching requests, insight sinks.

[OUTPUT]
- WorkEventDTO, WorkContextEntityDTO, ProjectRegistryEntryDTO, EntityMatchResultDTO,
  ExtractEntitiesRequestDTO, ExtractEntitiesResponseDTO, LinkEntitiesRequestDTO,
  LinkEntitiesResponseDTO, InsightCandidateDTO, InsightSinkRequestDTO, InsightSinkResponseDTO.

[POS]
- Server-side DTO contracts for Item 153 CrossSourceWorkContextFabricAndProjectEntityLinkerSuite.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class WorkEventDTO(BaseModel):
    """Data transfer object for a multi-source work event."""

    event_id: str = Field(..., description="Unique event identifier")
    source_kind: str = Field(..., description="Origin source kind (feishu, dingtalk, linear, local_file, etc.)")
    source_id: str = Field(..., description="Identifier in source platform")
    title: str = Field(..., description="Event title or subject")
    raw_content: str = Field(..., description="Raw text or transcript content")
    author: str = Field(default="", description="Author or speaker")
    timestamp_ms: int = Field(default=0, description="Creation timestamp in ms")
    metadata: dict[str, str] = Field(default_factory=dict, description="Custom metadata tags")


class WorkContextEntityDTO(BaseModel):
    """Structured entity extracted from work event."""

    entity_id: str
    entity_type: str  # project | person | module | commitment | blocker
    name: str
    role_or_relation: str = ""
    temporal_anchor: str | None = None
    status: str = "active"
    confidence: float = 1.0
    evidence_snippet: str = ""


class ProjectRegistryEntryDTO(BaseModel):
    """Project entry registered in the workspace registry."""

    project_id: str = Field(..., description="Unique project slug or identifier")
    name: str = Field(..., description="Canonical project name")
    aliases: list[str] = Field(default_factory=list, description="Project aliases")
    keywords: list[str] = Field(default_factory=list, description="Domain keywords")
    description: str = Field(default="", description="Project scope and description")
    status: str = Field(default="active", description="active | archived | planned")


class EntityMatchResultDTO(BaseModel):
    """Result of linking text to a canonical project."""

    project_id: str
    project_name: str
    confidence_score: float
    matched_terms: list[str] = Field(default_factory=list)
    evidence_snippet: str = ""
    is_definitive: bool = False


class ExtractEntitiesRequestDTO(BaseModel):
    """Payload to extract entities from an event or raw text."""

    text: str = Field(..., description="Raw text or meeting transcript")
    source_kind: str = Field(default="custom", description="Optional source hint")


class ExtractEntitiesResponseDTO(BaseModel):
    """Response containing extracted entities."""

    entities: list[WorkContextEntityDTO] = Field(default_factory=list)
    total_count: int = 0


class LinkEntitiesRequestDTO(BaseModel):
    """Payload to link text to registered projects."""

    text: str = Field(..., description="Content to resolve against projects")
    min_confidence: float = Field(default=0.4, description="Minimum confidence threshold")


class LinkEntitiesResponseDTO(BaseModel):
    """Response listing project match candidates."""

    matches: list[EntityMatchResultDTO] = Field(default_factory=list)
    top_project_id: str | None = None


class InsightCandidateDTO(BaseModel):
    """Actionable insight candidate for sinking to project memory."""

    insight_id: str
    title: str
    content: str
    source_event_ids: list[str] = Field(default_factory=list)
    target_project_id: str | None = None
    impact_level: str = "medium"


class InsightSinkRequestDTO(BaseModel):
    """Payload to sink an insight into project memory with provenance."""

    candidate: InsightCandidateDTO
    workspace_dir: str | None = None
    target_file_type: str = "PROJECT_STATE.md"


class InsightSinkResponseDTO(BaseModel):
    """Outcome of sinking an insight."""

    success: bool
    record_id: str | None = None
    project_id: str | None = None
    sink_target: str | None = None
    provenance_tag: str | None = None
    rendered_bullet: str | None = None
    message: str = ""
