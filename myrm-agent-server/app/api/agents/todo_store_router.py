"""
[POS] app/api/agents/todo_store_router.py
[INPUT] fastapi, app.schemas.todo_store, app.services.agent.todo_store_service
[OUTPUT] router

FastAPI router exposing shared Todo plan store and terminal-escape safe HUD projections.
Strict typing applied: No `Any` types allowed.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status

from app.schemas.todo_store import (
    CreateTodoItemRequestDTO,
    TodoHudProjectionDTO,
    TodoItemDTO,
    TodoListResponseDTO,
    UpdateTodoItemRequestDTO,
)
from app.services.agent.todo_store_service import (
    TodoStoreService,
    get_todo_store_service,
)

router = APIRouter()


@router.get(
    "/todo-store/{session_id}/hud",
    response_model=TodoHudProjectionDTO,
    status_code=status.HTTP_200_OK,
    summary="Get sanitized, terminal-escape safe HUD projection of session Todo plan",
)
def get_session_todo_hud(
    session_id: str,
    service: TodoStoreService = Depends(get_todo_store_service),
) -> TodoHudProjectionDTO:
    """Retrieve read-only sanitized HUD projection with metrics and formatted lines."""
    return service.get_hud_projection(session_id)


@router.get(
    "/todo-store/{session_id}/items",
    response_model=TodoListResponseDTO,
    status_code=status.HTTP_200_OK,
    summary="List all declared plan items in session Todo store",
)
def list_session_todo_items(
    session_id: str,
    service: TodoStoreService = Depends(get_todo_store_service),
) -> TodoListResponseDTO:
    """List all plan items declared in the session's shared Todo store."""
    return service.list_items(session_id)


@router.post(
    "/todo-store/{session_id}/items",
    response_model=TodoItemDTO,
    status_code=status.HTTP_201_CREATED,
    summary="Declare a new plan item in session Todo store",
)
def create_session_todo_item(
    session_id: str,
    request: CreateTodoItemRequestDTO,
    service: TodoStoreService = Depends(get_todo_store_service),
) -> TodoItemDTO:
    """Add a new plan declaration, enforcing capacity and string length limits."""
    try:
        return service.add_item(session_id, request)
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.patch(
    "/todo-store/{session_id}/items/{item_id}",
    response_model=TodoItemDTO,
    status_code=status.HTTP_200_OK,
    summary="Update an existing plan item",
)
def update_session_todo_item(
    session_id: str,
    item_id: str,
    request: UpdateTodoItemRequestDTO,
    service: TodoStoreService = Depends(get_todo_store_service),
) -> TodoItemDTO:
    """Update title, description, status, or assignee of a plan item."""
    try:
        return service.update_item(session_id, item_id, request)
    except KeyError as exc:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=str(exc),
        ) from exc
    except ValueError as exc:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(exc),
        ) from exc


@router.delete(
    "/todo-store/{session_id}/items/{item_id}",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Remove a plan item from session Todo store",
)
def remove_session_todo_item(
    session_id: str,
    item_id: str,
    service: TodoStoreService = Depends(get_todo_store_service),
) -> None:
    """Remove a plan item by ID."""
    removed = service.remove_item(session_id, item_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Todo item '{item_id}' not found in session '{session_id}'.",
        )


@router.delete(
    "/todo-store/{session_id}/items",
    status_code=status.HTTP_204_NO_CONTENT,
    summary="Clear all plan items in session Todo store",
)
def clear_session_todo_items(
    session_id: str,
    service: TodoStoreService = Depends(get_todo_store_service),
) -> None:
    """Clear all plan declarations in session."""
    service.clear_items(session_id)
