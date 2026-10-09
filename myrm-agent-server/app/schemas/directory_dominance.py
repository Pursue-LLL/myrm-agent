"""[POS]: app/schemas/directory_dominance.py
[INPUT]: Hierarchy node structures, query requests, and dominance ratio configurations.
[OUTPUT]: Strongly typed Pydantic models for hierarchical directory dominance API endpoints.
"""

from enum import StrEnum

from pydantic import BaseModel, Field


class HierarchyNodeTypeAPI(StrEnum):
    """Hierarchy node classifications for API endpoints."""

    DIRECTORY = "directory"
    FILE = "file"
    CHUNK = "chunk"


class DominanceDecisionAPI(StrEnum):
    """Dominance resolution decisions for API endpoints."""

    DIRECTORY_DOMINANT = "directory_dominant"
    LEAF_SPECIFIC = "leaf_specific"
    BALANCED = "balanced"


class HierarchicalNodePayload(BaseModel):
    """Payload representing a single hierarchical node for search."""

    uri: str = Field(..., description="Canonical URI identifier of the node")
    node_type: HierarchyNodeTypeAPI = Field(default=HierarchyNodeTypeAPI.FILE, description="Node classification")
    name: str = Field(..., description="Segment or display name")
    parent_uri: str | None = Field(default=None, description="Parent directory canonical URI")
    children_uris: list[str] = Field(default_factory=list, description="Immediate children URIs")
    abstract: str = Field(default="", description="L0 compact abstract or description")
    content: str = Field(default="", description="L1 overview or full payload")
    score: float = Field(default=0.0, ge=0.0, description="Relevance score")


class SiblingContextItemPayload(BaseModel):
    """Bundled sibling node summary payload."""

    uri: str = Field(..., description="Sibling canonical URI")
    name: str = Field(..., description="Sibling display name")
    abstract: str = Field(..., description="L0 summary of the sibling")
    relation: str = Field(default="sibling", description="Relationship label")


class HierarchicalRetrievalHitPayload(BaseModel):
    """Augmented retrieval hit containing hierarchical context and siblings."""

    uri: str = Field(..., description="Canonical URI of the hit")
    node_type: HierarchyNodeTypeAPI = Field(..., description="Type of node")
    score: float = Field(..., ge=0.0, description="Resolved relevance score")
    decision: DominanceDecisionAPI = Field(..., description="Dominance classification")
    abstract: str = Field(default="", description="L0 abstract")
    content: str = Field(default="", description="Overview or detail content")
    parent_uri: str | None = Field(default=None, description="Parent URI if present")
    parent_summary: str | None = Field(default=None, description="Parent overview summary")
    sibling_contexts: list[SiblingContextItemPayload] = Field(
        default_factory=list,
        description="Bundled sibling abstracts",
    )


class HierarchicalRetrievalStatsPayload(BaseModel):
    """Execution telemetry and metrics for hierarchical search."""

    convergence_rounds: int = Field(default=1, ge=1, description="Executed convergence rounds")
    nodes_evaluated: int = Field(default=0, ge=0, description="Count of evaluated nodes")
    dominant_directories_count: int = Field(default=0, ge=0, description="Dominant directory count")
    leaf_hits_count: int = Field(default=0, ge=0, description="Localized leaf hits count")
    total_siblings_bundled: int = Field(default=0, ge=0, description="Total bundled sibling items")


class HierarchicalRetrieveRequest(BaseModel):
    """Request payload to execute hierarchical directory dominance retrieval."""

    query: str = Field(..., description="Search query string")
    nodes: list[HierarchicalNodePayload] = Field(..., description="Hierarchical candidate nodes")
    limit: int = Field(default=5, ge=1, le=50, description="Maximum hits to return")
    dominance_ratio: float = Field(
        default=1.2,
        ge=1.0,
        le=5.0,
        description="Ratio threshold (dir_score >= max_child_score * ratio) to declare directory dominance",
    )
    max_convergence_rounds: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum iterations allowed for hierarchical convergence",
    )
    max_parallel_child_searches: int = Field(
        default=4,
        ge=1,
        le=20,
        description="Maximum fan-out exploring child subtrees per directory",
    )
    max_siblings_per_hit: int = Field(
        default=3,
        ge=0,
        le=10,
        description="Maximum sibling context items bundled per hit",
    )
    include_parent_context: bool = Field(
        default=True,
        description="Whether to include parent overview summary",
    )


class HierarchicalRetrieveResponse(BaseModel):
    """Response payload for hierarchical retrieval execution."""

    query: str = Field(..., description="Echoed query string")
    hits: list[HierarchicalRetrievalHitPayload] = Field(default_factory=list, description="Resolved hits")
    stats: HierarchicalRetrievalStatsPayload = Field(
        default_factory=HierarchicalRetrievalStatsPayload,
        description="Telemetry and convergence statistics",
    )


class DominanceEvaluationRequest(BaseModel):
    """Request payload to evaluate directory dominance against its immediate children."""

    dir_node: HierarchicalNodePayload = Field(..., description="Target directory node")
    children_nodes: list[HierarchicalNodePayload] = Field(
        default_factory=list,
        description="Immediate children nodes",
    )
    dominance_ratio: float = Field(
        default=1.2,
        ge=1.0,
        le=5.0,
        description="Dominance ratio threshold",
    )


class DominanceEvaluationResponse(BaseModel):
    """Response payload detailing directory dominance decision."""

    dir_uri: str = Field(..., description="Target directory URI")
    dir_score: float = Field(..., description="Target directory score")
    max_child_score: float = Field(default=0.0, description="Highest child score observed")
    dominance_ratio: float = Field(..., description="Configured dominance ratio")
    required_threshold: float = Field(..., description="Threshold needed for directory dominance")
    decision: DominanceDecisionAPI = Field(..., description="Resolved dominance decision")
