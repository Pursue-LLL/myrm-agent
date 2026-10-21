"""Pydantic V2 schemas for SwarmForge Dynamic Topology Orchestrator & Mesh Bus (Item 55).

[INPUT]
- CreateTopologyRequest, SwitchTopologyRequest, ScaleNodesRequest,
  MigrateNodeRequest, SendMeshMessageRequest, WriteBlackboardRequest.

[OUTPUT]
- SwarmNodeDTO, MeshEdgeDTO, MeshMessageDTO, BlackboardEntryDTO,
  SwarmTopologyStateDTO, MigrationResultDTO.

[POS]
- Server-side typed DTO schemas for dynamic topology orchestration, mesh messaging,
  and blackboard management.
"""

from __future__ import annotations

import enum

from pydantic import BaseModel, ConfigDict, Field


class TopologyTypeEnum(enum.StrEnum):
    """Supported swarm topology architectures."""

    STAR = "star"
    HIERARCHICAL_TREE = "hierarchical_tree"
    PEER_MESH = "peer_mesh"
    PIPELINE = "pipeline"
    RING = "ring"


class SwarmNodeRoleEnum(enum.StrEnum):
    """Operational roles of swarm participant nodes."""

    COORDINATOR = "coordinator"
    WORKER = "worker"
    REVIEWER = "reviewer"
    SPECIALIST = "specialist"
    GATEWAY = "gateway"


class SwarmNodeStatusEnum(enum.StrEnum):
    """Operational lifecycle status of swarm nodes."""

    IDLE = "idle"
    ACTIVE = "active"
    BUSY = "busy"
    MIGRATING = "migrating"
    DEGRADED = "degraded"
    OFFLINE = "offline"


class MessageRoutingModeEnum(enum.StrEnum):
    """Routing distribution modes in the mesh bus."""

    UNICAST = "unicast"
    MULTICAST = "multicast"
    BROADCAST = "broadcast"


class MeshDeliveryStatusEnum(enum.StrEnum):
    """Transmission delivery status of mesh messages."""

    SENT = "sent"
    DELIVERED = "delivered"
    ACKNOWLEDGED = "acknowledged"
    FAILED = "failed"


class MeshEdgeDTO(BaseModel):
    """Edge representation of an interconnected communication link between nodes."""

    model_config = ConfigDict(frozen=True)

    source: str = Field(..., description="Source node identifier")
    target: str = Field(..., description="Target node identifier")
    bidirectional: bool = Field(True, description="Whether connection is full-duplex")
    weight: float = Field(1.0, description="Routing link cost weight")


class SwarmNodeDTO(BaseModel):
    """Node state participating in the dynamic swarm."""

    model_config = ConfigDict(extra="ignore")

    node_id: str = Field(..., description="Unique node identifier")
    name: str = Field(..., description="Human-readable node label")
    role: SwarmNodeRoleEnum = Field(..., description="Functional role")
    status: SwarmNodeStatusEnum = Field(SwarmNodeStatusEnum.IDLE, description="Operational state")
    capabilities: list[str] = Field(default_factory=list, description="Supported skill tags")
    connected_peers: list[str] = Field(default_factory=list, description="Currently connected peer node IDs")
    workload_score: float = Field(0.0, description="Normalized workload consumption")
    meta: dict[str, str] = Field(default_factory=dict, description="Custom node context metadata")


class MeshMessageDTO(BaseModel):
    """Message payload delivered through the P2P mesh bus."""

    model_config = ConfigDict(frozen=True)

    message_id: str = Field(..., description="Message UUID")
    sender_id: str = Field(..., description="Origin node identifier")
    recipient_id: str = Field(..., description="Target node identifier or broadcast wildcard")
    routing_mode: MessageRoutingModeEnum = Field(..., description="Unicast, multicast, or broadcast")
    channel: str = Field(..., description="Topic or channel classification")
    payload: dict[str, str | int | float | bool] = Field(default_factory=dict, description="Typed payload")
    timestamp: float = Field(..., description="Transmission epoch timestamp")
    delivery_status: MeshDeliveryStatusEnum = Field(
        MeshDeliveryStatusEnum.DELIVERED,
        description="Delivery confirmation status",
    )


