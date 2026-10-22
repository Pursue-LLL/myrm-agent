"""FastAPI router for Visual Kanban Multi-Agent Workflow Dispatcher and Card Handoff (Item 66).

[INPUT]
- app.schemas.kanban_dispatcher::{
    CreateCardRequest, TransitionCardRequest, UpdateProgressRequest,
    FlagBlockerRequest, KanbanColumnDTOEnum,
  }
- app.services.agent.kanban_dispatcher_service::KanbanDispatcherService

[OUTPUT]
- REST endpoints under /agents/kanban-dispatcher for card creation, column transitions,
  automated cross-agent handoffs, progress tracking, and blocker management.

[POS]
- HTTP API layer for Item 66 visual kanban multi-agent workflow dispatching.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, Query, status

from app.schemas.kanban_dispatcher import (
    CreateCardRequest,
    FlagBlockerRequest,
    KanbanColumnDTOEnum,
    TransitionCardRequest,
    UpdateProgressRequest,
)
from app.schemas.responses import StandardSuccessResponse, create_success_response
from app.services.agent.kanban_dispatcher_service import KanbanDispatcherService

logger = logging.getLogger(__name__)

router = APIRouter(
    prefix="/agents/kanban-dispatcher",
    tags=["Visual Kanban Multi-Agent Workflow Dispatcher"],
)


@router.post(
    "/cards",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Create a new kanban card",
)
async def create_card(req: CreateCardRequest) -> StandardSuccessResponse:
    """Create a new work item card in the kanban workspace."""
    try:
        card = KanbanDispatcherService.create_card(req)
        return create_success_response(data=card.model_dump())
    except Exception as exc:
        logger.exception("Failed to create kanban card: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.get(
    "/workspaces/{workspace_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get complete kanban workspace state",
)
async def get_workspace_state(workspace_id: str) -> StandardSuccessResponse:
    """Retrieve full snapshot of the kanban board including cards and handoff history."""
    try:
        state = KanbanDispatcherService.get_workspace_state(workspace_id)
        return create_success_response(data=state.model_dump())
    except Exception as exc:
        logger.exception("Failed to fetch kanban workspace state: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get(
    "/workspaces/{workspace_id}/cards",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="List cards in a workspace",
)
async def list_cards(
    workspace_id: str,
    column: KanbanColumnDTOEnum | None = Query(
        default=None,
        description="Optional column filter",
    ),
) -> StandardSuccessResponse:
    """List cards in workspace, optionally filtered by column."""
    try:
        cards = KanbanDispatcherService.list_cards(workspace_id, column)
        return create_success_response(data=[c.model_dump() for c in cards])
    except Exception as exc:
        logger.exception("Failed to list kanban cards: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.get(
    "/workspaces/{workspace_id}/cards/{card_id}",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Get details of a single card",
)
async def get_card(workspace_id: str, card_id: str) -> StandardSuccessResponse:
    """Fetch details of a single kanban task card."""
    try:
        card = KanbanDispatcherService.get_card(workspace_id, card_id)
        if card is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Card '{card_id}' not found in workspace '{workspace_id}'",
            )
        return create_success_response(data=card.model_dump())
    except HTTPException:
        raise
    except Exception as exc:
        logger.exception("Failed to fetch kanban card: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=str(exc),
        ) from exc


@router.post(
    "/workspaces/{workspace_id}/cards/{card_id}/transition",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Transition card to a new column with automated agent handoff",
)
async def transition_card(
    workspace_id: str,
    card_id: str,
    req: TransitionCardRequest,
) -> StandardSuccessResponse:
    """Transition card column, reassign agent profile, package handoff context, and record event."""
    try:
        card = KanbanDispatcherService.transition_card(workspace_id, card_id, req)
        return create_success_response(data=card.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to transition kanban card: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/workspaces/{workspace_id}/cards/{card_id}/progress",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Update execution progress percent",
)
async def update_progress(
    workspace_id: str,
    card_id: str,
    req: UpdateProgressRequest,
) -> StandardSuccessResponse:
    """Update progress percentage for a card in execution."""
    try:
        card = KanbanDispatcherService.update_progress(workspace_id, card_id, req)
        return create_success_response(data=card.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to update card progress: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/workspaces/{workspace_id}/cards/{card_id}/block",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Flag card as blocked",
)
async def flag_blocker(
    workspace_id: str,
    card_id: str,
    req: FlagBlockerRequest,
) -> StandardSuccessResponse:
    """Mark card as blocked pending human review or dependency resolution."""
    try:
        card = KanbanDispatcherService.flag_blocker(workspace_id, card_id, req)
        return create_success_response(data=card.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to flag card blocker: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.post(
    "/workspaces/{workspace_id}/cards/{card_id}/unblock",
    response_model=StandardSuccessResponse,
    status_code=status.HTTP_200_OK,
    summary="Resolve blocker on card",
)
async def resolve_blocker(
    workspace_id: str,
    card_id: str,
) -> StandardSuccessResponse:
    """Clear blocker on card and resume accepted status."""
    try:
        card = KanbanDispatcherService.resolve_blocker(workspace_id, card_id)
        return create_success_response(data=card.model_dump())
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except Exception as exc:
        logger.exception("Failed to resolve card blocker: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc
