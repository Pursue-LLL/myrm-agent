"""REST endpoints for lineage dedup, automation demotion, and adaptive hydration.

[POS]
app/api/memory/conversation_lineage_defense_router.py

[INPUT]
- FastAPI APIRouter, Depends, conversation lineage defense DTOs and service

[OUTPUT]
- REST endpoints for lineage dedup, automation demotion, and adaptive hydration
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.conversation_lineage_defense import (
    LineageDefenseAuditRequestDTO,
    LineageDefenseSearchRequestDTO,
    LineageDefenseSearchResponseDTO,
    LineageDefenseStatsDTO,
)
from app.services.memory.conversation_lineage_defense_service import (
    ConversationLineageDefenseService,
    get_conversation_lineage_defense_service,
)

router = APIRouter(prefix="/lineage-defense", tags=["conversation-lineage-defense"])


@router.post("/search", response_model=LineageDefenseSearchResponseDTO)
def search_with_defense(
    payload: LineageDefenseSearchRequestDTO,
    service: ConversationLineageDefenseService = Depends(
        get_conversation_lineage_defense_service
    ),
) -> LineageDefenseSearchResponseDTO:
    """Execute conversation search defended against cron domination and multi-gen bloat."""
    return service.search_with_defense(payload)


@router.post("/audit", response_model=LineageDefenseSearchResponseDTO)
def audit_lineage_defense(
    payload: LineageDefenseAuditRequestDTO,
    service: ConversationLineageDefenseService = Depends(
        get_conversation_lineage_defense_service
    ),
) -> LineageDefenseSearchResponseDTO:
    """Audit candidate sessions to evaluate lineage dedup and automation suppression."""
    search_payload = LineageDefenseSearchRequestDTO(
        query="Audit Evaluation",
        limit=10,
        include_internal=payload.include_internal,
        window_size=payload.window_size,
        cron_weight_multiplier=payload.cron_weight_multiplier,
        candidates=payload.candidates,
    )
    return service.search_with_defense(search_payload)


@router.get("/stats", response_model=LineageDefenseStatsDTO)
def get_defense_stats(
    service: ConversationLineageDefenseService = Depends(
        get_conversation_lineage_defense_service
    ),
) -> LineageDefenseStatsDTO:
    """Fetch overview metrics on recall blindness defense and token economics."""
    return service.get_stats()
