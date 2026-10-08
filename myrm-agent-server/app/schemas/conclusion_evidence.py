"""Data transfer objects for Conclusion Attribution & Chat Evidence API.

[POS]
Defines Pydantic request and response schemas for attributed conclusions,
causality derivation traversal, and verifiable chat evidence bundling.

[INPUT]
- typing, pydantic

[OUTPUT]
- CreateAttributedConclusionDTO, AttributedConclusionDTO
- MessageEvidenceItemDTO, ToolCallEvidenceItemDTO, ChatEvidenceBundleDTO
- ChatWithEvidenceRequestDTO, ChatWithEvidenceResponseDTO
- DerivationTraversalViewDTO, ConclusionEvidenceStatsDTO
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateAttributedConclusionDTO(BaseModel):
    """Request payload to declare an attributed conclusion."""

    conclusion_id: str = Field(min_length=1, description="Unique conclusion ID")
    peer_id: str = Field(min_length=1, description="Originating peer ID")
    content: str = Field(min_length=1, description="Normative conclusion text")
    level: str = Field(
        default="explicit",
        description="Attribution classification: explicit, deductive, inductive, abductive, contradiction",
    )
    source_ids: list[str] = Field(default_factory=list, description="Premise conclusion IDs forming the causality chain")
    evidence_message_ids: list[str] = Field(default_factory=list, description="Snapshot message IDs providing factual proof")
    scope_tag: str = Field(default="general", description="Domain classification tag")
    status: str = Field(default="confirmed", description="Lifecycle state")
    metadata: dict[str, str] = Field(default_factory=dict, description="Custom metadata tags")


class AttributedConclusionDTO(BaseModel):
    """Authoritative attributed conclusion object."""

    conclusion_id: str
    peer_id: str
    content: str
    level: str
    source_ids: list[str]
    times_derived: int
    evidence_message_ids: list[str]
    scope_tag: str
    status: str
    created_at: float
    metadata: dict[str, str] = Field(default_factory=dict)


class MessageEvidenceItemDTO(BaseModel):
    """Message snapshot evidence snippet."""

    message_id: str
    session_id: str
    peer_id: str
    content_snippet: str
    timestamp: float


class ToolCallEvidenceItemDTO(BaseModel):
    """Tool call trace evidence record."""

    tool_name: str
    tool_input: dict[str, str] = Field(default_factory=dict)
    tool_output: str = ""


class ChatEvidenceBundleDTO(BaseModel):
    """Verifiable evidence bundle returned when include_evidence is enabled."""

    conclusions: list[AttributedConclusionDTO] = Field(default_factory=list)
    messages: list[MessageEvidenceItemDTO] = Field(default_factory=list)
    tool_calls: list[ToolCallEvidenceItemDTO] = Field(default_factory=list)
    reasoning_trace_id: str | None = None


class ChatWithEvidenceRequestDTO(BaseModel):
    """Request to query memory with optional verifiable evidence packaging."""

    query: str = Field(description="Search or reasoning prompt query")
    peer_id: str | None = Field(default=None, description="Optional peer ID filter")
    include_evidence: bool = Field(default=False, description="When true, returns structured verifiable evidence bundle")


class ChatWithEvidenceResponseDTO(BaseModel):
    """Response containing text answer and optional evidence bundle."""

    content: str
    evidence: ChatEvidenceBundleDTO | None = None


class DerivationTraversalViewDTO(BaseModel):
    """Two-way causal derivation view."""

    conclusion_id: str
    upstream_premises: list[AttributedConclusionDTO] = Field(default_factory=list)
    downstream_derivatives: list[AttributedConclusionDTO] = Field(default_factory=list)
    max_depth: int = 1


class ConclusionEvidenceStatsDTO(BaseModel):
    """Topology and volume statistics of conclusion attribution graph."""

    total_conclusions: int
    total_explicit: int
    total_derived: int
    total_edges: int
    max_derivation_depth: int
