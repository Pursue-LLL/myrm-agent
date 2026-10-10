"""Service layer coordinating Person Card management, relationship decay, and pre-action checks.

[INPUT]
- PersonCard creation/update/merge payloads, search queries, and pre-action verification requests.

[OUTPUT]
- PersonCardDTO, PreActionCheckResponseDTO, and updated decay scores.

[POS]
- Server-side business service for Item 155 PersonCardAndRelationshipMemoryLayer.
"""

from __future__ import annotations

import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from myrm_agent_harness.toolkits.memory.person_card import (
    PersonAttributes,
    PersonCard,
    PersonCardStore,
    PersonInteraction,
    PreActionAttributeChecker,
    PreActionCheckResult,
)

from app.schemas.person_card import (
    CreatePersonCardRequest,
    ParticipantAttributeSummaryDTO,
    PersonAttributesDTO,
    PersonCardDTO,
    PersonInteractionDTO,
    PreActionCheckRequestDTO,
    PreActionCheckResponseDTO,
    RelationTypeDTO,
    UpdatePersonCardRequest,
)


class PersonCardService:
    """Business service orchestrating person cards, relationship memory, and proactive verification."""

    def __init__(
        self,
        store: PersonCardStore | None = None,
        checker: PreActionAttributeChecker | None = None,
        storage_path: Path | str | None = None,
    ) -> None:
        self.store = store or PersonCardStore(storage_path=storage_path)
        self.checker = checker or PreActionAttributeChecker(store=self.store)

    @staticmethod
    def _to_dto(card: PersonCard) -> PersonCardDTO:
        return PersonCardDTO(
            person_id=card.person_id,
            display_name=card.display_name,
            aliases=list(card.aliases),
            relation_type=card.relation_type,
            org=card.org,
            attributes=PersonAttributesDTO(
                dietary_restrictions=list(card.attributes.dietary_restrictions),
                birthday=card.attributes.birthday,
                timezone=card.attributes.timezone,
                preferred_contact_hours=card.attributes.preferred_contact_hours,
                approval_preference=card.attributes.approval_preference,
                custom_notes=dict(card.attributes.custom_notes),
            ),
            commitments=list(card.commitments),
            interaction_timeline=[
                PersonInteractionDTO(
                    timestamp=item.timestamp,
                    summary=item.summary,
                    channel=item.channel,
                    source_event_id=item.source_event_id,
                )
                for item in card.interaction_timeline
            ],
            last_interaction_at=card.last_interaction_at,
            confidence=card.confidence,
            scope=card.scope,
            agent_id=card.agent_id,
            decay_status=card.decay_status,
            decay_score=card.decay_score,
        )

    def create_person(self, req: CreatePersonCardRequest) -> PersonCardDTO:
        """Create a new person card."""
        person_id = req.person_id or f"person_{uuid.uuid4().hex[:12]}"
        now_iso = datetime.now().astimezone().isoformat()

        card = PersonCard(
            person_id=person_id,
            display_name=req.display_name,
            aliases=list(req.aliases),
            relation_type=req.relation_type,
            org=req.org,
            attributes=PersonAttributes(
                dietary_restrictions=list(req.attributes.dietary_restrictions),
                birthday=req.attributes.birthday,
                timezone=req.attributes.timezone,
                preferred_contact_hours=req.attributes.preferred_contact_hours,
                approval_preference=req.attributes.approval_preference,
                custom_notes=dict(req.attributes.custom_notes),
            ),
            commitments=list(req.commitments),
            interaction_timeline=[
                PersonInteraction(
                    timestamp=now_iso,
                    summary="档案创建",
                )
            ],
            last_interaction_at=now_iso,
            confidence=1.0,
            scope=req.scope,
            agent_id=req.agent_id,
            decay_status="active",
            decay_score=1.0,
        )
        saved = self.store.save_person(card)
        return self._to_dto(saved)

    def get_person(self, person_id: str) -> PersonCardDTO | None:
        """Fetch a person card by ID."""
        card = self.store.get_person(person_id)
        return self._to_dto(card) if card is not None else None

    def list_persons(
        self,
        query: str | None = None,
        scope: Literal["global", "agent"] | None = None,
        relation_type: RelationTypeDTO | None = None,
        include_weak: bool = True,
        include_archived: bool = False,
        agent_id: str | None = None,
    ) -> list[PersonCardDTO]:
        """List or search person cards with filters."""
        if query and query.strip():
            cards = self.store.find_by_name_or_alias(
                query=query, agent_id=agent_id, include_weak=include_weak
            )
            # Apply scope/relation_type post-filters if provided
            filtered: list[PersonCard] = []
            for c in cards:
                if scope is not None and c.scope != scope:
                    continue
                if relation_type is not None and c.relation_type != relation_type:
                    continue
                if not include_archived and c.decay_status == "archived":
                    continue
                filtered.append(c)
            return [self._to_dto(c) for c in filtered]

        cards = self.store.list_persons(
            scope=scope,
            relation_type=relation_type,
            include_weak=include_weak,
            include_archived=include_archived,
            agent_id=agent_id,
        )
        return [self._to_dto(c) for c in cards]

    def update_person(
        self, person_id: str, req: UpdatePersonCardRequest
    ) -> PersonCardDTO | None:
        """Update fields of an existing person card."""
        card = self.store.get_person(person_id)
        if card is None:
            return None

        if req.display_name is not None:
            card.display_name = req.display_name
        if req.aliases is not None:
            card.aliases = list(req.aliases)
        if req.relation_type is not None:
            card.relation_type = req.relation_type
        if req.org is not None:
            card.org = req.org
        if req.attributes is not None:
            card.attributes = PersonAttributes(
                dietary_restrictions=list(req.attributes.dietary_restrictions),
                birthday=req.attributes.birthday,
                timezone=req.attributes.timezone,
                preferred_contact_hours=req.attributes.preferred_contact_hours,
                approval_preference=req.attributes.approval_preference,
                custom_notes=dict(req.attributes.custom_notes),
            )
        if req.commitments is not None:
            card.commitments = list(req.commitments)
        if req.confidence is not None:
            card.confidence = req.confidence
        if req.decay_status is not None:
            card.decay_status = req.decay_status

        saved = self.store.save_person(card)
        return self._to_dto(saved)

    def delete_person(self, person_id: str) -> bool:
        """Delete person card by ID."""
        return self.store.delete_person(person_id)

    def merge_persons(self, source_id: str, target_id: str) -> PersonCardDTO:
        """Merge source card into target card."""
        target = self.store.merge_persons(source_id=source_id, target_id=target_id)
        return self._to_dto(target)

    def refresh_decay(
        self,
        now: datetime | None = None,
        weak_threshold: float = 0.3,
    ) -> dict[str, float]:
        """Trigger gravity decay refresh on all cards."""
        return self.store.refresh_decay(now=now, weak_threshold=weak_threshold)

    def pre_action_check(
        self, req: PreActionCheckRequestDTO
    ) -> PreActionCheckResponseDTO:
        """Perform proactive attribute verification prior to outbound action."""
        result: PreActionCheckResult = self.checker.check_action(
            action_type=req.action_type,
            participant_names_or_ids=req.participant_names_or_ids,
            action_summary=req.action_summary,
            agent_id=req.agent_id,
        )

        participants_dto: list[ParticipantAttributeSummaryDTO] = []
        for p in result.participants:
            participants_dto.append(
                ParticipantAttributeSummaryDTO(
                    person_id=p.person_id,
                    display_name=p.display_name,
                    relation_type=p.relation_type,
                    dietary_restrictions=list(p.dietary_restrictions),
                    timezone=p.timezone,
                    approval_preference=p.approval_preference,
                    missing_critical_attributes=list(p.missing_critical_attributes),
                    is_weak_memory=p.is_weak_memory,
                    attributes=PersonAttributesDTO(
                        dietary_restrictions=list(p.attributes.dietary_restrictions),
                        birthday=p.attributes.birthday,
                        timezone=p.attributes.timezone,
                        preferred_contact_hours=p.attributes.preferred_contact_hours,
                        approval_preference=p.attributes.approval_preference,
                        custom_notes=dict(p.attributes.custom_notes),
                    ),
                )
            )

        return PreActionCheckResponseDTO(
            action_type=result.action_type,
            action_summary=result.action_summary,
            has_missing_attributes=result.has_missing_attributes,
            has_weak_memory_warning=result.has_weak_memory_warning,
            participants=participants_dto,
            prompt_cue=result.prompt_cue,
            warnings=list(result.warnings),
        )
