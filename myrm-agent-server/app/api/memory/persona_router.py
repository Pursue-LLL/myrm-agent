"""
[POS] app/api/memory/persona_router.py
[INPUT] fastapi, app.schemas.memory_persona_router, app.services.memory.memory_persona_router_service
[OUTPUT] router

FastAPI router exposing endpoints for On-Demand Persona Skill and Anti-Pollution Context Router.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, status

from app.schemas.memory_persona_router import (
    RoutePersonaContextRequestDTO,
    RoutePersonaContextResponseDTO,
)
from app.services.memory.memory_persona_router_service import (
    MemoryPersonaRouterService,
    get_memory_persona_router_service,
)

router = APIRouter()


@router.post(
    "/persona/route-context",
    response_model=RoutePersonaContextResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="Evaluate turn intent and dynamically route on-demand persona facets with 100% technical suppression",
)
def route_persona_context(
    request: RoutePersonaContextRequestDTO,
    service: MemoryPersonaRouterService = Depends(
        get_memory_persona_router_service
    ),
) -> RoutePersonaContextResponseDTO:
    """Route user query against persona facets, enforcing zero context pollution on technical tasks."""
    return service.route_persona_context(request)
