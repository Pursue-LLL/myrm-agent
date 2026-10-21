from pydantic import BaseModel, Field


class GatewayTelemetryDTO(BaseModel):
    cpu_pct: float = Field(ge=0.0, le=100.0, description="CPU usage %")
    mem_pct: float = Field(ge=0.0, le=100.0, description="Memory usage %")
    active_agents: int = Field(ge=0, description="Active agents count")
    queue_depth: int = Field(ge=0, description="Pending queue depth")


class RegisterGatewayRequest(BaseModel):
    gateway_id: str = Field(min_length=1, description="Unique identifier of gateway node")
    label: str = Field(min_length=1, description="Human readable label")
    host: str = Field(min_length=1, description="Host IP or FQDN")
    port: int = Field(ge=1, le=65535, description="Port number")
    protocol: str = Field(default="ws", description="Protocol schema (ws, wss, http, https)")
    platform: str = Field(description="Host platform (darwin, linux, vps, cloud)")
    latency_ms: float = Field(default=0.0, ge=0.0, description="Measured ping latency in ms")
    cpu_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    mem_pct: float = Field(default=0.0, ge=0.0, le=100.0)
    active_agents: int = Field(default=0, ge=0)
    queue_depth: int = Field(default=0, ge=0)


class GatewayNodeResponse(BaseModel):
    gateway_id: str
    label: str
    host: str
    port: int
    protocol: str
    platform: str
    status: str
    latency_ms: float
    telemetry: GatewayTelemetryDTO
    last_heartbeat: float


class HeartbeatRequest(BaseModel):
    cpu_pct: float = Field(ge=0.0, le=100.0)
    mem_pct: float = Field(ge=0.0, le=100.0)
    active_agents: int = Field(ge=0)
    queue_depth: int = Field(ge=0)
    latency_ms: float = Field(ge=0.0)
    status: str | None = None


class RegisterProfileRequest(BaseModel):
    profile_id: str = Field(min_length=1)
    gateway_id: str = Field(min_length=1)
    name: str = Field(min_length=1)
    avatar: str = Field(default="🤖")
    role: str = Field(min_length=1)
    system_context: str = Field(default="")
    is_active: bool = Field(default=True)


class FleetProfileResponse(BaseModel):
    profile_id: str
    gateway_id: str
    name: str
    avatar: str
    role: str
    system_context: str
    is_active: bool


class InjectedContextResponse(BaseModel):
    profile_id: str
    original_context: str
    injected_context: str
    host_badge: dict[str, str] | None = None


class BufferCommandRequest(BaseModel):
    gateway_id: str
    profile_id: str
    command_type: str
    payload: dict[str, str] = Field(default_factory=dict)


class BufferedCommandResponse(BaseModel):
    command_id: str
    gateway_id: str
    profile_id: str
    command_type: str
    payload: dict[str, str]
    queued_at: float
    retry_count: int


class FlushResponse(BaseModel):
    gateway_id: str
    flushed_count: int
    commands: list[BufferedCommandResponse]


class RelayArtifactRequest(BaseModel):
    source_gateway: str
    target_gateway: str
    name: str
    file_path: str
    chunk_data: str


class RelayedArtifactResponse(BaseModel):
    artifact_id: str
    source_gateway: str
    target_gateway: str
    name: str
    file_path: str
    sha256: str
    chunk_data: str
    created_at: float
    is_verified: bool


class FleetTopologyResponse(BaseModel):
    gateways: list[GatewayNodeResponse]
    profiles: list[FleetProfileResponse]
    total_gateways: int
    online_gateways: int
    total_buffered_commands: int
