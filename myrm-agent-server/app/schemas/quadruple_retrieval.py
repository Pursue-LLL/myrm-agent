"""Schemas for Goal-Driven Quadruple Retrieval and Reasoner Suite.

[POS]
Pydantic DTO contracts for query intent decomposition, 4-way parallel recall,
reasoner reranking outcomes, and audit rationale reports. Strictly typed without Any.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class QueryIntentTypeEnum(str, Enum):
    """Classification of the primary retrieval intent."""

    FACTUAL = "factual"
    PROCEDURAL = "procedural"
    PREFERENCE = "preference"
    EPISODIC = "episodic"
    GENERAL_EXPLORATION = "general_exploration"
    TECHNICAL_STANDARD = "technical_standard"


class RetrievalChannelKindEnum(str, Enum):
    """Parallel memory recall channel types."""

    GRAPH = "graph"
    VECTOR = "vector"
    LEXICAL = "lexical"
    METADATA = "metadata"


class ReasonerDecisionKindEnum(str, Enum):
    """Semantic reasoner decision during reranking."""

    KEEP = "keep"
    SUPPRESS = "suppress"
    BOOST = "boost"
    PENALIZE_STALE = "penalize_stale"


class TaskGoalDTO(BaseModel):
    """Data transfer object for pre-retrieval decomposed task goal."""

    goal_id: str = Field(..., description="Unique goal UUID")
    original_query: str = Field(..., description="Raw input query")
    explicit_intent: str = Field(..., description="Classified intent identifier")
    target_entities: List[str] = Field(
        default_factory=list, description="Extracted core target entities"
    )
    extracted_keywords: List[str] = Field(
        default_factory=list, description="Lexical search keywords"
    )
    metadata_filters: Dict[str, str] = Field(
        default_factory=dict, description="Extracted metadata filter criteria"
    )
    temporal_constraints: Optional[str] = Field(
        None, description="Extracted temporal constraint if any"
    )
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Parser confidence score")
    created_at: str = Field(..., description="Decomposition timestamp")


class MemoryHitDTO(BaseModel):
    """Final memory hit refined and ordered by the semantic reasoner."""

    memory_id: str = Field(..., description="Memory identifier")
    content: str = Field(..., description="Memory content statement")
    final_rank: int = Field(..., ge=1, description="Final rank position")
    final_score: float = Field(..., description="Harmonized final relevance score")
    channels_hit: List[RetrievalChannelKindEnum] = Field(
        default_factory=list, description="Channels that successfully recalled this item"
    )
    reasoner_decision: ReasonerDecisionKindEnum = Field(
        ..., description="Decision made by reasoner module"
    )
    rationale: str = Field(..., description="White-box audit rationale for ranking")
    metadata: Dict[str, str] = Field(
        default_factory=dict, description="Preserved node metadata tags"
    )


class QuadrupleSearchRequest(BaseModel):
    """Request payload to execute goal-driven quadruple retrieval."""

    query: str = Field(..., min_length=1, description="Natural language search query")
    scoped_filters: Optional[Dict[str, str]] = Field(
        None, description="Optional scoped filters (e.g. env, cube_id, tier)"
    )
    top_k: int = Field(5, ge=1, le=50, description="Maximum number of top memory hits to return")


class QuadrupleSearchResponse(BaseModel):
    """Response payload containing end-to-end quadruple retrieval and reasoner outcome."""

    query: str = Field(..., description="Original search query")
    parsed_goal: TaskGoalDTO = Field(..., description="Decomposed task goal")
    channel_hits_count: Dict[str, int] = Field(
        default_factory=dict, description="Count of candidate hits per channel"
    )
    fused_candidates_count: int = Field(
        ..., ge=0, description="Total unique candidates fused across channels"
    )
    final_hits: List[MemoryHitDTO] = Field(
        default_factory=list, description="Final ordered list of reranked memory hits"
    )
    latency_ms: float = Field(..., ge=0.0, description="Pipeline elapsed time in milliseconds")
    created_at: str = Field(..., description="Execution completion timestamp")


class IngestMemoryItemRequest(BaseModel):
    """Request payload to register a searchable memory item in service store."""

    memory_id: str = Field(..., min_length=1, description="Unique memory ID")
    content: str = Field(..., min_length=1, description="Fact or policy statement content")
    subject: str = Field(..., min_length=1, description="Primary subject entity")
    predicate: str = Field(..., min_length=1, description="Relation or property predicate")
    object_value: str = Field(..., min_length=1, description="Target value or entity")
    metadata: Dict[str, str] = Field(
        default_factory=dict, description="Arbitrary metadata key-values"
    )
