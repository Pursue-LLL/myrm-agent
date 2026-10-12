"""Pydantic schemas for Graph Memory Reorganization and Lineage Traceability endpoints.

[POS]
记忆图谱重组与演化溯源链 DTO 契约。
提供全链路严格强类型的请求体、响应体、白盒演化溯源图谱与版本回滚契约。

[INPUT]
- 前端与运行时触发的图谱重组扫描请求
- 记忆节点演化溯源追溯与版本回退请求

[OUTPUT]
- LineageRelationTypeEnum: 语义与谱系边分类
- MemoryNodeStatusEnum: 记忆节点生命周期状态
- MemoryGraphNodeDTO: 记忆图谱节点 DTO
- MemoryGraphEdgeDTO: 多维语义与演化关系边 DTO
- LineageStepDTO: 谱系推导演化单步里程碑 DTO
- MemoryLineageTrailDTO: 白盒可解释演化溯源树 DTO
- ReorganizationBatchRequest: 触发重组执行请求
- ReorganizationBatchResponse: 重组执行报告响应
- LineageRevertRequest: 版本回滚请求体
- LineageRevertResponse: 版本回滚响应体
- MemoryTopologyGraphDTO: 记忆全景图谱拓扑
- LineageStatsDTO: 谱系与图谱概览指标
"""

from __future__ import annotations

from enum import StrEnum

from pydantic import BaseModel, ConfigDict, Field


class LineageRelationTypeEnum(StrEnum):
    """Taxonomy of graph relation types connecting memory nodes."""

    SUBSUMPTION = "subsumption"
    TEMPORAL_SEQUENCE = "temporal_sequence"
    DEDUCTION = "deduction"
    SUPERSEDES = "supersedes"
    DERIVED_FROM = "derived_from"
    CONTRADICTION = "contradiction"
    MERGED_INTO = "merged_into"


class MemoryNodeStatusEnum(StrEnum):
    """Lifecycle status of a memory node."""

    ACTIVE = "active"
    SUPERSEDED = "superseded"
    ARCHIVED = "archived"
    REVERTED = "reverted"


class MemoryGraphNodeDTO(BaseModel):
    """Memory node with lineage and graph identity."""

    model_config = ConfigDict(frozen=True)

    node_id: str = Field(..., description="Unique node identifier")
    lineage_root_id: str = Field(..., description="Root lineage group ID")
    version: int = Field(..., description="Evolution version number")
    subject: str = Field(..., description="Subject entity")
    predicate: str = Field(..., description="Predicate relationship")
    object_value: str = Field(..., description="Object value")
    content: str = Field(..., description="Full text memory content")
    confidence: float = Field(default=1.0, description="Confidence score")
    status: MemoryNodeStatusEnum = Field(default=MemoryNodeStatusEnum.ACTIVE, description="Lifecycle status")
    created_at: str = Field(..., description="Creation timestamp ISO-8601")
    updated_at: str = Field(..., description="Update timestamp ISO-8601")
    source_session_id: str | None = Field(default=None, description="Optional session provenance")
    evidence_quote: str | None = Field(default=None, description="Verbatim citation anchor")
    metadata: dict[str, str] = Field(default_factory=dict, description="Custom string metadata")


class MemoryGraphEdgeDTO(BaseModel):
    """Directed multi-relational edge connecting memory nodes."""

    model_config = ConfigDict(frozen=True)

    edge_id: str = Field(..., description="Unique edge identifier")
    source_node_id: str = Field(..., description="Source node identifier")
    target_node_id: str = Field(..., description="Target node identifier")
    relation_type: LineageRelationTypeEnum = Field(..., description="Relation classification")
    weight: float = Field(default=1.0, description="Edge strength / confidence weight")
    rationale: str = Field(default="", description="Inference or supersession rationale")
    created_at: str = Field(..., description="Creation timestamp ISO-8601")