class BlackboardEntryDTO(BaseModel):
    """Shared blackboard key-value fact entry."""

    model_config = ConfigDict(frozen=True)

    key: str = Field(..., description="Unique fact key identifier")
    value: str = Field(..., description="Fact content representation")
    author_id: str = Field(..., description="Author node identifier")
    version: int = Field(1, description="Monotonically increasing version counter")
    updated_at: float = Field(..., description="Last update epoch timestamp")
    tags: list[str] = Field(default_factory=list, description="Categorization tags")


class SwarmTopologyStateDTO(BaseModel):
    """Complete snapshot of the swarm topology, nodes, edges, messages, and facts."""

    model_config = ConfigDict(extra="ignore")

    topology_id: str = Field(..., description="Swarm topology instance ID")
    topology_type: TopologyTypeEnum = Field(..., description="Current active topology structure")
    nodes: dict[str, SwarmNodeDTO] = Field(default_factory=dict, description="Active swarm nodes")
    edges: list[MeshEdgeDTO] = Field(default_factory=list, description="Network connection edges")
    blackboard: dict[str, BlackboardEntryDTO] = Field(default_factory=dict, description="Shared facts blackboard")
    recent_messages: list[MeshMessageDTO] = Field(default_factory=list, description="Recent mesh messages")
    is_adaptive: bool = Field(True, description="Whether automatic topology adaptation is enabled")


class CreateTopologyRequest(BaseModel):
    """Request payload to instantiate or reset a swarm topology."""

    topology_type: TopologyTypeEnum = Field(TopologyTypeEnum.STAR, description="Desired topology layout")
    max_nodes: int = Field(16, ge=2, le=64, description="Maximum node capacity")
    is_adaptive: bool = Field(True, description="Enable dynamic runtime adaptation")


class SwitchTopologyRequest(BaseModel):
    """Request payload to dynamically reconfigure the topology structure."""

    target_type: TopologyTypeEnum = Field(..., description="Target topology layout")


class ScaleNodesRequest(BaseModel):
    """Request payload to scale out or scale in nodes."""

    action: str = Field(..., description="'scale_out' to add, 'scale_in' to retire")
    node: SwarmNodeDTO = Field(..., description="Node specification to add or remove")


class MigrateNodeRequest(BaseModel):
    """Request payload to live-migrate a node to a different role with state preservation."""

    node_id: str = Field(..., description="Target node to migrate")
    target_role: SwarmNodeRoleEnum = Field(..., description="New role assignment")
    state_diff: dict[str, str] = Field(default_factory=dict, description="State delta to merge into node meta")
    reason: str = Field("", description="Justification for role migration")


class SendMeshMessageRequest(BaseModel):
    """Request payload to send a message over the P2P mesh bus."""

    sender_id: str = Field(..., description="Origin node identifier")
    recipient_id: str = Field("*", description="Destination node identifier or '*' for broadcast")
    routing_mode: MessageRoutingModeEnum = Field(
        MessageRoutingModeEnum.BROADCAST,
        description="Routing distribution mode",
    )
    channel: str = Field("general", description="Target topic channel")
    payload: dict[str, str | int | float | bool] = Field(default_factory=dict, description="Message data")


class WriteBlackboardRequest(BaseModel):
    """Request payload to write or update a fact in the shared blackboard."""

    key: str = Field(..., description="Fact key identifier")
    value: str = Field(..., description="Fact value string")
    author_id: str = Field(..., description="Authoring node identifier")
    tags: list[str] = Field(default_factory=list, description="Optional search/filter tags")


class MigrationResultDTO(BaseModel):
    """Response payload detailing the outcome of a node migration."""

    model_config = ConfigDict(frozen=True)

    migration_id: str = Field(..., description="Migration event identifier")
    node_id: str = Field(..., description="Target node identifier")
    success: bool = Field(..., description="Whether migration completed successfully")
    previous_role: SwarmNodeRoleEnum = Field(..., description="Role prior to migration")
    current_role: SwarmNodeRoleEnum = Field(..., description="Role post migration")
    reconnected_peers: list[str] = Field(default_factory=list, description="Reconstructed peer connections")
    details: str = Field("", description="Execution details or error explanation")
