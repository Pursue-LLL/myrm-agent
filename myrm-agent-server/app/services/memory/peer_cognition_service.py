# [POS]: app/services/memory/peer_cognition_service.py
# [INPUT]: app.schemas.peer_cognition, myrm_agent_harness.toolkits.memory
# [OUTPUT]: PeerCognitionService, get_peer_cognition_service

"""Business service implementing Peer-Centric Social Cognition and Persona Card Suite (Item 110)."""

from __future__ import annotations

import logging
from functools import lru_cache

from myrm_agent_harness.toolkits.memory import (
    PeerCognitionGraphStore,
    PeerCognitionProjection,
    PeerIdentity,
    PeerPersonaCard,
    PeerPersonaCardEngine,
    PeerRelationEdge,
    PeerRelationKind,
    PeerType,
)

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

logger = logging.getLogger(__name__)


def _identity_to_dto(peer: PeerIdentity) -> PeerIdentityDTO:
    """Map internal peer identity to API DTO."""
    return PeerIdentityDTO(
        peer_id=peer.peer_id,
        peer_type=peer.peer_type.value,
        display_name=peer.display_name,
        role_title=peer.role_title,
        avatar_or_icon=peer.avatar_or_icon,
        created_at=peer.created_at,
        last_seen_at=peer.last_seen_at,
    )


def _edge_to_dto(edge: PeerRelationEdge) -> PeerRelationEdgeDTO:
    """Map internal relation edge to API DTO."""
    return PeerRelationEdgeDTO(
        edge_id=edge.edge_id,
        source_peer_id=edge.source_peer_id,
        target_entity_id=edge.target_entity_id,
        target_is_peer=edge.target_is_peer,
        relation_kind=edge.relation_kind.value,
        context_note=edge.context_note,
        weight=edge.weight,
        created_at=edge.created_at,
    )


def _card_to_dto(card: PeerPersonaCard) -> PeerPersonaCardDTO:
    """Map internal persona card to API DTO."""
    return PeerPersonaCardDTO(
        peer_id=card.peer_id,
        peer_type=card.peer_type.value,
        display_name=card.display_name,
        core_responsibilities=list(card.core_responsibilities),
        decision_style=card.decision_style,
        standing_preferences=dict(card.standing_preferences),
        interaction_count=card.interaction_count,
        success_rate=card.success_rate,
        trust_score=card.trust_score,
        summary_digest=card.summary_digest,
        updated_at=card.updated_at,
    )


def _projection_to_dto(proj: PeerCognitionProjection) -> PeerCognitionProjectionDTO:
    """Map internal context projection to API DTO."""
    return PeerCognitionProjectionDTO(
        formatted_prompt_block=proj.formatted_prompt_block,
        token_cost_estimate=proj.token_cost_estimate,
        targeted_peers=list(proj.targeted_peers),
    )


class PeerCognitionService:
    """Service encapsulating social cognition graph and standing persona card engine."""

    def __init__(self) -> None:
        self._graph_store = PeerCognitionGraphStore()
        self._card_engine = PeerPersonaCardEngine(graph_store=self._graph_store)

    def register_peer(self, req: RegisterPeerRequest) -> PeerIdentityDTO:
        """Register or update a participant peer identity."""
        try:
            ptype = PeerType(req.peer_type)
        except ValueError:
            ptype = PeerType.USER_PEER

        identity = PeerIdentity(
            peer_id=req.peer_id,
            peer_type=ptype,
            display_name=req.display_name,
            role_title=req.role_title,
            avatar_or_icon=req.avatar_or_icon,
        )
        self._graph_store.register_peer(identity)
        # Initialize basic persona card
        self._card_engine.create_or_update_card(req.peer_id)
        return _identity_to_dto(identity)

    def get_peer(self, peer_id: str) -> PeerIdentityDTO | None:
        """Retrieve peer identity by identifier."""
        peer = self._graph_store.get_peer(peer_id)
        if peer is None:
            return None
        return _identity_to_dto(peer)

    def list_peers(self, peer_type_str: str | None = None) -> list[PeerIdentityDTO]:
        """List peers, optionally filtered by peer category."""
        ptype: PeerType | None = None
        if peer_type_str:
            try:
                ptype = PeerType(peer_type_str)
            except ValueError:
                ptype = None
        peers = self._graph_store.list_peers(peer_type=ptype)
        return [_identity_to_dto(p) for p in peers]

    def get_persona_card(self, peer_id: str) -> PeerPersonaCardDTO | None:
        """Get curated persona card for a peer."""
        card = self._card_engine.get_card(peer_id)
        if card is None:
            return None
        return _card_to_dto(card)

    def update_persona_card(self, peer_id: str, req: UpdatePersonaCardRequest) -> PeerPersonaCardDTO:
        """Explicitly mutate a persona card."""
        card = self._card_engine.create_or_update_card(
            peer_id=peer_id,
            core_responsibilities=req.core_responsibilities,
            decision_style=req.decision_style,
            standing_preferences=req.standing_preferences,
            summary_digest=req.summary_digest,
        )
        return _card_to_dto(card)

    def record_interaction(self, peer_id: str, req: RecordInteractionRequest) -> PeerPersonaCardDTO:
        """Evolve persona card following an interaction outcome."""
        card = self._card_engine.record_interaction(
            peer_id=peer_id,
            success=req.success,
            preference_deltas=req.preference_deltas,
        )
        return _card_to_dto(card)

    def add_relation_edge(self, req: AddRelationEdgeRequest) -> PeerRelationEdgeDTO:
        """Insert a relational edge into the social cognition graph."""
        try:
            rkind = PeerRelationKind(req.relation_kind)
        except ValueError:
            rkind = PeerRelationKind.ASSERTS

        edge = PeerRelationEdge(
            edge_id=req.edge_id,
            source_peer_id=req.source_peer_id,
            target_entity_id=req.target_entity_id,
            target_is_peer=req.target_is_peer,
            relation_kind=rkind,
            context_note=req.context_note,
            weight=req.weight,
        )
        self._graph_store.add_edge(edge)
        return _edge_to_dto(edge)

    def list_edges_for_peer(self, peer_id: str) -> list[PeerRelationEdgeDTO]:
        """List incoming and outgoing graph edges for a given peer."""
        edges = self._graph_store.get_edges_for_peer(peer_id)
        return [_edge_to_dto(e) for e in edges]

    def generate_projection(self, req: GenerateProjectionRequest) -> PeerCognitionProjectionDTO:
        """Compile a low-token prompt context projection for targeted peers."""
        proj = self._card_engine.generate_projection(req.peer_ids)
        return _projection_to_dto(proj)


@lru_cache(maxsize=1)
def get_peer_cognition_service() -> PeerCognitionService:
    """Dependency provider returning singleton PeerCognitionService."""
    return PeerCognitionService()
