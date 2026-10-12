"""API router for Project Experience & ADR Flywheel suite (Item 154).

[INPUT]
- Narrative strings, IngestExperienceRequestDTO payloads, SniffMinefieldRequestDTO queries.

[OUTPUT]
- Endpoints for extracting experiences, ingesting into flywheel, listing experiences, and sniffing minefields.

[POS]
- Server-side API router for Item 154 ProjectExperienceAndADRFlywheelSuite.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.schemas.experience_flywheel import (
    EngineeringExperienceDTO,
    ExtractExperienceRequestDTO,
    ExtractExperienceResponseDTO,
    IngestExperienceRequestDTO,
    IngestExperienceResponseDTO,
    SniffMinefieldRequestDTO,
    SniffMinefieldResponseDTO,
)
from app.services.memory.experience_flywheel_service import ExperienceFlywheelService

router = APIRouter(prefix="/experience-flywheel", tags=["experience_flywheel"])

_singleton_service: ExperienceFlywheelService | None = None


def get_flywheel_service() -> ExperienceFlywheelService:
    """Dependency provider returning singleton ExperienceFlywheelService."""
    global _singleton_service
    if _singleton_service is None:
        _singleton_service = ExperienceFlywheelService()
    return _singleton_service


@router.post("/extract", response_model=ExtractExperienceResponseDTO)
def extract_experiences(
    payload: ExtractExperienceRequestDTO,
    service: ExperienceFlywheelService = Depends(get_flywheel_service),
) -> ExtractExperienceResponseDTO:
    """Extract structured Bug experiences and ADR items from task narratives."""
    return service.extract_experiences(payload.narrative, default_kind_str=payload.default_kind)


@router.post("/ingest", response_model=IngestExperienceResponseDTO)
def ingest_experience(
    payload: IngestExperienceRequestDTO,
    service: ExperienceFlywheelService = Depends(get_flywheel_service),
) -> IngestExperienceResponseDTO:
    """Ingest an experience into the causal flywheel and optionally sync to worktree dongles."""
    return service.ingest_experience(payload)


@router.get("/list", response_model=list[EngineeringExperienceDTO])
def list_experiences(
    kind: str | None = Query(default=None, description="Optional kind filter: bug_experience, architectural_decision"),
    service: ExperienceFlywheelService = Depends(get_flywheel_service),
) -> list[EngineeringExperienceDTO]:
    """List all ingested experiences in the flywheel."""
    return service.list_experiences(kind_str=kind)


@router.post("/sniff", response_model=SniffMinefieldResponseDTO)
def sniff_minefield(
    payload: SniffMinefieldRequestDTO,
    service: ExperienceFlywheelService = Depends(get_flywheel_service),
) -> SniffMinefieldResponseDTO:
    """Pre-sniff upcoming execution plan or candidate entities against historical minefields."""
    return service.sniff_minefield(payload)
