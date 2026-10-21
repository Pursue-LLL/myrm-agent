"""Service layer for SwarmForge Dynamic Topology Orchestrator & MultiGent Mesh Network (Item 55).

[INPUT]
- CreateTopologyRequest, SwitchTopologyRequest, ScaleNodesRequest,
  MigrateNodeRequest, SendMeshMessageRequest, WriteBlackboardRequest.

[OUTPUT]
- SwarmTopologyStateDTO, MigrationResultDTO, MeshMessageDTO, BlackboardEntryDTO.

[POS]
- Encapsulates lifecycle orchestration, mesh bus communication, shared blackboard,
  and dynamic topology reconfiguration for multi-agent swarms.
"""

from __future__ import annotations

import logging
from typing import TYPE_CHECKING

from app.schemas.swarm_mesh import (
    BlackboardEntryDTO,
    CreateTopologyRequest,
    MeshDeliveryStatusEnum,
    MeshEdgeDTO,
    MeshMessageDTO,
    MessageRoutingModeEnum,
    MigrateNodeRequest,
    MigrationResultDTO,
    ScaleNodesRequest,
    SendMeshMessageRequest,
    SwarmNodeDTO,
    SwarmNodeRoleEnum,
    SwarmNodeStatusEnum,
    SwarmTopologyStateDTO,
    SwitchTopologyRequest,
    TopologyTypeEnum,
    WriteBlackboardRequest,
)

if TYPE_CHECKING:
    from myrm_agent_harness.agent.sub_agents.swarm_mesh import (
        BlackboardEntry,
        MeshEdge,
        MeshMessage,
        SwarmNode,
        SwarmTopologyState,
    )

logger = logging.getLogger(__name__)


