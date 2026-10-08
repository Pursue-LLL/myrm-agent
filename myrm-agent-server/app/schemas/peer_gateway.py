"""Pydantic schemas and DTOs for Multi-Channel Peer Alias & Anti-Cross-Contamination Gateway (Item 113).

[INPUT]
- pydantic::{BaseModel, Field} (POS: validated request and response models)

[OUTPUT]
- ResolvedPeerIdentityDTO, ResolvePeerRequest: canonical peer resolution from a channel id
- PeerBoundaryCheckResultDTO, VerifyBoundaryRequest: cross-peer boundary verification
- RegisterAliasRequest, EscalateHashRequest, EscalateHashResultDTO: alias registration and hash-collision escalation

[POS]
API contracts of the multi-channel peer gateway, shared by its router and service.
"""

from __future__ import annotations

from pydantic import BaseModel, Field


class ResolvedPeerIdentityDTO(BaseModel):
    """DTO representing the deterministic normalized peer identity."""

    canonical_peer_id: str = Field(description="Normalized canonical system peer identifier")
    channel_type: str = Field(description="Originating client access channel (web, desktop, feishu, etc.)")
    raw_channel_id: str = Field(description="Raw external identifier supplied by channel")
    alias_matched: bool = Field(default=False, description="True if identity resolved via alias table")
    is_pinned: bool = Field(default=False, description="True if resolved via pinned primary user")
    hash_escalated: bool = Field(default=False, description="True if hash suffix length was escalated")
    resolved_at: str = Field(description="Resolution ISO timestamp")


class PeerBoundaryCheckResultDTO(BaseModel):
    """DTO representing access isolation outcome preventing cross-peer contamination."""

    allowed: bool = Field(description="True if memory boundary check permits access")
    session_peer_id: str = Field(description="Active session peer identifier")
    target_peer_id: str = Field(description="Requested target memory partition identifier")
    violation_reason: str | None = Field(default=None, description="Detailed explanation if blocked")


class ResolvePeerRequest(BaseModel):
    """Request payload to deterministically resolve external channel ID to canonical peer."""

    channel_type: str = Field(default="web", description="Channel platform: web, desktop, feishu, dingtalk, telegram, slack, api")
    raw_channel_id: str = Field(min_length=1, description="Raw channel identity identifier")


class VerifyBoundaryRequest(BaseModel):
    """Request payload to check whether a session peer is authorized to access target peer memory."""

    session_peer_id: str = Field(min_length=1, description="Originating session peer id")
    target_peer_id: str = Field(min_length=1, description="Target peer memory id")


class RegisterAliasRequest(BaseModel):
    """Request payload to map a multi-channel external key to a canonical peer."""

    channel_key: str = Field(min_length=1, description="Channel identifier key (e.g. desktop:workstation_1 or ou_xxx)")
    canonical_peer_id: str = Field(min_length=1, description="Target canonical peer id")


class EscalateHashRequest(BaseModel):
    """Request payload to test or simulate adaptive collision escalation."""

    raw_id: str = Field(min_length=1, description="Raw identifier to normalize and hash")
    prefix: str = Field(default="peer_", description="Prefix prepended to identifier")
    existing_peers: list[str] = Field(default_factory=list, description="Existing known peers simulating collisions")


class EscalateHashResultDTO(BaseModel):
    """DTO representing adaptive hash escalation outcome."""

    escalated_id: str = Field(description="Generated collision-free identifier")
    was_escalated: bool = Field(description="True if hash was expanded beyond initial 8-char length")
