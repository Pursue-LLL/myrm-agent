"""Schemas for multimodal vision assets and sandbox artifacts memory API.

[INPUT]
- pydantic BaseModel, Field

[OUTPUT]
- MultimodalIngestRequestDTO, MultimodalMemoryItemDTO
- MultimodalSearchRequestDTO, MultimodalSearchHitDTO, MultimodalSearchResponseDTO

[POS]
app.schemas.multimodal_memory
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class MultimodalIngestRequestDTO(BaseModel):
    """Payload to ingest a vision asset or sandbox artifact into multimodal memory."""

    title: str = Field(..., min_length=1, max_length=200, description="Title of the asset or artifact")
    description: str = Field(..., min_length=1, max_length=2000, description="Detailed text description")
    modality: str = Field(default="artifact", description="Asset modality: image, artifact, or hybrid")
    artifact_kind: str = Field(default="generic_file", description="Kind: diagram, chart, report_html, data_sheet, source_code, generic_file")
    visual_summary: str | None = Field(default=None, description="OCR text or visual layout description")
    file_path: str | None = Field(default=None, description="Physical path in sandbox volume or storage")
    mime_type: str = Field(default="application/octet-stream", description="MIME content type")
    tags: list[str] = Field(default_factory=list, description="Categorical and domain tags")
    session_id: str | None = Field(default=None, description="Scoped session identifier")
    metadata: dict[str, str] = Field(default_factory=dict, description="Arbitrary string key-value metadata")


class MultimodalMemoryItemDTO(BaseModel):
    """Domain model of indexed multimodal memory item."""

    item_id: str = Field(..., description="Unique item identifier")
    modality: str = Field(..., description="Asset modality")
    artifact_kind: str = Field(..., description="Artifact structural kind")
    title: str = Field(..., description="Title of the asset")
    description: str = Field(..., description="Detailed description")
    mime_type: str = Field(..., description="MIME content type")
    visual_summary: str | None = Field(default=None, description="Visual description or OCR text")
    file_path: str | None = Field(default=None, description="Path to physical file")
    tags: list[str] = Field(default_factory=list, description="Extracted tags")
    session_id: str | None = Field(default=None, description="Originating session identifier")
    created_at: str = Field(..., description="ISO 8601 creation timestamp")
    metadata: dict[str, str] = Field(default_factory=dict, description="Associated metadata")


class MultimodalSearchRequestDTO(BaseModel):
    """Specification for cross-modal search query."""

    query_text: str = Field(..., min_length=1, max_length=500, description="Natural language search query")
    modality_filter: str | None = Field(default=None, description="Optional modality filter: image, artifact, hybrid")
    artifact_kind_filter: str | None = Field(default=None, description="Optional artifact kind filter")
    session_id: str | None = Field(default=None, description="Optional session filter")
    limit: int = Field(default=10, ge=1, le=50, description="Maximum number of hits to return")


class MultimodalSearchHitDTO(BaseModel):
    """Single ranked search hit with presentation card metadata."""

    item: MultimodalMemoryItemDTO = Field(..., description="Indexed multimodal asset record")
    relevance_score: float = Field(..., description="Relevance score between 0.0 and 1.0")
    matched_modality: str = Field(..., description="Matched modality")
    card_preview: dict[str, str] = Field(default_factory=dict, description="UI card preview presentation attributes")


class MultimodalSearchResponseDTO(BaseModel):
    """Collection response for cross-modal search query."""

    hits: list[MultimodalSearchHitDTO] = Field(default_factory=list, description="Ranked retrieval hits")
    total_matched: int = Field(..., description="Total number of items matched")
    query_text: str = Field(..., description="Executed query string")
