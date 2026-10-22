"""[INPUT] MachineNode, MachineMetrics, and Takeover schemas.
[OUTPUT] Strong-typed Pydantic schemas for self-hosted machine fleet and remote takeover.
[POS] app/services/machines/machine_types.py.
"""

from datetime import datetime, timezone
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class MachinePlatform(str, Enum):
    DARWIN = "darwin"
    LINUX = "linux"
    WINDOWS = "windows"


class MachineStatus(str, Enum):
    ONLINE = "online"
    BUSY = "busy"
    OFFLINE = "offline"
    TAKEOVER = "takeover"


class MachineMetrics(BaseModel):
    """Real-time system telemetry metrics for a self-hosted node."""

    cpu_usage_pct: float = Field(..., ge=0.0, le=100.0, description="CPU usage percentage")
    memory_usage_pct: float = Field(..., ge=0.0, le=100.0, description="Memory utilization percentage")
    disk_usage_pct: float = Field(..., ge=0.0, le=100.0, description="Disk capacity utilization percentage")
    active_tasks_count: int = Field(0, ge=0, description="Number of currently running sub-agent tasks")
    last_heartbeat_at: str = Field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat(),
        description="ISO 8601 timestamp of last reported heartbeat",
    )


class MachineNode(BaseModel):
    """Registered self-hosted worker machine node."""

    machine_id: str = Field(..., description="Unique machine identifier, e.g. 'mach-mac-studio-01'")
    hostname: str = Field(..., description="Machine local hostname")
    display_name: str = Field(..., description="Human friendly label for the machine")
    platform: MachinePlatform = Field(..., description="Operating system platform")
    ip_address: str = Field(..., description="Local or tunnel IP address")
    status: MachineStatus = Field(MachineStatus.ONLINE, description="Current operational state")
    metrics: MachineMetrics = Field(..., description="Telemetry snapshot")
    registered_at: str = Field(..., description="ISO 8601 registration timestamp")
    tags: List[str] = Field(default_factory=list, description="Descriptive capability tags")
    screen_stream_url: Optional[str] = Field(None, description="WebRTC / CDP screen stream URL")


class RegistrationTokenResponse(BaseModel):
    """Response containing 1-click machine registration script and temporary token."""

    token: str = Field(..., description="Temporary registration token")
    platform: MachinePlatform = Field(..., description="Target platform")
    quick_command: str = Field(..., description="Copy-pasteable one-line command to register the node")
    expires_at: str = Field(..., description="Token expiration ISO 8601 timestamp")


class TakeoverState(str, Enum):
    AGENT = "agent"
    HUMAN_TAKEOVER = "human_takeover"


class TakeoverSession(BaseModel):
    """Session state tracking human takeover over a remote agent screen."""

    session_id: str = Field(..., description="Unique takeover session identifier")
    machine_id: str = Field(..., description="Target machine identifier")
    state: TakeoverState = Field(TakeoverState.AGENT, description="Current control state")
    operator_id: Optional[str] = Field(None, description="Operator user identifier when under human takeover")
    started_at: str = Field(..., description="ISO 8601 takeover start timestamp")
    updated_at: str = Field(..., description="ISO 8601 last update timestamp")


class TakeoverActionRequest(BaseModel):
    """Request payload to initiate or release human control takeover."""

    action: str = Field(..., description="'takeover' to seize control or 'release' to hand back to agent")
    operator_id: Optional[str] = Field("user-primary", description="Operator identifier")
