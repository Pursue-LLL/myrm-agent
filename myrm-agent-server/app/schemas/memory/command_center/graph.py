"""[INPUT]
- pydantic::BaseModel (POS: request/response model base)

[OUTPUT]
- MemoryCommandGraphNode, MemoryCommandGraphEdge, MemoryCommandGraphStats, MemoryCommandGraphHubItem, MemoryCommandGraphResponse

[POS]
Memory command center schemas: memory graph nodes, edges, hubs and the graph response.
"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class MemoryCommandGraphNode(BaseModel):
    """Graph node for claim graph visualization."""

    id: str
    labels: list[str] = Field(default_factory=list)
    properties: dict[str, str | int | float | bool] = Field(default_factory=dict)


class MemoryCommandGraphEdge(BaseModel):
    """Graph edge (relationship) for claim graph visualization."""

    id: str
    source: str
    target: str
    rel_type: str
    properties: dict[str, str | int | float] = Field(default_factory=dict)
    valid_from: str | None = None
    valid_until: str | None = None
    superseded_by: str | None = None
    supersedes_id: str | None = None


class MemoryCommandGraphStats(BaseModel):
    """Graph aggregate statistics."""

    node_count: int = 0
    relationship_count: int = 0
    node_label_counts: dict[str, int] = Field(default_factory=dict)
    relationship_type_counts: dict[str, int] = Field(default_factory=dict)


class MemoryCommandGraphHubItem(BaseModel):
    """Ranked high-centrality claim or hotspot for dual-view navigation."""

    id: str
    label: str
    snippet: str = ""
    primary_namespace: str | None = None
    degree: int = 0
    in_degree: int = 0
    out_degree: int = 0
    supported_count: int = 0
    contradicted_count: int = 0
    has_conflict: bool = False


class MemoryCommandGraphResponse(BaseModel):
    """Knowledge Graph visualization data for the command center."""

    nodes: list[MemoryCommandGraphNode] = Field(default_factory=list)
    edges: list[MemoryCommandGraphEdge] = Field(default_factory=list)
    stats: MemoryCommandGraphStats = Field(default_factory=MemoryCommandGraphStats)
    ranked_hubs: list[MemoryCommandGraphHubItem] = Field(default_factory=list)
    graph_state: Literal["ready", "storage_disabled", "empty_knowledge", "sparse_islands"] = "ready"
    has_graph: bool = False