class SwarmMeshService:
    """Manages swarm topology orchestration, mesh messaging, and blackboard state."""

    def __init__(self) -> None:
        self._orchestrators: dict[str, object] = {}
        self._default_topology_id = "swarm-primary"

    def _get_or_create_orchestrator(self, topology_id: str | None = None) -> object:
        from myrm_agent_harness.agent.sub_agents.swarm_mesh import (
            SwarmTopologyConfig,
            SwarmTopologyOrchestrator,
            TopologyType,
        )

        tid = topology_id or self._default_topology_id
        if tid not in self._orchestrators:
            cfg = SwarmTopologyConfig(
                topology_id=tid,
                topology_type=TopologyType.STAR,
                max_nodes=16,
                is_adaptive=True,
            )
            self._orchestrators[tid] = SwarmTopologyOrchestrator(cfg)
        return self._orchestrators[tid]

    def _convert_node_to_dto(self, node: SwarmNode) -> SwarmNodeDTO:
        return SwarmNodeDTO(
            node_id=node.node_id,
            name=node.name,
            role=SwarmNodeRoleEnum(node.role.value),
            status=SwarmNodeStatusEnum(node.status.value),
            capabilities=list(node.capabilities),
            connected_peers=list(node.connected_peers),
            workload_score=node.workload_score,
            meta=dict(node.meta),
        )

    def _convert_edge_to_dto(self, edge: MeshEdge) -> MeshEdgeDTO:
        return MeshEdgeDTO(
            source=edge.source,
            target=edge.target,
            bidirectional=edge.bidirectional,
            weight=edge.weight,
        )

    def _convert_blackboard_entry_to_dto(self, entry: BlackboardEntry) -> BlackboardEntryDTO:
        return BlackboardEntryDTO(
            key=entry.key,
            value=entry.value,
            author_id=entry.author_id,
            version=entry.version,
            updated_at=entry.updated_at,
            tags=list(entry.tags),
        )

    def _convert_message_to_dto(self, msg: MeshMessage) -> MeshMessageDTO:
        return MeshMessageDTO(
            message_id=msg.message_id,
            sender_id=msg.sender_id,
            recipient_id=msg.recipient_id,
            routing_mode=MessageRoutingModeEnum(msg.routing_mode.value),
            channel=msg.channel,
            payload=dict(msg.payload),
            timestamp=msg.timestamp,
            delivery_status=MeshDeliveryStatusEnum(msg.delivery_status.value),
        )

    def _convert_state_to_dto(self, state: SwarmTopologyState) -> SwarmTopologyStateDTO:
        return SwarmTopologyStateDTO(
            topology_id=state.topology_id,
            topology_type=TopologyTypeEnum(state.topology_type.value),
            nodes={nid: self._convert_node_to_dto(n) for nid, n in state.nodes.items()},
            edges=[self._convert_edge_to_dto(e) for e in state.edges],
            blackboard={k: self._convert_blackboard_entry_to_dto(v) for k, v in state.blackboard.items()},
            recent_messages=[self._convert_message_to_dto(m) for m in state.recent_messages],
            is_adaptive=state.is_adaptive,
        )

    def get_topology_state(self, topology_id: str | None = None) -> SwarmTopologyStateDTO:
        """Fetch the current topology state and active mesh configuration."""
        orch = self._get_or_create_orchestrator(topology_id)
        return self._convert_state_to_dto(orch.state)  # type: ignore[attr-defined]

    def create_topology(self, req: CreateTopologyRequest) -> SwarmTopologyStateDTO:
        """Instantiate a new swarm topology with desired layout and parameters."""
        from myrm_agent_harness.agent.sub_agents.swarm_mesh import (
            SwarmTopologyConfig,
            SwarmTopologyOrchestrator,
            TopologyType,
        )

        tid = f"swarm-{req.topology_type.value}"
        cfg = SwarmTopologyConfig(
            topology_id=tid,
            topology_type=TopologyType(req.topology_type.value),
            max_nodes=req.max_nodes,
            is_adaptive=req.is_adaptive,
        )
        orch = SwarmTopologyOrchestrator(cfg)
        self._orchestrators[tid] = orch
        self._default_topology_id = tid
        return self._convert_state_to_dto(orch.state)

    def switch_topology(
        self,
        req: SwitchTopologyRequest,
        topology_id: str | None = None,
    ) -> SwarmTopologyStateDTO:
        """Dynamically reconfigure the swarm layout while preserving active states."""
        from myrm_agent_harness.agent.sub_agents.swarm_mesh import TopologyType

        orch = self._get_or_create_orchestrator(topology_id)
        target_type = TopologyType(req.target_type.value)
        updated_state = orch.switch_topology(target_type)  # type: ignore[attr-defined]
        return self._convert_state_to_dto(updated_state)

    def scale_nodes(
        self,
        req: ScaleNodesRequest,
        topology_id: str | None = None,
    ) -> SwarmTopologyStateDTO:
        """Scale out or retire nodes in the dynamic swarm."""
        from myrm_agent_harness.agent.sub_agents.swarm_mesh import (
            SwarmNode,
            SwarmNodeRole,
            SwarmNodeStatus,
        )

        orch = self._get_or_create_orchestrator(topology_id)
        node_model = SwarmNode(
            node_id=req.node.node_id,
            name=req.node.name,
            role=SwarmNodeRole(req.node.role.value),
            status=SwarmNodeStatus(req.node.status.value),
            capabilities=list(req.node.capabilities),
            connected_peers=list(req.node.connected_peers),
            workload_score=req.node.workload_score,
            meta=dict(req.node.meta),
        )
        updated_state = orch.scale_nodes(req.action, node_model)  # type: ignore[attr-defined]
        return self._convert_state_to_dto(updated_state)

    def migrate_node(
        self,
        req: MigrateNodeRequest,
        topology_id: str | None = None,
    ) -> MigrationResultDTO:
        """Live-migrate an agent node to a different functional role."""
        from myrm_agent_harness.agent.sub_agents.swarm_mesh import (
            MigrationRequest,
            SwarmNodeRole,
        )

        orch = self._get_or_create_orchestrator(topology_id)
        request = MigrationRequest(
            node_id=req.node_id,
            target_role=SwarmNodeRole(req.target_role.value),
            state_diff=dict(req.state_diff),
            reason=req.reason,
        )
        res = orch.migrate_node(request)  # type: ignore[attr-defined]
        return MigrationResultDTO(
            migration_id=res.migration_id,
            node_id=res.node_id,
            success=res.success,
            previous_role=SwarmNodeRoleEnum(res.previous_role.value),
            current_role=SwarmNodeRoleEnum(res.current_role.value),
            reconnected_peers=list(res.reconnected_peers),
            details=res.details,
        )

    def send_mesh_message(
        self,
        req: SendMeshMessageRequest,
        topology_id: str | None = None,
    ) -> MeshMessageDTO:
        """Dispatch a message over the P2P mesh bus."""
        from myrm_agent_harness.agent.sub_agents.swarm_mesh import MessageRoutingMode

        orch = self._get_or_create_orchestrator(topology_id)
        msg = orch.send_mesh_message(  # type: ignore[attr-defined]
            sender_id=req.sender_id,
            recipient_id=req.recipient_id,
            routing_mode=MessageRoutingMode(req.routing_mode.value),
            channel=req.channel,
            payload=dict(req.payload),
        )
        return self._convert_message_to_dto(msg)

    def get_blackboard(
        self,
        key: str | None = None,
        topology_id: str | None = None,
    ) -> dict[str, BlackboardEntryDTO]:
        """Fetch shared blackboard facts."""
        orch = self._get_or_create_orchestrator(topology_id)
        entries = orch.read_blackboard(key)  # type: ignore[attr-defined]
        return {k: self._convert_blackboard_entry_to_dto(v) for k, v in entries.items()}

    def write_blackboard(
        self,
        req: WriteBlackboardRequest,
        topology_id: str | None = None,
    ) -> BlackboardEntryDTO:
        """Write or update a fact in the shared blackboard."""
        orch = self._get_or_create_orchestrator(topology_id)
        entry = orch.write_blackboard(  # type: ignore[attr-defined]
            key=req.key,
            value=req.value,
            author_id=req.author_id,
            tags=list(req.tags),
        )
        return self._convert_blackboard_entry_to_dto(entry)


_instance: SwarmMeshService | None = None


def get_swarm_mesh_service() -> SwarmMeshService:
    """Retrieve the singleton instance of SwarmMeshService."""
    global _instance
    if _instance is None:
        _instance = SwarmMeshService()
    return _instance
