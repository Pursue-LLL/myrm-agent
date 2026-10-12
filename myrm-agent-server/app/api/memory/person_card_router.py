"""API router for Person Card & Relationship Memory Layer.

[INPUT]
- HTTP requests for listing, creating, updating, merging person cards, and checking pre-action constraints.

[OUTPUT]
- JSON responses with PersonCardDTO, PreActionCheckResponseDTO, and mutation statuses.

[POS]
- FastAPI endpoints for Item 155 PersonCardAndRelationshipMemoryLayer.
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.person_card import (
    CreatePersonCardRequest,
    MergePersonCardRequest,
    PersonCardDTO,
    PreActionCheckRequestDTO,
    PreActionCheckResponseDTO,
    RelationTypeDTO,
    UpdatePersonCardRequest,
)
from app.services.memory.person_card_service import PersonCardService

router = APIRouter(prefix="/person-card", tags=["memory-person-card"])
_service = PersonCardService()


def get_person_card_service() -> PersonCardService:
    """Dependency helper to return the active PersonCardService."""
    return _service


@router.get("", response_model=list[PersonCardDTO])
async def list_person_cards(
    query: str | None = Query(default=None, description="Search query for name or alias"),
    scope: Literal["global", "agent"] | None = Query(default=None, description="Scope filter"),
    relation_type: RelationTypeDTO | None = Query(default=None, description="Relation type filter"),
    include_weak: bool = Query(default=True, description="Include weak memory cards"),
    include_archived: bool = Query(default=False, description="Include archived cards"),
    agent_id: str | None = Query(default=None, description="Agent ID when scoped to agent"),
) -> list[PersonCardDTO]:
    """List person cards matching criteria."""
    return get_person_card_service().list_persons(
        query=query,
        scope=scope,
        relation_type=relation_type,
        include_weak=include_weak,
        include_archived=include_archived,
        agent_id=agent_id,
    )


@router.post("", response_model=PersonCardDTO, status_code=status.HTTP_201_CREATED)
async def create_person_card(req: CreatePersonCardRequest) -> PersonCardDTO:
    """Create a new person card profile."""
    return get_person_card_service().create_person(req)


@router.get("/{person_id}", response_model=PersonCardDTO)
async def get_person_card(person_id: str) -> PersonCardDTO:
    """Fetch an individual person card by ID."""
    card = get_person_card_service().get_person(person_id)
    if card is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person card {person_id} not found",
        )
    return card


@router.put("/{person_id}", response_model=PersonCardDTO)
async def update_person_card(
    person_id: str, req: UpdatePersonCardRequest
) -> PersonCardDTO:
    """Update fields on an existing person card."""
    updated = get_person_card_service().update_person(person_id, req)
    if updated is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person card {person_id} not found",
        )
    return updated


@router.delete("/{person_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_person_card(person_id: str) -> None:
    """Delete a person card by ID."""
    deleted = get_person_card_service().delete_person(person_id)
    if not deleted:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Person card {person_id} not found",
        )


@router.post("/merge", response_model=PersonCardDTO)
async def merge_person_cards(req: MergePersonCardRequest) -> PersonCardDTO:
    """Merge source person card into target person card."""
    try:
        return get_person_card_service().merge_persons(
            source_id=req.source_person_id,
            target_id=req.target_person_id,
        )
    except ValueError as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e),
        ) from e


@router.post("/pre-action-check", response_model=PreActionCheckResponseDTO)
async def pre_action_check(
    req: PreActionCheckRequestDTO,
) -> PreActionCheckResponseDTO:
    """Perform pre-action attribute verification for proactive fulfillment."""
    return get_person_card_service().pre_action_check(req)


@router.post("/refresh-decay")
async def refresh_decay_scores(
    weak_threshold: float = Query(default=0.3, ge=0.0, le=1.0)
) -> dict[str, float]:
    """Trigger gravity decay refresh on all stored cards."""
    return get_person_card_service().refresh_decay(weak_threshold=weak_threshold)
