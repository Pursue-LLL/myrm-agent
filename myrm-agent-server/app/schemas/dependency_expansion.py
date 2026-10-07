"""
[POS] app/schemas/dependency_expansion.py
[INPUT] pydantic
[OUTPUT] ArchitectureNodeDTO, DependencyEdgeDTO, RegisterArchitectureNodeRequestDTO, RegisterDependencyEdgeRequestDTO, ExpandDependenciesRequestDTO, DependencyGraphExpansionResponseDTO, ClassifyComplexityRequestDTO, TaskComplexityClassificationResponseDTO

Pydantic DTOs for Architectural Dependency Expansion and Adaptive Complexity Dual-Track Scheduler suite.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field


class ArchitectureNodeDTO(BaseModel):
    """Data transfer object representing a cross-stack architectural entity node."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., description="Unique entity identifier")
    node_type: str = Field(
        ...,
        description="Node type: component, dependency, api, data_model, architectural_decision",
    )
    name: str = Field(..., description="Human-readable entity name or symbol")
    file_path: str = Field(default="", description="Source file path if applicable")
    description: str = Field(default="", description="Detailed functional description or role")
    metadata: dict[str, str] = Field(
        default_factory=dict, description="Arbitrary string metadata"
    )


class DependencyEdgeDTO(BaseModel):
    """Data transfer object representing a dependency edge between architectural entities."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    edge_type: str = Field(
        ...,
        description="Edge type: calls, depends_on, exposes_api, binds_model, constrained_by, rejected_alternative",
    )
    description: str = Field(default="", description="Edge rationale or contract note")


class RegisterArchitectureNodeRequestDTO(BaseModel):
    """Payload to register an architectural node in the graph."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., description="Unique node ID")
    node_type: str = Field(
        default="component",
        description="Node type: component, dependency, api, data_model, architectural_decision",
    )
    name: str = Field(..., description="Entity name")
    file_path: str = Field(default="", description="File path")
    description: str = Field(default="", description="Description")
    metadata: dict[str, str] = Field(default_factory=dict, description="Metadata")


class RegisterDependencyEdgeRequestDTO(BaseModel):
    """Payload to link two architectural nodes with a typed dependency edge."""

    model_config = ConfigDict(extra="forbid")

    source_id: str = Field(..., description="Source node ID")
    target_id: str = Field(..., description="Target node ID")
    edge_type: str = Field(
        default="calls",
        description="Edge type: calls, depends_on, exposes_api, binds_model, constrained_by, rejected_alternative",
    )
    description: str = Field(default="", description="Edge description")


class ExpandDependenciesRequestDTO(BaseModel):
    """Payload to trigger cascade dependency expansion from a target node."""

    model_config = ConfigDict(extra="forbid")

    target_node_id: str = Field(..., description="Target starting node ID")
    max_depth: int = Field(default=3, ge=1, le=10, description="Max traversal depth")


class DependencyGraphExpansionResponseDTO(BaseModel):
    """Response containing cascaded nodes, blast radius, constraints, and formatted block."""

    model_config = ConfigDict(extra="forbid")

    target_node_id: str = Field(..., description="Starting node ID")
    visited_nodes: list[ArchitectureNodeDTO] = Field(
        default_factory=list, description="All traversed nodes across stack"
    )
    blast_radius_score: float = Field(
        ..., ge=0.0, le=100.0, description="Calculated impact score"
    )
    critical_constraints: list[str] = Field(
        default_factory=list, description="Governing architecture constraints extracted"
    )
    rejected_alternatives: list[str] = Field(
        default_factory=list, description="Rejected alternatives and anti-patterns"
    )
    formatted_expansion_block: str = Field(
        ..., description="Markdown block formatted for context injection"
    )


class ClassifyComplexityRequestDTO(BaseModel):
    """Payload to classify task complexity and determine routing track."""

    model_config = ConfigDict(extra="forbid")

    task_prompt: str = Field(..., description="User prompt or instruction")
    target_components_or_files: list[str] = Field(
        default_factory=list, description="Target components or file paths"
    )
    is_multi_turn_project_session: bool = Field(
        default=False, description="Whether currently inside long-term project session"
    )


class TaskComplexityClassificationResponseDTO(BaseModel):
    """Response reflecting adaptive dual-track scheduling decision."""

    model_config = ConfigDict(extra="forbid")

    track: str = Field(..., description="Chosen track: fast_lean or full_workbench")
    reason: str = Field(..., description="Reasoning rationale behind classification")
    estimated_token_overhead: int = Field(
        ..., ge=0, description="Estimated context token overhead"
    )
    bypass_state_sync: bool = Field(
        ..., description="True if heavy state synchronization can be safely bypassed"
    )
