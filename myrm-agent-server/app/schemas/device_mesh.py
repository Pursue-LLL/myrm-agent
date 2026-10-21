"""
[POS] app/schemas/device_mesh.py
[INPUT] pydantic
[OUTPUT] DeviceTelemetryDTO, MeshDeviceNodeDTO, RegisterDeviceNodeRequestDTO, PairDeviceNodeRequestDTO, DeviceHeartbeatRequestDTO, DispatchCommandRequestDTO, DispatchCommandResponseDTO, DeviceNodeListResponseDTO

Pydantic schemas for Edge Device Mesh topology, node registration, telemetry, and distributed workload dispatch.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

import time
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field

DeviceNodeKindLiteral = Literal[
    "linux_server",
    "mac_mini",
    "raspberry_pi",
    "mobile_device",
    "edge_accelerator",
    "custom",
]

DeviceNodeStatusLiteral = Literal[
    "online",
    "offline",
    "busy",
    "unpaired",
]


class DeviceTelemetryDTO(BaseModel):
    """Real-time compute and task telemetry metrics from an edge node."""

    model_config = ConfigDict(extra="forbid")

    cpu_usage_pct: float = Field(ge=0.0, le=100.0, default=0.0, description="CPU utilization percentage")
    memory_usage_pct: float = Field(ge=0.0, le=100.0, default=0.0, description="Memory utilization percentage")
    gpu_usage_pct: float | None = Field(default=None, description="Optional GPU compute utilization percentage")
    uptime_seconds: float = Field(ge=0.0, default=0.0, description="System uptime in seconds")
    active_tasks: int = Field(ge=0, default=0, description="Concurrent workload tasks active on this node")


class MeshDeviceNodeDTO(BaseModel):
    """Full snapshot of an edge device node within the mesh topology."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, description="Unique node identifier")
    name: str = Field(..., min_length=1, description="Human readable device name")
    kind: DeviceNodeKindLiteral = Field(..., description="Hardware device kind")
    ip_or_hostname: str = Field(..., min_length=1, description="LAN IP address or network hostname")
    status: DeviceNodeStatusLiteral = Field(default="unpaired", description="Current node connectivity status")
    pairing_token: str = Field(default="", description="Authentication pairing token")
    capabilities: list[str] = Field(default_factory=list, description="Supported hardware capabilities")
    telemetry: DeviceTelemetryDTO = Field(default_factory=DeviceTelemetryDTO, description="Live telemetry metrics")
    last_heartbeat: float = Field(default_factory=time.time, description="Epoch timestamp of most recent heartbeat")
    created_at: float = Field(default_factory=time.time, description="Registration epoch timestamp")


class RegisterDeviceNodeRequestDTO(BaseModel):
    """Request payload to register a new edge device node."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, description="Unique node identifier")
    name: str = Field(..., min_length=1, description="Device label")
    kind: DeviceNodeKindLiteral = Field(..., description="Device kind")
    ip_or_hostname: str = Field(..., min_length=1, description="IP address or hostname")
    capabilities: list[str] = Field(default_factory=list, description="Declared capabilities")
    pairing_token: str = Field(default="", description="Initial pairing token")
    auto_pair: bool = Field(default=True, description="Whether to automatically mark as paired online if token provided")


class PairDeviceNodeRequestDTO(BaseModel):
    """Request payload to verify token and pair an unpaired device."""

    model_config = ConfigDict(extra="forbid")

    pairing_token: str = Field(..., min_length=1, description="Verification pairing token")


class DeviceHeartbeatRequestDTO(BaseModel):
    """Request payload for periodic edge node heartbeat pulse."""

    model_config = ConfigDict(extra="forbid")

    telemetry: DeviceTelemetryDTO | None = Field(default=None, description="Optional telemetry update")


class DispatchCommandRequestDTO(BaseModel):
    """Request payload to dispatch a shell command to an edge node."""

    model_config = ConfigDict(extra="forbid")

    node_id: str = Field(..., min_length=1, description="Target node identifier")
    command: str = Field(..., min_length=1, description="Command string to execute")
    timeout_seconds: float = Field(default=30.0, ge=1.0, le=300.0, description="Execution timeout")
    environment: dict[str, str] = Field(default_factory=dict, description="Environment variables")


class DispatchCommandResponseDTO(BaseModel):
    """Execution receipt returned from a dispatched command."""

    model_config = ConfigDict(extra="forbid")

    task_id: str = Field(..., description="Unique dispatched task ID")
    node_id: str = Field(..., description="Target node ID")
    exit_code: int = Field(..., description="Command exit code")
    stdout: str = Field(default="", description="Captured standard output")
    stderr: str = Field(default="", description="Captured standard error")
    duration_seconds: float = Field(..., description="Execution duration in seconds")
    success: bool = Field(..., description="Whether the command succeeded")
    dispatched_at: float = Field(default_factory=time.time, description="Dispatch epoch timestamp")


class DeviceNodeListResponseDTO(BaseModel):
    """Collection response containing registered mesh nodes."""

    model_config = ConfigDict(extra="forbid")

    nodes: list[MeshDeviceNodeDTO] = Field(default_factory=list, description="List of mesh device nodes")
    total_count: int = Field(ge=0, description="Total matching node count")
