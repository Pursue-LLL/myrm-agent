"""API router for Cross-Source Context Fabric and Project Entity Linker (Item 153).

[INPUT]
- Text payloads, ProjectRegistryEntryDTO items, InsightSinkRequestDTO payloads.

[OUTPUT]
- Endpoints for project registration, entity extraction, project linking, and insight sinking.

[POS]
- Server-side API router for Item 153 CrossSourceWorkContextFabricAndProjectEntityLinkerSuite.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends

from app.schemas.context_fabric import (
    ExtractEntitiesRequestDTO,
    ExtractEntitiesResponseDTO,
    InsightSinkRequestDTO,
    InsightSinkResponseDTO,
    LinkEntitiesRequestDTO,
    LinkEntitiesResponseDTO,
    ProjectRegistryEntryDTO,
)
from app.services.memory.context_fabric_service import ContextFabricService

router = APIRouter(prefix="/context-fabric", tags=["context_fabric"])

_singleton_service: ContextFabricService | None = None


def get_context_fabric_service() -> ContextFabricService:
    """Dependency provider returning singleton ContextFabricService."""
    global _singleton_service
    if _singleton_service is None:
        _singleton_service = ContextFabricService()
    return _singleton_service


@router.post("/projects", response_model=ProjectRegistryEntryDTO)
def register_project(
    entry: ProjectRegistryEntryDTO,
    service: ContextFabricService = Depends(get_context_fabric_service),
) -> ProjectRegistryEntryDTO:
    """Register or update a canonical project in the workspace registry."""
    service.register_project(entry)
    return entry


@router.get("/projects", response_model=list[ProjectRegistryEntryDTO])
def list_projects(
    service: ContextFabricService = Depends(get_context_fabric_service),
) -> list[ProjectRegistryEntryDTO]:
    """List all currently registered projects."""
    return service.list_projects()


@router.post("/extract", response_model=ExtractEntitiesResponseDTO)
def extract_context_entities(
    payload: ExtractEntitiesRequestDTO,
    service: ContextFabricService = Depends(get_context_fabric_service),
) -> ExtractEntitiesResponseDTO:
    """Extract structured people, commitments, blockers, and modules from unstructured text."""
    return service.extract_entities(payload.text)


@router.post("/link", response_model=LinkEntitiesResponseDTO)
def link_text_to_projects(
    payload: LinkEntitiesRequestDTO,
    service: ContextFabricService = Depends(get_context_fabric_service),
) -> LinkEntitiesResponseDTO:
    """Link text to canonical projects with normalized confidence scoring."""
    return service.link_entities(payload.text, min_confidence=payload.min_confidence)


@router.post("/sink", response_model=InsightSinkResponseDTO)
def sink_project_insight(
    payload: InsightSinkRequestDTO,
    service: ContextFabricService = Depends(get_context_fabric_service),
) -> InsightSinkResponseDTO:
    """Sink derived conclusions into project memory blocks with full provenance."""
    return service.sink_insight(payload)
