"""FastAPI router for Orchestrator Auto Squad Composition & Model-Deferred Wizard (Item 34).

[INPUT]
- app.schemas.squad_composition::{ComposeSquadBlueprintRequest, MaterializeSquadRequest, ...}
- app.services.agent.squad_composition_service::{SquadCompositionService, get_squad_composition_service}

[OUTPUT]
- Router mounted under /chats/{chat_id}/squad-composition.

[POS]
- HTTP endpoints for goal-driven team roster synthesis, Phase-2 Model-Deferred confirmation,
  and dynamic compute budget allocation.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, Depends, HTTPException, Path

from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.schemas.squad_composition import (
    ComposeSquadBlueprintRequest,
    MaterializeSquadRequest,
)
from app.services.agent.squad_composition_service import (
    SquadCompositionService,
    get_squad_composition_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/chats/{chat_id}/squad-composition", tags=["Squad Composition Wizard"])


@router.post(
    "/compose",
    response_model=StandardSuccessResponse,
    summary="Synthesize multi-agent roster blueprint from high-level goal (Phase 1)",
)
def compose_blueprint_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    req: ComposeSquadBlueprintRequest = ...,
    service: SquadCompositionService = Depends(get_squad_composition_service),
) -> StandardSuccessResponse:
    """Analyze high-level mission objective and output structured team blueprint with SOUL system prompts."""
    if req.session_id != chat_id:
        req = ComposeSquadBlueprintRequest(
            session_id=chat_id,
            goal_description=req.goal_description,
            total_budget_tokens=req.total_budget_tokens,
            total_max_cost_usd=req.total_max_cost_usd,
            max_descendants_per_run=req.max_descendants_per_run,
        )

    try:
        blueprint = service.compose_squad_blueprint(req)
        return create_success_response(data=blueprint)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get(
    "/blueprints/{squad_id}",
    response_model=StandardSuccessResponse,
    summary="Get synthesized squad blueprint by identifier",
)
def get_blueprint_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    squad_id: str = Path(..., description="Unique squad identifier"),
    service: SquadCompositionService = Depends(get_squad_composition_service),
) -> StandardSuccessResponse:
    """Fetch Phase-1 blueprint details, role breakdowns, and SOUL prompts."""
    bp = service.get_squad_blueprint(session_id=chat_id, squad_id=squad_id)
    if not bp:
        raise HTTPException(status_code=404, detail=f"Squad blueprint '{squad_id}' not found")
    return create_success_response(data=bp)


@router.get(
    "/blueprints",
    response_model=StandardSuccessResponse,
    summary="List all squad blueprints in this chat session",
)
def list_blueprints_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    service: SquadCompositionService = Depends(get_squad_composition_service),
) -> StandardSuccessResponse:
    """List all synthesized team blueprints for current session."""
    blueprints = service.list_squad_blueprints(session_id=chat_id)
    return create_success_response(data=blueprints)


@router.post(
    "/materialize",
    response_model=StandardSuccessResponse,
    summary="Confirm Model-Deferred choices and instantiate squad (Phase 2)",
)
def materialize_squad_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    req: MaterializeSquadRequest = ...,
    service: SquadCompositionService = Depends(get_squad_composition_service),
) -> StandardSuccessResponse:
    """Bind user-confirmed model selections per role and materialize active team."""
    if req.session_id != chat_id:
        req = MaterializeSquadRequest(
            session_id=chat_id,
            squad_id=req.squad_id,
            model_choices=req.model_choices,
            default_model_id=req.default_model_id,
        )

    try:
        materialized = service.materialize_squad(req)
        return create_success_response(data=materialized)
    except ValueError as err:
        raise HTTPException(status_code=400, detail=str(err)) from err


@router.get(
    "/squads/{squad_id}",
    response_model=StandardSuccessResponse,
    summary="Get materialized squad execution state",
)
def get_materialized_squad_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    squad_id: str = Path(..., description="Unique squad identifier"),
    service: SquadCompositionService = Depends(get_squad_composition_service),
) -> StandardSuccessResponse:
    """Retrieve fully instantiated squad execution context."""
    squad = service.get_materialized_squad(session_id=chat_id, squad_id=squad_id)
    if not squad:
        raise HTTPException(status_code=404, detail=f"Materialized squad '{squad_id}' not found")
    return create_success_response(data=squad)


@router.delete(
    "",
    response_model=StandardSuccessResponse,
    summary="Purge all squad blueprints and materialized state for the session",
)
def reset_session_endpoint(
    chat_id: str = Path(..., description="Unique chat session identifier"),
    service: SquadCompositionService = Depends(get_squad_composition_service),
) -> StandardSuccessResponse:
    """Clear all session squad composition data."""
    service.reset_session(session_id=chat_id)
    return create_success_response(data={"reset": True})
