"""Socket Mesh Service coordinating peer discovery, atomic envelopes, and local IPC routing."""

from __future__ import annotations

import os
from typing import Dict, List, Optional, Tuple

from myrm_agent_harness.agent.sub_agents.socket_mesh import (
    Envelope,
    EnvelopeType,
    MeshRegistry,
    PeerStatus,
    RegistryEntry,
    SocketMeshNode,
)

from app.schemas.socket_mesh import (
    AwaitResponseDTO,
    EnvelopeDispatchResponseDTO,
    MeshAuditLogDTO,
    PeerInfoDTO,
    PeerRegisterRequestDTO,
    PeerStatusEnum,
    PingResponseDTO,
)


class SocketMeshService:
    """Singleton service managing peer-to-peer agent mesh networks across projects."""

    _instance: Optional[SocketMeshService] = None

    def __init__(self, base_dir: Optional[str] = None) -> None:
        self.registry = MeshRegistry(base_dir=base_dir)
        # Key: (project, name) -> SocketMeshNode
        self._nodes: Dict[Tuple[str, str], SocketMeshNode] = {}

    @classmethod
    def get_instance(cls, base_dir: Optional[str] = None) -> SocketMeshService:
        """Get or initialize singleton instance."""
        if cls._instance is None:
            cls._instance = cls(base_dir=base_dir)
        return cls._instance

    @classmethod
    def reset_instance(cls) -> None:
        """Reset singleton instance (useful for clean unit testing)."""
        if cls._instance is not None:
            for node in list(cls._instance._nodes.values()):
                node.stop()
            cls._instance._nodes.clear()
        cls._instance = None

    def get_or_create_node(
        self,
        project: str,
        name: str,
        purpose: str = "General Task Agent",
        model: str = "default-model",
    ) -> SocketMeshNode:
        """Retrieve existing active node or instantiate and start a new one."""
        key = (project, name)
        if key in self._nodes and self._nodes[key].is_running:
            return self._nodes[key]

        node = SocketMeshNode(
            name=name,
            project=project,
            purpose=purpose,
            model=model,
            registry=self.registry,
        )
        node.start()
        self._nodes[key] = node
        return node

    def register_peer(self, project: str, req: PeerRegisterRequestDTO) -> PeerInfoDTO:
        """Register or update an agent node in the specified project mesh."""
        node = self.get_or_create_node(
            project=project,
            name=req.name,
            purpose=req.purpose,
            model=req.model,
        )
        node.context_used_pct = req.context_used_pct
        node.queue_depth = req.queue_depth

        entry = RegistryEntry(
            session_id=node.session_id,
            name=node.name,
            purpose=node.purpose,
            model=node.model,
            pid=req.pid or os.getpid(),
            endpoint=node.endpoint,
            cwd=node.cwd,
            started_at=node.registry.get_peer(project, req.name).started_at if node.registry.get_peer(project, req.name) else 0.0,
            heartbeat_at=0.0,
            context_used_pct=req.context_used_pct,
            queue_depth=req.queue_depth,
            status=PeerStatus.ONLINE,
        )
        saved = self.registry.register_peer(project, entry)
        return self._entry_to_dto(saved)

    def unregister_peer(self, project: str, name: str) -> bool:
        """Unregister an agent and tear down its active node."""
        key = (project, name)
        if key in self._nodes:
            self._nodes[key].stop()
            self._nodes.pop(key, None)
            return True
        return self.registry.unregister_peer(project, name)

    def list_peers(self, project: str, auto_mark_stale: bool = True) -> List[PeerInfoDTO]:
        """List all discovered peers in a project."""
        peers = self.registry.list_peers(project, auto_mark_stale=auto_mark_stale)
        return [self._entry_to_dto(p) for p in peers]

    def get_peer(self, project: str, name: str) -> Optional[PeerInfoDTO]:
        """Get details of a single peer by name."""
        peer = self.registry.get_peer(project, name)
        return self._entry_to_dto(peer) if peer else None

    async def send_message(
        self,
        project: str,
        sender_name: str,
        target_name: str,
        prompt: str,
        timeout_seconds: float = 30.0,
    ) -> EnvelopeDispatchResponseDTO:
        """Dispatch a prompt envelope from sender to target."""
        sender_node = self.get_or_create_node(project, sender_name)
        res = await sender_node.coms_send(
            target_name=target_name,
            prompt=prompt,
            timeout_seconds=timeout_seconds,
        )
        return EnvelopeDispatchResponseDTO(
            success=res.success,
            msg_id=res.msg_id,
            hops=res.hops,
            duration_ms=res.duration_ms,
            error=res.error,
        )

    async def await_reply(
        self,
        project: str,
        sender_name: str,
        msg_id: str,
        timeout_seconds: float = 30.0,
    ) -> AwaitResponseDTO:
        """Wait for response envelope matching a previously dispatched message ID."""
        sender_node = self.get_or_create_node(project, sender_name)
        res = await sender_node.coms_await(msg_id=msg_id, timeout_seconds=timeout_seconds)
        return AwaitResponseDTO(
            success=res.success,
            msg_id=res.msg_id,
            response=res.response,
            error=res.error,
            hops=res.hops,
            duration_ms=res.duration_ms,
        )

    async def reply_message(
        self,
        project: str,
        responder_name: str,
        msg_id: str,
        response_text: str,
        error: Optional[str] = None,
    ) -> EnvelopeDispatchResponseDTO:
        """Reply to an inbound message from responder to original sender."""
        responder_node = self.get_or_create_node(project, responder_name)

        # Locate the inbound envelope on responder node
        matching_inbound = next(
            (env for env in responder_node._inbound_messages if env.msg_id == msg_id),
            None,
        )

        if not matching_inbound:
            # Reconstruct fallback envelope if not in memory
            matching_inbound = Envelope(
                msg_id=msg_id,
                type=EnvelopeType.PROMPT,
                sender_name="unknown",
                target_name=responder_name,
                hops=0,
            )

        res = await responder_node.coms_reply(
            inbound_envelope=matching_inbound,
            response_text=response_text,
            error=error,
        )
        return EnvelopeDispatchResponseDTO(
            success=res.success,
            msg_id=res.msg_id,
            hops=res.hops,
            error=res.error,
            duration_ms=res.duration_ms,
        )

    async def ping_peer(
        self,
        project: str,
        sender_name: str,
        target_name: str,
        timeout_seconds: float = 5.0,
    ) -> PingResponseDTO:
        """Ping a target peer to verify health and retrieve its AgentCard."""
        sender_node = self.get_or_create_node(project, sender_name)
        res = await sender_node.coms_ping(target_name, timeout_seconds=timeout_seconds)
        return PingResponseDTO(
            success=res.success,
            msg_id=res.msg_id,
            response=res.response,
            error=res.error,
            duration_ms=res.duration_ms,
        )

    def get_audit_logs(self, project: str) -> List[MeshAuditLogDTO]:
        """Aggregate audit logs from all nodes in the given project."""
        logs: List[MeshAuditLogDTO] = []
        for (proj, _), node in self._nodes.items():
            if proj == project:
                for entry in node.get_audit_logs():
                    logs.append(
                        MeshAuditLogDTO(
                            timestamp=float(entry.get("timestamp", 0.0)),
                            event_type=str(entry.get("event_type", "")),
                            node=str(entry.get("node", "")),
                            project=str(entry.get("project", "")),
                            detail=str(entry.get("detail", "")),
                        )
                    )
        logs.sort(key=lambda x: x.timestamp)
        return logs

    def cleanup_stale_peers(self, project: str, max_age_seconds: float = 300.0) -> int:
        """Clean up inactive stale peers from the project registry."""
        return self.registry.cleanup_stale_peers(project, max_age_seconds=max_age_seconds)

    def _entry_to_dto(self, entry: RegistryEntry) -> PeerInfoDTO:
        """Map internal RegistryEntry to external Pydantic DTO."""
        return PeerInfoDTO(
            session_id=entry.session_id,
            name=entry.name,
            purpose=entry.purpose,
            model=entry.model,
            pid=entry.pid,
            endpoint=entry.endpoint,
            cwd=entry.cwd,
            started_at=entry.started_at,
            heartbeat_at=entry.heartbeat_at,
            context_used_pct=entry.context_used_pct,
            queue_depth=entry.queue_depth,
            status=PeerStatusEnum(entry.status.value),
        )


def get_socket_mesh_service() -> SocketMeshService:
    """Dependency provider for FastAPI route injection."""
    return SocketMeshService.get_instance()
