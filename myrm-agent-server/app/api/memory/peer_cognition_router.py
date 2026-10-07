# [POS]: app/api/memory/peer_cognition_router.py
# [INPUT]: app.schemas.peer_cognition, app.services.memory.peer_cognition_service
# [OUTPUT]: router (FastAPI APIRouter for Peer-Centric Social Cognition and Persona Card Suite)

"""FastAPI router for Peer-Centric Social Cognition and Persona Card Suite (Item 110)."""

from __future__ import annotations

import logging
from typing import Annotated

from fastapi import APIRouter, Depends, HTTPException, Query

from app.schemas.peer_cognition import (
    AddRelationEdgeRequest,
    GenerateProjectionRequest,
    PeerCognitionProjectionDTO,
    PeerIdentityDTO,
    PeerPersonaCardDTO,
    PeerRelationEdgeDTO,
    RecordInteractionRequest,
    RegisterPeerRequest,
    UpdatePersonaCardRequest,
)
from app.services.memory.peer_cognition_service import (
    PeerCognitionService,
    get_peer_cognition_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/peer-cognition", tags=["Peer Social Cognition & Persona Card"])


@router.post(
    "/peers",
    response_model=PeerIdentityDTO,
    status_code=201,
    summary="Register or update a participant peer identity",
)
async def register_peer_identity(
    request: RegisterPeerRequest,
    service: Annotated[PeerCognitionService, Depends(get_peer_cognition_service)],
) -> PeerIdentityDTO:
    """Register a new participant (user, agent, reviewer, project) in the social cognition network."""
    return service.register_peer(request)


@router.get(
    "/peers",
    response_model=list[PeerIdentityDTO],
    summary="List registered participant peers",
)
async def list_peer_identities(
    service: Annotated[PeerCognitionService, Depends(get_peer_cognition_service)],
    peer_type: str | None = Query(default=None, description="Optional peer type filter"),
) -> list[PeerIdentityDTO]:
    """Retrieve all peers, optionally filtered by peer category."""
    return service.list_peers(peer_type_str=peer_type)


@router.get(
    "/peers/{peer_id}",
    response_model=PeerIdentityDTO,
    summary="Get single peer identity by identifier",
)
async def get_peer_identity(
    peer_id: str,
    service: Annotated[PeerCognitionService, Depends(get_peer_cognition_service)],
) -> PeerIdentityDTO:
    """Retrieve identity details for an individual peer."""
    peer = service.get_peer(peer_id)
    if peer is None:
        raise HTTPException(status_code=404, detail=f"Peer identity not found: {peer_id}")
    return peer


@router.get(
    "/cards/{peer_id}",
    response_model=PeerPersonaCardDTO,
    summary="Retrieve curated standing persona card for a peer",
)
async def get_persona_card(
    peer_id: str,
    service: Annotated[PeerCognitionService, Depends(get_peer_cognition_service)],
) -> PeerPersonaCardDTO:
    """Retrieve standing persona card with responsibilities, decision style, and preferences."""
    card = service.get_persona_card(peer_id)
    if card is None:
        raise HTTPException(status_code=404, detail=f"Persona card not found for peer: {peer_id}")
    return card


@router.put(
    "/cards/{peer_id}",
    response_model=PeerPersonaCardDTO,
    summary="Explicitly mutate or enrich a persona card",
)
async def update_persona_card(
    peer_id: str,
    request: UpdatePersonaCardRequest,
    service: Annotated[PeerCognitionService, Depends(get_peer_cognition_service)],
) -> PeerPersonaCardDTO:
    """Update responsibilities, decision style, or standing preferences on a persona card."""
    return service.update_persona_card(peer_id=peer_id, req=request)


@router.post(
    "/cards/{peer_id}/interactions",
    response_model=PeerPersonaCardDTO,
    summary="Record interaction outcome and evolve persona card",
)
async def record_interaction_event(
    peer_id: str,
    request: RecordInteractionRequest,
    service: Annotated[PeerCognitionService, Depends(get_peer_cognition_service)],
) -> PeerPersonaCardDTO:
    """Evolve persona card trust score and preference digest based on interaction feedback."""
    return service.record_interaction(peer_id=peer_id, req=request)


@router.post(
    "/edges",
    response_model=PeerRelationEdgeDTO,
    status_code=201,
    summary="Add a directed relational edge into the social cognition graph",
)
async def add_relation_edge(
    request: AddRelationEdgeRequest,
    service: Annotated[PeerCognitionService, Depends(get_peer_cognition_service)],
) -> PeerRelationEdgeDTO:
    """Insert a semantic relation (asserts, approves, collaborates_with, governs) into the graph."""
    return service.add_relation_edge(request)


@router.get(
    "/edges/{peer_id}",
    response_model=list[PeerRelationEdgeDTO],
    summary="Get all graph edges connected to a peer",
)
async def get_edges_for_peer(
    peer_id: str,
    service: Annotated[PeerCognitionService, Depends(get_peer_cognition_service)],
) -> list[PeerRelationEdgeDTO]:
    """Retrieve outgoing and incoming relational edges for a peer."""
    return service.list_edges_for_peer(peer_id)


@router.post(
    "/projection",
    response_model=PeerCognitionProjectionDTO,
    summary="Compile low-token context prompt injection block for targeted peers",
)
async def generate_prompt_projection(
    request: GenerateProjectionRequest,
    service: Annotated[PeerCognitionService, Depends(get_peer_cognition_service)],
) -> PeerCognitionProjectionDTO:
    """Compile compact (<150 words per peer) social cognition context ready for LLM prompt."""
    return service.generate_projection(request)
