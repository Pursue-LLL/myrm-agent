"""Data transfer objects for Conclusion Attribution and Chat Evidence API (Item 141).

Defines Pydantic V2 schemas for conclusion creation, bidirectional graph traversal,
ripple impact evaluation, and verifiable chat evidence packages.

[POS]
API contract of the conclusion attribution domain, shared by the router and the provider.

[INPUT]
- pydantic

[OUTPUT]
- Conclusion, traversal, ripple impact, chat evidence and metrics request/response models
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class AttributedConclusionDTO(BaseModel):
    """Public representation of an attributed conclusion."""

    id: str = Field(description="Unique conclusion identifier")
    peer_id: str = Field(description="Observer or subject peer identifier")
    content: str = Field(description="Extracted or derived conclusion statement")
    level: str = Field(description="Derivation level: explicit, deductive, inductive, contradiction")
    source_ids: list[str] = Field(default_factory=list, description="IDs of premise conclusions")
    times_derived: int = Field(default=1, description="Independent verification/derivation counter")
    session_id: str | None = Field(default=None, description="Bound session identifier if any")
    confidence: float = Field(default=1.0, description="Normalized confidence score 0.0 to 1.0")
    created_at: str = Field(description="Creation ISO8601 timestamp")
    updated_at: str | None = Field(default=None, description="Update ISO8601 timestamp")
    metadata: dict[str, str] = Field(default_factory=dict, description="Custom metadata tags")


class MessageReferenceDTO(BaseModel):
    """Reference to an original chat message supporting the conclusion."""

    message_id: str = Field(description="Original message identifier")
    session_id: str = Field(description="Session identifier where message occurred")
    role: str = Field(default="user", description="Message sender role")
    snippet: str = Field(description="Extracted verbatim snippet")
    timestamp: str | None = Field(default=None, description="Message timestamp")


class ToolCallRecordDTO(BaseModel):
    """Record of an executed tool call providing grounding evidence."""

    tool_name: str = Field(description="Invoked tool name")
    tool_input: dict[str, str] = Field(default_factory=dict, description="Serialized tool parameters")
    tool_output_snippet: str = Field(default="", description="Snippet of returned tool output")


class ChatEvidenceDTO(BaseModel):
    """Verifiable evidence package associated with an agent response."""

    conclusions: list[AttributedConclusionDTO] = Field(default_factory=list)
    messages: list[MessageReferenceDTO] = Field(default_factory=list)
    tool_calls: list[ToolCallRecordDTO] = Field(default_factory=list)
    reasoning_trace_id: str | None = Field(default=None)


class GraphTraversalNodeDTO(BaseModel):
    """Hierarchy node in a reasoning graph traversal."""

    conclusion: AttributedConclusionDTO
    depth: int = 0
    direct_parent_ids: list[str] = Field(default_factory=list)
    direct_child_ids: list[str] = Field(default_factory=list)


class CreateConclusionRequest(BaseModel):
    """Request payload to create an attributed memory conclusion."""

    peer_id: str = Field(min_length=1, description="Target peer identity")
    content: str = Field(min_length=1, description="Conclusion content")
    level: str = Field(default="explicit", description="explicit, deductive, inductive, or contradiction")
    source_ids: list[str] = Field(default_factory=list, description="Premise conclusion IDs")
    session_id: str | None = Field(default=None, description="Optional session scope")
    confidence: float = Field(default=1.0, ge=0.0, le=1.0, description="Confidence score")
    metadata: dict[str, str] = Field(default_factory=dict, description="Arbitrary string metadata")


class CreateConclusionResponse(BaseModel):
    """Response containing created conclusion DTO."""

    conclusion: AttributedConclusionDTO
    status: str = "created"


class QueryConclusionsRequest(BaseModel):
    """Semantic/keyword query for memory conclusions."""

    query: str = Field(description="Search terms or semantic intent")
    peer_id: str | None = Field(default=None, description="Filter by peer identity")
    level: str | None = Field(default=None, description="Filter by attribution level")
    top_k: int = Field(default=10, ge=1, le=100, description="Max results")


class QueryConclusionsResponse(BaseModel):
    """Query response containing matching conclusions."""

    items: list[AttributedConclusionDTO]
    total: int


class ListConclusionsResponse(BaseModel):
    """Paginated list of memory conclusions."""

    items: list[AttributedConclusionDTO]
    total: int
    page: int
    size: int


class TraverseTreeResponse(BaseModel):
    """Traversed graph nodes in upward or downward direction."""

    root_id: str
    direction: Literal["downward", "upward"]
    nodes: list[GraphTraversalNodeDTO]
    total_nodes: int


class RippleImpactResponse(BaseModel):
    """Assessment of ripple effects upon conclusion retraction or edit."""

    target_conclusion_id: str
    impacted_conclusion_ids: list[str]
    depth_reached: int
    severity: Literal["low", "medium", "high", "critical"]
    explanation: str


class ChatWithEvidenceRequest(BaseModel):
    """Simulated or actual chat request requesting transparent evidence."""

    query: str = Field(min_length=1, description="User question or statement")
    peer_id: str = Field(min_length=1, description="Peer identity")
    session_id: str | None = Field(default=None, description="Session identifier")
    include_evidence: bool = Field(default=True, description="Whether to include evidence package")


class ChatWithEvidenceResponse(BaseModel):
    """Response accompanied by verifiable ChatEvidence package."""

    reply: str
    evidence: ChatEvidenceDTO | None = None


class AttributionMetricsResponse(BaseModel):
    """Global telemetry and attribution health metrics."""

    total_conclusions: int
    explicit_count: int
    deductive_count: int
    inductive_count: int
    contradiction_count: int
    max_derivation_depth: int
    average_times_derived: float


class DeleteConclusionResponse(BaseModel):
    """Result of deleting a conclusion."""

    deleted_ids: list[str]
    cascade: bool
    status: str
