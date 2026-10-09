"""Schemas for Graph Memory Reorganization and Lineage Traceability.

[POS]
Pydantic DTO contracts for entity graph nodes, relational edges,
immutable lineage tracking steps, and graph reorganization operations.
Strictly typed without Any.
"""

from __future__ import annotations

from enum import Enum
from typing import Dict, List, Optional

from pydantic import BaseModel, Field


class GraphRelationTypeEnum(str, Enum):
    """Multi-relational semantic edge types."""

    SUBSUMPTION = "subsumption"
    TEMPORAL_SEQUENCE = "temporal_sequence"
    DEDUCTION = "deduction"
    SUPERSEDES = "supersedes"
    DERIVED_FROM = "derived_from"
    CONTRADICTION = "contradiction"
    MERGED_INTO = "merged_into"


class MemoryNodeStatusEnum(str, Enum):
    """Lifecycle status of memory graph nodes."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    REVERTED = "reverted"


class MemoryGraphNodeDTO(BaseModel):
    """Data transfer object for a memory graph node."""

    node_id: str = Field(..., description="Unique node UUID")
    lineage_root_id: str = Field(..., description="Root lineage identifier")
    version: int = Field(1, ge=1, description="Sequential version counter")
    subject: str = Field(..., description="Subject entity name")
    predicate: str = Field(..., description="Relationship or property predicate")
    object_value: str = Field(..., description="Target value or entity")
    content: str = Field(..., description="Full synthesized statement content")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score")
    status: MemoryNodeStatusEnum = Field(
        MemoryNodeStatusEnum.ACTIVE, description="Node status"
    )
    created_at: str = Field(..., description="Creation ISO-8601 timestamp")
    updated_at: str = Field(..., description="Last update ISO-8601 timestamp")
    source_session_id: Optional[str] = Field(None, description="Origin session ID")
    evidence_quote: Optional[str] = Field(None, description="Direct quote evidence")
    metadata: Dict[str, str] = Field(
        default_factory=dict, description="Custom metadata tags"
    )


class MemoryGraphEdgeDTO(BaseModel):
    """Data transfer object for a directional semantic edge between memory nodes."""

    edge_id: str = Field(..., description="Unique edge identifier")
    source_node_id: str = Field(..., description="Source node UUID")
    target_node_id: str = Field(..., description="Target node UUID")
    relation_type: GraphRelationTypeEnum = Field(..., description="Semantic relation type")
    weight: float = Field(1.0, ge=0.0, le=1.0, description="Relation weight/confidence score")
    rationale: str = Field("", description="Reasoning or inference context")
    created_at: str = Field(..., description="Edge creation ISO-8601 timestamp")


class CreateNodeRequest(BaseModel):
    """Request payload to create a new initial memory graph node."""

    subject: str = Field(..., min_length=1, description="Subject entity name")
    predicate: str = Field(..., min_length=1, description="Predicate property")
    object_value: str = Field(..., min_length=1, description="Object value")
    content: Optional[str] = Field(None, description="Optional custom statement content")
    confidence: float = Field(1.0, ge=0.0, le=1.0, description="Confidence score")
    source_session_id: Optional[str] = Field(None, description="Origin session ID")
    evidence_quote: Optional[str] = Field(None, description="Direct quote evidence")
    metadata: Dict[str, str] = Field(
        default_factory=dict, description="Metadata key-values"
    )


class EvolveNodeRequest(BaseModel):
    """Request payload to evolve an existing node into a superseding revision."""

    object_value: Optional[str] = Field(None, description="Updated object value")
    content: Optional[str] = Field(None, description="Updated content statement")
    rationale: str = Field(
        "Memory evolved with updated preferences or factual supersession.",
        description="Reason for evolving the memory",
    )
    metadata: Dict[str, str] = Field(
        default_factory=dict, description="Metadata patch or additional tags"
    )


class RevertNodeRequest(BaseModel):
    """Request payload to revert an active node back to a historical version snapshot."""

    historical_node_id: str = Field(
        ..., min_length=1, description="Historical node ID to revert back to"
    )
    rationale: str = Field(
        "Rollback to historical memory version",
        min_length=1,
        description="Audit reason for reversion",
    )


class CreateEdgeRequest(BaseModel):
    """Request payload to establish an explicit relationship between nodes."""

    source_node_id: str = Field(..., description="Source node id")
    target_node_id: str = Field(..., description="Target node id")
    relation_type: GraphRelationTypeEnum = Field(..., description="Relation type")
    weight: float = Field(1.0, ge=0.0, le=1.0, description="Weight/Confidence score")
    rationale: str = Field("", description="Audit rationale")


class LineageStepDTO(BaseModel):
    """A discrete audited transition step in the evolution DAG."""

    step_index: int = Field(..., ge=0, description="Chronological step index")
    node: MemoryGraphNodeDTO = Field(..., description="Snapshot node in lineage")
    relation_to_target: Optional[GraphRelationTypeEnum] = Field(
        None, description="Relation to target node"
    )
    rationale: str = Field("", description="Audit rationale")
    timestamp: str = Field(..., description="Event timestamp")


class MemoryLineageTrailDTO(BaseModel):
    """Full audited history trail for a conceptual entity."""

    target_node: MemoryGraphNodeDTO = Field(..., description="Target node snapshot")
    lineage_root_id: str = Field(..., description="Root lineage identifier")
    ancestor_nodes: List[MemoryGraphNodeDTO] = Field(
        default_factory=list, description="Historical ancestor nodes"
    )
    descendant_nodes: List[MemoryGraphNodeDTO] = Field(
        default_factory=list, description="Forward descendant nodes"
    )
    steps: List[LineageStepDTO] = Field(
        default_factory=list, description="Ordered lineage transition steps"
    )
    relation_edges: List[MemoryGraphEdgeDTO] = Field(
        default_factory=list, description="Associated lineage edges"
    )
    depth: int = Field(..., ge=0, description="Lineage depth")
    is_latest: bool = Field(..., description="Whether target node is latest active version")


class ReorganizeRequest(BaseModel):
    """Request payload to run memory graph reorganization."""

    min_confidence: float = Field(
        0.8, ge=0.0, le=1.0, description="Minimum confidence for inferred relations"
    )


class ReorganizeResponse(BaseModel):
    """Result report of graph memory reorganization."""

    batch_id: str = Field(..., description="Batch identifier")
    analyzed_nodes_count: int = Field(..., ge=0, description="Number of analyzed active nodes")
    created_edges_count: int = Field(..., ge=0, description="Number of created semantic edges")
    superseded_nodes_count: int = Field(..., ge=0, description="Number of superseded nodes")
    deductions_count: int = Field(..., ge=0, description="Number of deduced nodes")
    edges: List[MemoryGraphEdgeDTO] = Field(
        default_factory=list, description="List of created edges in batch"
    )
    created_at: str = Field(..., description="Batch execution timestamp")
