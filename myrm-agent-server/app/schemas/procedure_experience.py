# [POS]: app/schemas/procedure_experience.py
# [INPUT]: None (Pydantic models for Procedure-Shaped Experience Protocol & Dual-Node Retrieval)
# [OUTPUT]: ProcedureMemoryEntryDTO, RegisterProcedureMemoryRequest, DualNodeRetrievalRequest, DualNodeRetrievalResponseDTO, ProtocolValidationResponseDTO, MultiIntentSplitRequest, MultiIntentSplitResponseDTO

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ProcedureMemoryEntryDTO(BaseModel):
    """DTO representing an 8-field procedure-shaped experience memory unit."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str
    name: str
    retrieval_anchor: str
    operation_intent: str
    preconditions: list[str] = Field(default_factory=list)
    immutable_boundary: list[str] = Field(default_factory=list)
    procedure_steps: list[str] = Field(default_factory=list)
    write_field_provenance: dict[str, str] = Field(default_factory=dict)
    anti_patterns: list[str] = Field(default_factory=list)
    applicability: list[str] = Field(default_factory=list)
    negative_applicability: list[str] = Field(default_factory=list)
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_session_id: str | None = None
    created_at: str | None = None


class RegisterProcedureMemoryRequest(BaseModel):
    """Request payload to register a new procedure memory following the 8-field protocol."""

    model_config = ConfigDict(extra="forbid")

    entry_id: str | None = None
    name: str = Field(..., description="Short recognizable procedure name")
    operation_intent: str = Field(..., description="Primary operation intent")
    preconditions: list[str] = Field(..., min_length=1, description="Required preconditions")
    immutable_boundary: list[str] = Field(..., min_length=1, description="Protected immutable boundaries")
    procedure_steps: list[str] = Field(..., min_length=1, description="Sequential steps")
    write_field_provenance: dict[str, str] = Field(..., description="Output field provenance mappings")
    anti_patterns: list[str] = Field(..., min_length=1, description="Common anti-patterns to avoid")
    applicability: list[str] = Field(..., min_length=1, description="Positive application contexts")
    negative_applicability: list[str] = Field(..., min_length=1, description="Negative exclusion boundaries")
    retrieval_anchor: str | None = None
    confidence: float = Field(default=1.0, ge=0.0, le=1.0)
    source_session_id: str | None = None


class DualNodeRetrievalRequest(BaseModel):
    """Request payload to execute fixed-count dual-node retrieval."""

    model_config = ConfigDict(extra="forbid")

    query_text: str = Field(..., description="Query text matching operation intent or action context")
    node_kind: str = Field(default="first_user", description="Call site node: 'first_user' or 'pre_write'")
    top_n: int = Field(default=2, ge=1, le=10, description="Fixed-count top N entries to inject")
    scope_filter: str | None = None


class DualNodeRetrievalResponseDTO(BaseModel):
    """Response payload returning fixed-count retrieved procedure memories."""

    model_config = ConfigDict(extra="forbid")

    node_kind: str
    top_n_requested: int
    total_matched: int
    matched_entries: list[ProcedureMemoryEntryDTO]


class ProtocolValidationResponseDTO(BaseModel):
    """Response payload detailing protocol conformance check."""

    model_config = ConfigDict(extra="forbid")

    is_valid: bool
    violations: list[str] = Field(default_factory=list)


class MultiIntentSplitRequest(BaseModel):
    """Request payload to split a multi-intent raw execution trace into distinct fragments."""

    model_config = ConfigDict(extra="forbid")

    raw_text: str = Field(..., description="Multi-intent execution trace text")


class MultiIntentSplitResponseDTO(BaseModel):
    """Response payload containing decomposed single-intent fragments."""

    model_config = ConfigDict(extra="forbid")

    fragment_count: int
    fragments: list[dict[str, str]]
