# [POS]: app/services/memory/relational_backtrack_service.py
# [INPUT]: app.schemas.relational_backtrack, myrm_agent_harness.toolkits.memory
# [OUTPUT]: RelationalBacktrackService, get_relational_backtrack_service

from __future__ import annotations

import logging
import uuid

from myrm_agent_harness.toolkits.memory import (
    ActionSynonymNormalizer,
    CrossSessionBacktrackEngine,
    EntityTypeKind,
    RelationalBacktrackHit,
    RelationalBacktrackQuery,
    RelationalBacktrackResult,
    TemporalRelationTriplet,
    TemporalTripletStore,
)

from app.schemas.relational_backtrack import (
    RecordTripletRequest,
    RecordTripletResponse,
    RelationalBacktrackHitDTO,
    RelationalBacktrackQueryRequest,
    RelationalBacktrackResponseDTO,
    TemporalRelationTripletDTO,
)

logger = logging.getLogger(__name__)


def _to_triplet_dto(triplet: TemporalRelationTriplet) -> TemporalRelationTripletDTO:
    return TemporalRelationTripletDTO(
        triplet_id=triplet.triplet_id,
        subject=triplet.subject,
        predicate_action=triplet.predicate_action,
        target_entity=triplet.target_entity,
        target_entity_type=triplet.target_entity_type.value,
        temporal_anchor=triplet.temporal_anchor,
        session_id=triplet.session_id,
        message_id=triplet.message_id,
        verbatim_quote=triplet.verbatim_quote,
        action_synonyms=list(triplet.action_synonyms),
        confidence=triplet.confidence,
        created_at=triplet.created_at,
    )


def _to_hit_dto(hit: RelationalBacktrackHit) -> RelationalBacktrackHitDTO:
    return RelationalBacktrackHitDTO(
        triplet=_to_triplet_dto(hit.triplet),
        matched_cue=hit.matched_cue,
        match_score=hit.match_score,
    )


class RelationalBacktrackService:
    """Application service managing temporal relation triplets and cross-session entity backtracking."""

    def __init__(
        self,
        engine: CrossSessionBacktrackEngine | None = None,
        store: TemporalTripletStore | None = None,
        normalizer: ActionSynonymNormalizer | None = None,
    ) -> None:
        self._store = store or TemporalTripletStore()
        self._normalizer = normalizer or ActionSynonymNormalizer()
        self._engine = engine or CrossSessionBacktrackEngine(
            store=self._store,
            normalizer=self._normalizer,
        )

    def record_triplet(self, req: RecordTripletRequest) -> RecordTripletResponse:
        """Store a structured entity-action-temporal triplet."""
        type_map: dict[str, EntityTypeKind] = {
            "person": EntityTypeKind.PERSON,
            "client": EntityTypeKind.CLIENT,
            "project": EntityTypeKind.PROJECT,
            "organization": EntityTypeKind.ORGANIZATION,
            "location": EntityTypeKind.LOCATION,
            "tool": EntityTypeKind.TOOL,
        }
        ent_type = type_map.get(req.target_entity_type.lower(), EntityTypeKind.CLIENT)
        triplet_id = f"trip-{uuid.uuid4().hex[:8]}"

        domain_triplet = TemporalRelationTriplet(
            triplet_id=triplet_id,
            subject=req.subject,
            predicate_action=req.predicate_action,
            target_entity=req.target_entity,
            target_entity_type=ent_type,
            temporal_anchor=req.temporal_anchor,
            session_id=req.session_id,
            message_id=req.message_id,
            verbatim_quote=req.verbatim_quote,
            action_synonyms=req.action_synonyms,
            confidence=req.confidence,
        )

        recorded = self._engine.store.record_triplet(domain_triplet)
        return RecordTripletResponse(
            is_success=True,
            triplet=_to_triplet_dto(recorded),
        )

    def query_backtrack(self, req: RelationalBacktrackQueryRequest) -> RelationalBacktrackResponseDTO:
        """Execute cross-session relational backtracking for a given action cue."""
        type_map: dict[str, EntityTypeKind] = {
            "person": EntityTypeKind.PERSON,
            "client": EntityTypeKind.CLIENT,
            "project": EntityTypeKind.PROJECT,
            "organization": EntityTypeKind.ORGANIZATION,
            "location": EntityTypeKind.LOCATION,
            "tool": EntityTypeKind.TOOL,
        }
        ent_type = (
            type_map.get(req.target_entity_type.lower())
            if req.target_entity_type
            else None
        )

        domain_query = RelationalBacktrackQuery(
            action_cue=req.action_cue,
            target_entity_type=ent_type,
            session_id_scope=req.session_id_scope,
            min_confidence=req.min_confidence,
        )

        result: RelationalBacktrackResult = self._engine.backtrack(domain_query)

        return RelationalBacktrackResponseDTO(
            hits=[_to_hit_dto(h) for h in result.hits],
            total_found=result.total_found,
            inferred_answer=result.inferred_answer,
        )

    def list_all_triplets(self) -> list[TemporalRelationTripletDTO]:
        """List all registered relation triplets in chronological descending order."""
        return [_to_triplet_dto(t) for t in self._engine.store.list_all()]


_instance: RelationalBacktrackService | None = None


def get_relational_backtrack_service() -> RelationalBacktrackService:
    """Dependency provider for RelationalBacktrackService singleton."""
    global _instance
    if _instance is None:
        _instance = RelationalBacktrackService()
    return _instance
