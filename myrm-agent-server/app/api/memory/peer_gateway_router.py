"""FastAPI router for Multi-Channel Peer Alias & Anti-Cross-Contamination Gateway Suite (Item 113).

[POS]
app/api/memory/peer_gateway_router.py

[INPUT]
- app.schemas.peer_gateway, app.services.memory.peer_gateway_service

[OUTPUT]
- router (FastAPI APIRouter for Multi-Channel Peer Gateway Suite)
"""


from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends

from app.schemas.peer_gateway import (
    EscalateHashRequest,
    EscalateHashResultDTO,
    PeerBoundaryCheckResultDTO,
    RegisterAliasRequest,
    ResolvedPeerIdentityDTO,
    ResolvePeerRequest,
    VerifyBoundaryRequest,
)
from app.services.memory.peer_gateway_service import (
    PeerGatewayService,
    get_peer_gateway_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/peer-gateway", tags=["Peer Gateway"])


@router.post(
    "/resolve",
    response_model=ResolvedPeerIdentityDTO,
    summary="Deterministically resolve external channel ID to canonical peer",
)
async def resolve_peer(
    request: ResolvePeerRequest,
    service: Annotated[PeerGatewayService, Depends(get_peer_gateway_service)],
) -> ResolvedPeerIdentityDTO:
    """Resolve an incoming external channel identity using pinned mode, alias tables, or adaptive escalation."""
    return service.resolve_peer(request)


@router.post(
    "/verify-boundary",
    response_model=PeerBoundaryCheckResultDTO,
    summary="Enforce memory boundary fences to prevent cross-peer contamination",
)
async def verify_boundary(
    request: VerifyBoundaryRequest,
    service: Annotated[PeerGatewayService, Depends(get_peer_gateway_service)],
) -> PeerBoundaryCheckResultDTO:
    """Verify that a session peer has legitimate authority to read or mutate target peer memory."""
    return service.verify_boundary(request)


@router.post(
    "/aliases",
    response_model=dict[str, str],
    summary="Register multi-channel peer alias mapping",
)
async def register_alias(
    request: RegisterAliasRequest,
    service: Annotated[PeerGatewayService, Depends(get_peer_gateway_service)],
) -> dict[str, str]:
    """Register or update a channel-specific identifier to canonical peer mapping."""
    return service.register_alias(request)


@router.get(
    "/aliases",
    response_model=dict[str, str],
    summary="List all registered peer alias mappings",
)
async def get_aliases(
    service: Annotated[PeerGatewayService, Depends(get_peer_gateway_service)],
) -> dict[str, str]:
    """Retrieve the full table of registered channel-to-peer aliases."""
    return service.get_aliases()


@router.post(
    "/escalate-hash",
    response_model=EscalateHashResultDTO,
    summary="Simulate adaptive hash collision escalation",
)
async def escalate_hash(
    request: EscalateHashRequest,
    service: Annotated[PeerGatewayService, Depends(get_peer_gateway_service)],
) -> EscalateHashResultDTO:
    """Simulate or execute collision-free hash suffix escalation over existing peers."""
    return service.escalate_hash(request)
