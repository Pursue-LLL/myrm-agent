"""
[POS] app/api/memory/dual_track_router.py
[INPUT] fastapi, app.schemas.memory_dual_track, app.services.memory.memory_dual_track_service
[OUTPUT] router

FastAPI router exposing dual-track memory extraction routing, anti-silent-drop destiny reporting, and procedural rules endpoints.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.memory_dual_track import (
    ExtractDualTrackRequestDTO,
    ExtractedProceduralRuleDTO,
    ExtractionDestinyReportDTO,
    FactQueryResponseDTO,
    ProceduralRuleQueryResponseDTO,
)
from app.services.memory.memory_dual_track_service import (
    MemoryDualTrackService,
    get_memory_dual_track_service,
)

router = APIRouter()


@router.post(
    "/dual-track/extract",
    response_model=ExtractionDestinyReportDTO,
    status_code=status.HTTP_200_OK,
    summary="Adaptive dual-track extraction with anti-silent-drop gateway",
)
def extract_dual_track(
    request: ExtractDualTrackRequestDTO,
    service: MemoryDualTrackService = Depends(get_memory_dual_track_service),
) -> ExtractionDestinyReportDTO:
    """Classify input text into procedural rules vs declarative facts, route accordingly, or produce transparent discard reason."""
    return service.extract_and_route(request)


@router.get(
    "/dual-track/rules",
    response_model=ProceduralRuleQueryResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="List stored operational procedural rules",
)
def list_rules(
    service: MemoryDualTrackService = Depends(get_memory_dual_track_service),
) -> ProceduralRuleQueryResponseDTO:
    """Retrieve all procedural operational rules ordered by priority descending."""
    rules = service.list_rules()
    return ProceduralRuleQueryResponseDTO(rules=rules, total=len(rules))


@router.get(
    "/dual-track/rules/{rule_id}",
    response_model=ExtractedProceduralRuleDTO,
    status_code=status.HTTP_200_OK,
    summary="Get single procedural rule by identifier",
)
def get_rule(
    rule_id: str,
    service: MemoryDualTrackService = Depends(get_memory_dual_track_service),
) -> ExtractedProceduralRuleDTO:
    """Retrieve specific procedural rule or return 404."""
    rule = service.get_rule(rule_id)
    if rule is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Procedural rule '{rule_id}' not found",
        )
    return rule


@router.get(
    "/dual-track/facts",
    response_model=FactQueryResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="List stored declarative facts",
)
def list_facts(
    service: MemoryDualTrackService = Depends(get_memory_dual_track_service),
) -> FactQueryResponseDTO:
    """Retrieve all extracted declarative facts."""
    facts = service.list_facts()
    return FactQueryResponseDTO(facts=facts, total=len(facts))
