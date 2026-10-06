"""
[POS] app/schemas/graph_rrf.py
[INPUT] pydantic
[OUTPUT] EntityNodeCreateRequest, RelationEdgeCreateRequest, MemoryAssociationRequest, GraphTraverseRequest, VectorHitInput, DualChannelSearchRequest, EntityNodeResponse, RelationEdgeResponse, GraphTraverseResponse, FusedMemoryHitResponse, DualChannelSearchResponse
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class EntityNodeCreateRequest(BaseModel):
    """Payload to create or update an entity node."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, description="Unique entity identifier")
    name: str = Field(..., min_length=1, description="Entity display name")
    entity_type: str = Field(..., min_length=1, description="Entity classification")
    properties: dict[str, str] = Field(
        default_factory=dict, description="Custom key-value attributes"
    )


class RelationEdgeCreateRequest(BaseModel):
    """Payload to create or update a directional relationship edge."""

    model_config = ConfigDict(extra="forbid")

    id: str = Field(..., min_length=1, description="Unique edge identifier")
    source_id: str = Field(..., min_length=1, description="Source entity ID")
    target_id: str = Field(..., min_length=1, description="Target entity ID")
    relation_type: str = Field(..., min_length=1, description="Relation predicate")
    weight: float = Field(default=1.0, ge=0.0, description="Edge strength weight")
    properties: dict[str, str] = Field(
        default_factory=dict, description="Custom key-value attributes"
    )


class MemoryAssociationRequest(BaseModel):
    """Payload to link a memory unit with an entity node."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., min_length=1, description="Memory item ID")
    entity_id: str = Field(..., min_length=1, description="Entity node ID")
    content: str = Field(
        default="", description="Optional stored memory content preview"
    )


class GraphTraverseRequest(BaseModel):
    """Payload to trigger BFS traversal from seed entities."""

    model_config = ConfigDict(extra="forbid")

    seed_entity_ids: list[str] = Field(
        ..., min_length=1, description="Seed entity IDs to start walk from"
    )
    max_hops: int = Field(default=2, ge=1, le=5, description="Maximum traversal depth")
    allowed_relations: list[str] | None = Field(
        default=None, description="Optional relation type whitelist"
    )


class VectorHitInput(BaseModel):
    """Candidate memory from external vector search channel."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., description="Target memory ID")
    content: str = Field(default="", description="Memory text snippet")
    score: float = Field(default=0.0, description="Raw cosine or dot-product score")
    rank: int = Field(..., ge=1, description="1-indexed rank in vector search")


class DualChannelSearchRequest(BaseModel):
    """Payload for dual-channel hybrid vector and knowledge graph RRF search."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Natural language search query")
    seed_entity_names: list[str] | None = Field(
        default=None, description="Explicit entity names for graph anchoring"
    )
    seed_entity_ids: list[str] | None = Field(
        default=None, description="Explicit entity IDs for graph anchoring"
    )
    vector_candidates: list[VectorHitInput] | None = Field(
        default=None, description="Optional vector search hits to fuse"
    )
    top_k: int = Field(default=10, ge=1, le=100, description="Max final hits to return")
    k: int = Field(default=60, ge=1, description="RRF smoothing parameter")
    vector_weight: float = Field(default=1.0, ge=0.0, description="Weight for vector rank")
    graph_weight: float = Field(default=1.0, ge=0.0, description="Weight for graph rank")
    max_graph_hops: int = Field(default=2, ge=1, le=5, description="Max graph traversal hops")


class EntityNodeResponse(BaseModel):
    """Entity node representation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    name: str
    entity_type: str
    properties: dict[str, str]
    created_at: float


class RelationEdgeResponse(BaseModel):
    """Relation edge representation."""

    model_config = ConfigDict(extra="forbid")

    id: str
    source_id: str
    target_id: str
    relation_type: str
    weight: float
    properties: dict[str, str]
    created_at: float


class GraphTraverseResponse(BaseModel):
    """Graph traversal result."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[EntityNodeResponse]
    edges: list[RelationEdgeResponse]
    paths: list[dict[str, str | int]]
    associated_memory_ids: list[str]


class FusedMemoryHitResponse(BaseModel):
    """Single item fused across vector and knowledge graph channels."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str
    content: str
    fused_score: float
    vector_rank: int | None
    graph_rank: int | None
    hit_sources: list[str]
    explanation: dict[str, str | int | float | list[str]]


class DualChannelSearchResponse(BaseModel):
    """Top-level response for dual-channel hybrid search."""

    model_config = ConfigDict(extra="forbid")

    results: list[FusedMemoryHitResponse]
    total_hits: int
    query: str
