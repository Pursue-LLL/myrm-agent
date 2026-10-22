"""[INPUT]
- Query parameters: category, q
- Suggestion body: status, running_step_count, recent_tools, mastered_commands, max_results
- CommandMatrixService: Business layer service

[OUTPUT]
- GET /chats/commands/matrix: Returns system command matrix catalog (filtered or full)
- POST /chats/{chat_id}/commands/suggest: Evaluates runtime context and yields progressive hint chips

[POS]
API route layer for Context-Aware Capability Discovery & Interactive Command Matrix (Item 38 P0).
"""

from __future__ import annotations

from typing import Literal

from fastapi import APIRouter, Query
from fastapi.responses import JSONResponse
from pydantic import BaseModel, Field

from app.core.utils.response_utils import success_response
from app.schemas.responses import StandardSuccessResponse
from app.services.chat.command_matrix import CommandMatrixService

router = APIRouter()


class SuggestCommandsRequest(BaseModel):
    status: Literal["idle", "running", "paused", "interrupted", "error"] = Field(
        default="idle",
        description="Current session lifecycle status",
    )
    running_step_count: int = Field(
        default=0,
        ge=0,
        description="Active step execution counter",
    )
    recent_tools: list[str] = Field(
        default_factory=list,
        description="Recently used tool names in the current turn",
    )
    mastered_commands: list[str] = Field(
        default_factory=list,
        description="Commands the user already knows or dismissed",
    )
    max_results: int = Field(
        default=3,
        ge=1,
        le=10,
        description="Maximum hint chips to recommend",
    )


@router.get("/commands/matrix", response_model=StandardSuccessResponse)
async def get_command_matrix(
    category: str | None = Query(default=None, description="Filter by domain category"),
    q: str | None = Query(default=None, description="Fuzzy search keyword"),
) -> JSONResponse:
    """Returns the comprehensive command matrix catalog across 5 capability domains."""
    service = CommandMatrixService.get_instance()
    catalog = service.get_command_catalog(category=category, query=q)
    return success_response({"items": catalog, "total": len(catalog)})


@router.post("/{chat_id}/commands/suggest", response_model=StandardSuccessResponse)
async def suggest_context_commands(
    chat_id: str,
    body: SuggestCommandsRequest,
) -> JSONResponse:
    """Heuristically evaluates session lifecycle context and yields ranked capability discovery hint chips."""
    service = CommandMatrixService.get_instance()
    chips = service.suggest_commands(
        session_id=chat_id,
        status=body.status,
        running_step_count=body.running_step_count,
        recent_tools=body.recent_tools,
        mastered_commands=body.mastered_commands,
        max_results=body.max_results,
    )
    return success_response({"session_id": chat_id, "chips": chips, "total": len(chips)})
