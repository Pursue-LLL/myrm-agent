"""Pydantic V2 schemas for Heavy MCP Payload Fetch Subagent & Summarizer (Item 44).

[INPUT]
- SummarizePayloadRequest, DiagnosePayloadRequest.

[OUTPUT]
- McpPayloadSummaryArtifactDTO, ContaminationReportDTO, SubagentPresetSpecDTO.

[POS]
- Server-side typed DTO schemas for MCP payload isolation and structured summarization.
"""

from __future__ import annotations

import enum
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field


class ContaminationRiskLevelEnum(enum.StrEnum):
    """Threat level when injecting bulky MCP payloads directly into parent conversation."""

    SAFE = "safe"
    SUSPICIOUS = "suspicious"
    SEVERE_CONTAMINATION = "severe_contamination"


class PayloadExtractionTargetDTO(BaseModel):
    """Extraction rules for pruning and restructuring bulky raw payloads."""

    model_config = ConfigDict(frozen=True)

    required_keys: list[str] = Field(
        default_factory=list, description="Keys to extract from JSON dictionary"
    )
    max_summary_tokens: int = Field(
        default=800, ge=50, le=4000, description="Max token limit for generated summary"
    )
    strip_raw_binary: bool = Field(
        default=True, description="Whether to discard binary/base64 encoded payloads"
    )
    preserve_markdown_tables: bool = Field(
        default=True, description="Preserve structured markdown tables"
    )
    summarize_nested_lists_limit: int = Field(
        default=5, ge=1, le=50, description="Max nested list items in summary preview"
    )


class McpPayloadSummaryArtifactDTO(BaseModel):
    """Summary artifact returned to parent context without polluting full history."""

    model_config = ConfigDict(frozen=True)

    artifact_id: str = Field(..., min_length=1, description="Unique artifact identifier")
    source_tool_or_mcp: str = Field(..., min_length=1, description="Origin tool or MCP name")
    raw_payload_bytes: int = Field(..., ge=0, description="Original raw payload byte length")
    summary_bytes: int = Field(..., ge=0, description="Restructured summary byte length")
    token_saving_ratio: float = Field(
        ..., ge=0.0, le=1.0, description="Ratio of tokens saved from raw payload"
    )
    summary_text: str = Field(..., description="Compact summary representation")
    extracted_fields: dict[str, str] = Field(
        default_factory=dict, description="Key-value mapping of extracted fields"
    )
    file_reference_path: str | None = Field(
        default=None, description="Optional path to persistent full raw artifact"
    )
    created_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Creation timestamp"
    )


class ContaminationReportDTO(BaseModel):
    """Diagnostic audit report evaluating payload size and recommending subagent isolation."""

    model_config = ConfigDict(frozen=True)

    risk_level: ContaminationRiskLevelEnum = Field(..., description="Contamination severity tier")
    payload_bytes: int = Field(..., ge=0, description="Evaluated payload byte length")
    estimated_tokens: int = Field(..., ge=0, description="Estimated token count")
    is_isolated_via_subagent: bool = Field(
        ..., description="Whether payload fetch was isolated inside subagent"
    )
    remediation_advice: str = Field(..., description="Actionable remediation recommendation")
    detected_at: datetime = Field(
        default_factory=lambda: datetime.now(tz=UTC), description="Audit timestamp"
    )


class SubagentPresetSpecDTO(BaseModel):
    """Specification of the prebuilt mcp-data-summarizer subagent."""

    model_config = ConfigDict(frozen=True)

    name: str = Field(default="mcp-data-summarizer", description="Preset subagent name")
    description: str = Field(..., description="Subagent operational role description")
    tools_whitelist: list[str] = Field(
        default_factory=list, description="Permitted tools inside isolated worker"
    )
    default_extraction_target: PayloadExtractionTargetDTO = Field(
        default_factory=PayloadExtractionTargetDTO, description="Default extraction preferences"
    )


class SummarizePayloadRequest(BaseModel):
    """Request to summarize a bulky MCP payload and extract structured fields."""

    model_config = ConfigDict(frozen=True)

    source_tool: str = Field(..., min_length=1, description="Origin tool or MCP name")
    raw_payload: str = Field(..., description="Bulky raw payload content to summarize")
    target: PayloadExtractionTargetDTO | None = Field(
        default=None, description="Optional custom extraction target"
    )
    artifact_store_path: str | None = Field(
        default=None, description="Optional offline storage destination"
    )


class DiagnosePayloadRequest(BaseModel):
    """Request to diagnose context contamination risk of an MCP tool payload."""

    model_config = ConfigDict(frozen=True)

    raw_payload: str = Field(..., description="Raw payload content to diagnose")
    is_isolated_via_subagent: bool = Field(
        default=False, description="Whether fetch was routed through dedicated subagent"
    )