class LineageStepDTO(BaseModel):
    """Individual milestone step in memory evolution."""

    model_config = ConfigDict(frozen=True)

    step_index: int = Field(..., description="1-based step ordering")
    node: MemoryGraphNodeDTO = Field(..., description="Snapshot node at this step")
    relation_to_target: LineageRelationTypeEnum | None = Field(default=None, description="Relation to target")
    rationale: str = Field(default="", description="Step rationale")
    timestamp: str = Field(..., description="Step timestamp ISO-8601")


class MemoryLineageTrailDTO(BaseModel):
    """White-box lineage trace across historical roots and downstream dependents."""

    model_config = ConfigDict(frozen=True)

    target_node: MemoryGraphNodeDTO = Field(..., description="Analyzed node")
    lineage_root_id: str = Field(..., description="Root lineage identifier")
    ancestor_nodes: list[MemoryGraphNodeDTO] = Field(default_factory=list, description="Historical ancestor nodes")
    descendant_nodes: list[MemoryGraphNodeDTO] = Field(default_factory=list, description="Downstream superseded nodes")
    steps: list[LineageStepDTO] = Field(default_factory=list, description="Milestone progression steps")
    relation_edges: list[MemoryGraphEdgeDTO] = Field(default_factory=list, description="Involved relational edges")
    depth: int = Field(default=0, description="Total lineage depth")
    is_latest: bool = Field(default=True, description="Whether this node is current latest active version")


class ReorganizationBatchRequest(BaseModel):
    """Request payload to trigger graph reorganization edge generation."""

    model_config = ConfigDict(frozen=True)

    min_confidence: float = Field(default=0.8, ge=0.0, le=1.0, description="Minimum confidence threshold")


class ReorganizationBatchResponse(BaseModel):
    """Summary response for graph reorganization execution."""

    model_config = ConfigDict(frozen=True)

    batch_id: str = Field(..., description="Batch execution identifier")
    analyzed_nodes_count: int = Field(..., description="Total active nodes evaluated")
    created_edges_count: int = Field(..., description="New edges synthesized")
    superseded_nodes_count: int = Field(..., description="Nodes marked superseded")
    deductions_count: int = Field(..., description="Deduction edges synthesized")
    edges: list[MemoryGraphEdgeDTO] = Field(default_factory=list, description="Generated relational edges")
    created_at: str = Field(..., description="Completion timestamp ISO-8601")


class LineageRevertRequest(BaseModel):
    """Payload to execute atomic historical version rollback."""

    model_config = ConfigDict(frozen=True)

    historical_node_id: str = Field(..., description="Historical version node identifier to restore")
    rationale: str = Field(default="Rollback to historical version", description="Audit rationale for reversion")


class LineageRevertResponse(BaseModel):
    """Outcome of historical rollback operation."""

    model_config = ConfigDict(frozen=True)

    reverted_node: MemoryGraphNodeDTO = Field(..., description="Previous active node marked reverted")
    restored_active_node: MemoryGraphNodeDTO = Field(..., description="Newly spawned active successor node")


class MemoryTopologyGraphDTO(BaseModel):
    """Complete graph topology for visualization."""

    model_config = ConfigDict(frozen=True)

    nodes: list[MemoryGraphNodeDTO] = Field(default_factory=list, description="Graph nodes")
    edges: list[MemoryGraphEdgeDTO] = Field(default_factory=list, description="Graph edges")


class LineageStatsDTO(BaseModel):
    """Overall lineage system statistics."""

    model_config = ConfigDict(frozen=True)

    total_nodes: int = Field(..., description="Total memory nodes across all statuses")
    active_nodes: int = Field(..., description="Currently active memory nodes")
    superseded_nodes: int = Field(..., description="Historical superseded memory nodes")
    reverted_nodes: int = Field(..., description="Reverted memory nodes")
    total_edges: int = Field(..., description="Total relational edges")
    max_depth: int = Field(default=1, description="Deepest lineage branch depth")
