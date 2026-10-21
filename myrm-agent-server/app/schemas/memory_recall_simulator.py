"""
[POS] app/schemas/memory_recall_simulator.py
[INPUT] pydantic
[OUTPUT] RecallSimulateRequest, RecallCandidateScore, RecallCandidate, RecallSimulateResponse, MemoryGovernanceUpdateRequest, MemoryGovernanceUpdateResponse
"""

from __future__ import annotations

from typing import Literal
from pydantic import BaseModel, ConfigDict, Field


class RecallSimulateRequest(BaseModel):
    """Request payload for simulating dynamic memory recall across multiple retrieval channels."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., min_length=1, description="Input query or test prompt to simulate recall for")
    top_k: int = Field(default=5, ge=1, le=50, description="Maximum number of candidates to return")
    domain_filter: str | None = Field(default=None, description="Optional domain or skill partition filter")
    recall_types: list[Literal["bm25", "vector", "causal_gene"]] = Field(
        default=["bm25", "vector", "causal_gene"],
        description="Active recall pipelines enabled for RRF fusion",
    )


class RecallCandidateScore(BaseModel):
    """Detailed multi-dimensional matching scores for a recalled memory candidate."""

    model_config = ConfigDict(extra="forbid")

    rrf_score: float = Field(..., ge=0.0, le=1.0, description="Reciprocal Rank Fusion composite score")
    bm25_score: float = Field(..., ge=0.0, description="BM25 lexical relevance score")
    vector_similarity: float = Field(..., ge=0.0, le=1.0, description="Vector cosine semantic similarity")
    causal_relevance: float = Field(..., ge=0.0, le=1.0, description="Causal gene / decision graph affinity")


class RecallCandidate(BaseModel):
    """Candidate memory item with transparency metadata and governance indicators."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., min_length=1, description="Unique memory or gene identifier")
    content: str = Field(..., min_length=1, description="Original memory textual body")
    summary: str = Field(..., min_length=1, description="Concise summary or lesson learned")
    recall_type: str = Field(..., description="Dominant recall pipeline or primary match channel")
    scores: RecallCandidateScore = Field(..., description="Multi-dimensional ranking scores")
    confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Operator-controllable confidence weight")
    is_negative_trap: bool = Field(default=False, description="Whether marked as a must-avoid pitfall gene")
    status: Literal["active", "disabled", "locked"] = Field(
        default="active", description="Governance lifecycle status of this memory item"
    )
    hit_reason: str = Field(..., description="Explainability attribution statement")
    tags: list[str] = Field(default_factory=list, description="Categorization or skill domain tags")


class RecallSimulateResponse(BaseModel):
    """Result of the recall simulation sandbox run."""

    model_config = ConfigDict(extra="forbid")

    query: str = Field(..., description="Evaluated query string")
    total_matched: int = Field(ge=0, description="Total candidate items matching retrieval conditions")
    candidates: list[RecallCandidate] = Field(default_factory=list, description="Ranked top-k recalled items")
    execution_latency_ms: float = Field(ge=0.0, description="Simulated retrieval latency in milliseconds")


class MemoryGovernanceUpdateRequest(BaseModel):
    """Payload to perform in-place secondary governance adjustments on a memory item."""

    model_config = ConfigDict(extra="forbid")

    memory_id: str = Field(..., min_length=1, description="Identifier of the target memory item")
    confidence: float | None = Field(default=None, ge=0.0, le=1.0, description="Updated confidence score")
    is_negative_trap: bool | None = Field(default=None, description="Toggle negative pitfall trap flag")
    status: Literal["active", "disabled", "locked"] | None = Field(
        default=None, description="Updated lifecycle governance status"
    )
    merged_into_id: str | None = Field(default=None, description="Optional target memory ID if merging duplicates")


class MemoryGovernanceUpdateResponse(BaseModel):
    """Result of applying governance action."""

    model_config = ConfigDict(extra="forbid")

    success: bool = Field(..., description="Whether governance update succeeded")
    memory_id: str = Field(..., description="Target memory ID")
    message: str = Field(..., description="Outcome summary message")
    updated_record: RecallCandidate = Field(..., description="Latest state of the governed memory item")
