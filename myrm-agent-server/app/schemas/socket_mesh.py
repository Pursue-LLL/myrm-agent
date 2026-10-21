"""Pydantic V2 DTO schemas for the Lightweight P2P Agent Socket Mesh Protocol."""

from __future__ import annotations

from enum import StrEnum
from typing import List, Optional

from pydantic import BaseModel, Field


class PeerStatusEnum(StrEnum):
    """Operational status of a peer in the mesh."""

    ONLINE = "online"
    STALE = "stale"
    OFFLINE = "offline"


class EnvelopeTypeEnum(StrEnum):
    """Type of standard atomic envelope."""

    PROMPT = "prompt"
    RESPONSE = "response"
    PING = "ping"
    PONG = "pong"


class PeerRegisterRequestDTO(BaseModel):
    """Request payload to register a peer in the mesh."""

    name: str = Field(..., description="Unique name of the agent within the project")
    purpose: str = Field(default="Task Agent", description="Functional purpose of the agent")
    model: str = Field(default="default-model", description="Model backing the agent")
    pid: int = Field(default=0, description="Process ID of the agent")
    context_used_pct: float = Field(default=0.0, ge=0.0, le=100.0, description="Context window usage percentage")
    queue_depth: int = Field(default=0, ge=0, description="In-flight queue depth")


class PeerInfoDTO(BaseModel):
    """Telemetry and identity details of a registered peer."""

    session_id: str
    name: str
    purpose: str
    model: str
    pid: int
    endpoint: str
    cwd: str
    started_at: float
    heartbeat_at: float
    context_used_pct: float
    queue_depth: int
    status: PeerStatusEnum


class PeerListResponseDTO(BaseModel):
    """Response containing list of registered peers in a project."""

    project: str
    total_peers: int
    peers: List[PeerInfoDTO]


class SendEnvelopeRequestDTO(BaseModel):
    """Request payload to dispatch a prompt envelope to a peer."""

    sender_name: str = Field(..., description="Name of the sender agent")
    target_name: str = Field(..., description="Name of the destination agent")
    prompt: str = Field(..., description="Prompt payload to dispatch")
    timeout_seconds: float = Field(default=30.0, gt=0.0, description="Dispatch timeout in seconds")


class EnvelopeDispatchResponseDTO(BaseModel):
    """Response returned upon dispatching an envelope."""

    success: bool
    msg_id: str
    hops: int = 0
    duration_ms: float = 0.0
    error: Optional[str] = None


class AwaitResponseDTO(BaseModel):
    """Response returned when awaiting reply for a message."""

    success: bool
    msg_id: str
    response: Optional[str] = None
    error: Optional[str] = None
    hops: int = 0
    duration_ms: float = 0.0


class ReplyEnvelopeRequestDTO(BaseModel):
    """Request payload to reply to an inbound message."""

    responder_name: str = Field(..., description="Name of the responder agent")
    msg_id: str = Field(..., description="ID of the message being replied to")
    response_text: str = Field(..., description="Response payload")
    error: Optional[str] = Field(default=None, description="Optional error description")


class PingResponseDTO(BaseModel):
    """Result of pinging a peer."""

    success: bool
    msg_id: str
    response: Optional[str] = None
    error: Optional[str] = None
    duration_ms: float = 0.0


class MeshAuditLogDTO(BaseModel):
    """Audit trail record for an event in the socket mesh."""

    timestamp: float
    event_type: str
    node: str
    project: str
    detail: str


class AuditLogsResponseDTO(BaseModel):
    """List of audit logs for a project mesh."""

    project: str
    logs: List[MeshAuditLogDTO]


class CleanupStalePeersResponseDTO(BaseModel):
    """Result of cleaning up inactive stale peers."""

    project: str
    cleaned_count: int
