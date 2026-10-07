# [POS]: app/services/memory/peer_gateway_service.py
# [INPUT]: app.schemas.peer_gateway, myrm_agent_harness.toolkits.memory
# [OUTPUT]: PeerGatewayService, get_peer_gateway_service

"""Business service implementing Multi-Channel Peer Alias & Anti-Cross-Contamination Gateway (Item 113)."""

from __future__ import annotations

import logging
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    AntiCrossContaminationGateway,
    ChannelType,
    HashEscalationEngine,
    PeerBoundaryCheckResult,
    ResolvedPeerIdentity,
)

from app.schemas.peer_gateway import (
    EscalateHashRequest,
    EscalateHashResultDTO,
    PeerBoundaryCheckResultDTO,
    RegisterAliasRequest,
    ResolvedPeerIdentityDTO,
    ResolvePeerRequest,
    VerifyBoundaryRequest,
)

logger = logging.getLogger(__name__)


def _identity_to_dto(identity: ResolvedPeerIdentity) -> ResolvedPeerIdentityDTO:
    """Map internal domain resolved identity to API DTO."""
    return ResolvedPeerIdentityDTO(
        canonical_peer_id=identity.canonical_peer_id,
        channel_type=identity.channel_type.value,
        raw_channel_id=identity.raw_channel_id,
        alias_matched=identity.alias_matched,
        is_pinned=identity.is_pinned,
        hash_escalated=identity.hash_escalated,
        resolved_at=identity.resolved_at,
    )


def _boundary_to_dto(res: PeerBoundaryCheckResult) -> PeerBoundaryCheckResultDTO:
    """Map internal domain boundary check to API DTO."""
    return PeerBoundaryCheckResultDTO(
        allowed=res.allowed,
        session_peer_id=res.session_peer_id,
        target_peer_id=res.target_peer_id,
        violation_reason=res.violation_reason,
    )


class PeerGatewayService:
    """Domain service managing multi-channel peer resolution and boundary defense."""

    def __init__(self, gateway: AntiCrossContaminationGateway | None = None) -> None:
        self._gateway = gateway or AntiCrossContaminationGateway()

    @property
    def gateway(self) -> AntiCrossContaminationGateway:
        return self._gateway

    def resolve_peer(self, request: ResolvePeerRequest) -> ResolvedPeerIdentityDTO:
        """Resolve raw external channel ID to canonical peer identity."""
        try:
            c_type = ChannelType(request.channel_type.lower())
        except ValueError:
            c_type = ChannelType.API

        identity = self._gateway.resolver.resolve_peer(
            channel_type=c_type,
            raw_channel_id=request.raw_channel_id,
        )
        return _identity_to_dto(identity)

    def verify_boundary(self, request: VerifyBoundaryRequest) -> PeerBoundaryCheckResultDTO:
        """Verify whether session peer is permitted to access target peer memory partition."""
        check = self._gateway.validate_session_peer_boundary(
            session_peer_id=request.session_peer_id,
            target_peer_id=request.target_peer_id,
        )
        return _boundary_to_dto(check)

    def register_alias(self, request: RegisterAliasRequest) -> dict[str, str]:
        """Register or update an external channel identifier mapping."""
        self._gateway.resolver.register_alias(
            channel_key=request.channel_key,
            canonical_peer_id=request.canonical_peer_id,
        )
        return self._gateway.resolver.get_aliases()

    def get_aliases(self) -> dict[str, str]:
        """Retrieve all registered channel-to-peer alias mappings."""
        return self._gateway.resolver.get_aliases()

    def escalate_hash(self, request: EscalateHashRequest) -> EscalateHashResultDTO:
        """Simulate adaptive hash collision escalation algorithm."""
        collision_set = set(request.existing_peers)
        escalated_id, was_escalated = HashEscalationEngine.escalate_hash_suffix(
            raw_id=request.raw_id,
            collision_registry=collision_set,
            prefix=request.prefix,
        )
        return EscalateHashResultDTO(
            escalated_id=escalated_id,
            was_escalated=was_escalated,
        )


@lru_cache(maxsize=1)
def get_peer_gateway_service() -> PeerGatewayService:
    """Provide singleton PeerGatewayService instance."""
    return PeerGatewayService()
