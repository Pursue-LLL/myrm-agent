"""
[POS] app/services/agent/device_mesh_service.py
[INPUT] threading, myrm_agent_harness.agent.sub_agents.device_mesh, app.schemas.device_mesh
[OUTPUT] DeviceMeshService, get_device_mesh_service

Service layer governing edge device mesh topology, node pairing, live telemetry heartbeats, and workload command dispatch.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import threading
from typing import cast

from myrm_agent_harness.agent.sub_agents.device_mesh import (
    DeviceNodeKind,
    DeviceNodeStatus,
    DeviceTelemetry,
    DispatchCommandRequest,
    EdgeDeviceMeshScheduler,
    MeshDeviceNode,
)

from app.schemas.device_mesh import (
    DeviceHeartbeatRequestDTO,
    DeviceNodeKindLiteral,
    DeviceNodeListResponseDTO,
    DeviceNodeStatusLiteral,
    DeviceTelemetryDTO,
    DispatchCommandRequestDTO,
    DispatchCommandResponseDTO,
    MeshDeviceNodeDTO,
    PairDeviceNodeRequestDTO,
    RegisterDeviceNodeRequestDTO,
)


def _node_to_dto(node: MeshDeviceNode) -> MeshDeviceNodeDTO:
    """Map internal Harness MeshDeviceNode dataclass to public Pydantic DTO."""
    return MeshDeviceNodeDTO(
        node_id=node.node_id,
        name=node.name,
        kind=cast(DeviceNodeKindLiteral, node.kind),
        ip_or_hostname=node.ip_or_hostname,
        status=cast(DeviceNodeStatusLiteral, node.status),
        pairing_token=node.pairing_token,
        capabilities=list(node.capabilities),
        telemetry=DeviceTelemetryDTO(
            cpu_usage_pct=node.telemetry.cpu_usage_pct,
            memory_usage_pct=node.telemetry.memory_usage_pct,
            gpu_usage_pct=node.telemetry.gpu_usage_pct,
            uptime_seconds=node.telemetry.uptime_seconds,
            active_tasks=node.telemetry.active_tasks,
        ),
        last_heartbeat=node.last_heartbeat,
        created_at=node.created_at,
    )


class DeviceMeshService:
    """Business service governing distributed edge device mesh orchestration."""

    def __init__(self, scheduler: EdgeDeviceMeshScheduler | None = None) -> None:
        self._scheduler = scheduler or EdgeDeviceMeshScheduler(stale_timeout_seconds=60.0)

    def register_node(self, req: RegisterDeviceNodeRequestDTO) -> MeshDeviceNodeDTO:
        """Register a new edge device node into the mesh topology."""
        node = self._scheduler.register_node(
            node_id=req.node_id,
            name=req.name,
            kind=cast(DeviceNodeKind, req.kind),
            ip_or_hostname=req.ip_or_hostname,
            capabilities=req.capabilities,
            pairing_token=req.pairing_token,
            auto_pair=req.auto_pair,
        )
        return _node_to_dto(node)

    def pair_node(self, node_id: str, req: PairDeviceNodeRequestDTO) -> MeshDeviceNodeDTO:
        """Pair an unpaired device node using verification token."""
        success = self._scheduler.pair_node(node_id, req.pairing_token)
        if not success:
            raise ValueError(f"Pairing failed for node '{node_id}'. Invalid token or node missing.")
        node = self._scheduler.get_node(node_id)
        if node is None:
            raise KeyError(f"Device node '{node_id}' not found.")
        return _node_to_dto(node)

    def heartbeat(self, node_id: str, req: DeviceHeartbeatRequestDTO) -> MeshDeviceNodeDTO:
        """Process periodic heartbeat pulse with optional telemetry snapshot."""
        telemetry: DeviceTelemetry | None = None
        if req.telemetry is not None:
            telemetry = DeviceTelemetry(
                cpu_usage_pct=req.telemetry.cpu_usage_pct,
                memory_usage_pct=req.telemetry.memory_usage_pct,
                gpu_usage_pct=req.telemetry.gpu_usage_pct,
                uptime_seconds=req.telemetry.uptime_seconds,
                active_tasks=req.telemetry.active_tasks,
            )
        node = self._scheduler.heartbeat(node_id, telemetry=telemetry)
        return _node_to_dto(node)

    def get_node(self, node_id: str) -> MeshDeviceNodeDTO | None:
        """Fetch details of an edge device node by ID."""
        node = self._scheduler.get_node(node_id)
        if node is None:
            return None
        return _node_to_dto(node)

    def list_nodes(
        self,
        kind: str | None = None,
        status: str | None = None,
    ) -> DeviceNodeListResponseDTO:
        """List registered edge device nodes matching optional filters."""
        k_val = cast(DeviceNodeKind, kind) if kind else None
        s_val = cast(DeviceNodeStatus, status) if status else None
        nodes = self._scheduler.list_nodes(kind=k_val, status=s_val)
        dtos = [_node_to_dto(n) for n in nodes]
        return DeviceNodeListResponseDTO(nodes=dtos, total_count=len(dtos))

    def dispatch_command(self, req: DispatchCommandRequestDTO) -> DispatchCommandResponseDTO:
        """Dispatch a workload or diagnostic command to an edge node."""
        harness_req = DispatchCommandRequest(
            node_id=req.node_id,
            command=req.command,
            timeout_seconds=req.timeout_seconds,
            environment=req.environment,
        )
        res = self._scheduler.dispatch_command(harness_req)
        return DispatchCommandResponseDTO(
            task_id=res.task_id,
            node_id=res.node_id,
            exit_code=res.exit_code,
            stdout=res.stdout,
            stderr=res.stderr,
            duration_seconds=res.duration_seconds,
            success=res.success,
            dispatched_at=res.dispatched_at,
        )

    def remove_node(self, node_id: str) -> bool:
        """Remove a node from the mesh registry."""
        return self._scheduler.remove_node(node_id)


_DEVICE_MESH_SERVICE_INSTANCE: DeviceMeshService | None = None
_DEVICE_MESH_SERVICE_LOCK = threading.Lock()


def get_device_mesh_service() -> DeviceMeshService:
    """Singleton provider for DeviceMeshService."""
    global _DEVICE_MESH_SERVICE_INSTANCE
    if _DEVICE_MESH_SERVICE_INSTANCE is None:
        with _DEVICE_MESH_SERVICE_LOCK:
            if _DEVICE_MESH_SERVICE_INSTANCE is None:
                _DEVICE_MESH_SERVICE_INSTANCE = DeviceMeshService()
    return _DEVICE_MESH_SERVICE_INSTANCE
