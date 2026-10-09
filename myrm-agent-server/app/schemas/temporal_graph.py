"""[POS]: app/schemas/temporal_graph.py
[INPUT]: Pydantic BaseModel, Field, datetime, and typing primitives.
[OUTPUT]: Request and response DTO schemas for temporal entities, fact edges, conflict reconciliation, and decay scoring.
"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class TemporalEntityNodeDTO(BaseModel):
    """Entity node in the temporal knowledge graph."""

    node_id: str = Field(description="Unique entity identifier")
    name: str = Field(description="Entity name or label")
    entity_type: str = Field(description="Entity classification category, e.g. user, organization, project")
    attributes: dict[str, str] = Field(default_factory=dict, description="Metadata key-value pairs")
    created_at: datetime = Field(description="Creation timestamp")
    updated_at: datetime = Field(description="Last update timestamp")


class SaveEntityNodeRequestDTO(BaseModel):
    """Payload to create or update an entity node."""

    name: str = Field(description="Entity name or label")
    entity_type: str = Field(default="concept", description="Entity category type")
    attributes: dict[str, str] = Field(default_factory=dict, description="Custom metadata attributes")
    node_id: str | None = Field(default=None, description="Optional custom entity ID")


class TemporalFactEdgeDTO(BaseModel):
    """Relationship edge with temporal validity interval and supersession state."""

    edge_id: str = Field(description="Unique edge identifier")
    source_id: str = Field(description="Source entity node ID")
    target_id: str = Field(description="Target entity node ID")
    predicate: str = Field(description="Relationship predicate, e.g. works_at, residence_city, primary_database")
    valid_from: datetime = Field(description="Timestamp when fact became valid")
    valid_until: datetime | None = Field(default=None, description="Timestamp when fact became superseded or expired")
    is_superseded: bool = Field(description="True if edge was replaced by newer conflicting fact")
    superseded_by: str | None = Field(default=None, description="ID of superseding edge")
    confidence_score: float = Field(ge=0.0, le=1.0, description="Base confidence score")
    access_count: int = Field(ge=0, description="Cumulative retrieval hit count")
    last_accessed_at: datetime | None = Field(default=None, description="Timestamp of most recent retrieval")
    created_at: datetime = Field(description="Creation timestamp")


class SaveFactEdgeRequestDTO(BaseModel):
    """Payload to insert a new fact relationship edge, triggering conflict reconciliation."""

    source_id: str = Field(description="Source entity node ID")
    target_id: str = Field(description="Target entity node ID")
    predicate: str = Field(description="Relationship predicate")
    confidence_score: float = Field(default=1.0, ge=0.0, le=1.0, description="Base fact confidence")
    edge_id: str | None = Field(default=None, description="Optional custom edge ID")


class FactConflictResolutionResultDTO(BaseModel):
    """Outcome report when inserting a fact edge and resolving mutual exclusion conflicts."""

    new_edge: TemporalFactEdgeDTO = Field(description="Newly inserted active fact edge")
    superseded_edges: list[TemporalFactEdgeDTO] = Field(
        default_factory=list, description="Historical edges marked superseded"
    )
    is_conflict_detected: bool = Field(description="True if mutually exclusive contradiction was reconciled")
    conflict_reason: str = Field(description="Description of reconciliation decision")


class TemporalFactHitDTO(BaseModel):
    """Ranked fact hit with dynamic exponential half-life decay score."""

    edge: TemporalFactEdgeDTO = Field(description="Evaluated fact edge")
    source_node: TemporalEntityNodeDTO = Field(description="Resolved source entity")
    target_node: TemporalEntityNodeDTO = Field(description="Resolved target entity")
    decayed_score: float = Field(description="Calculated recency and access-boosted score")
    effective_status: str = Field(description="Edge lifecycle state: active, superseded, expired")


class TemporalGraphStatsDTO(BaseModel):
    """Summary metrics of the temporal knowledge graph."""

    total_nodes_count: int = Field(ge=0, description="Total entity nodes stored")
    active_edges_count: int = Field(ge=0, description="Currently valid active relationship edges")
    superseded_edges_count: int = Field(ge=0, description="Historical superseded edges preserved for lineage")
    average_decayed_score: float = Field(ge=0.0, le=1.0, description="Average recency score of active edges")
