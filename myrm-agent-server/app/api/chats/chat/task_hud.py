"""Session Task HUD & Anti-Compaction Task State API Router.

[INPUT]
- chat_id, task_id, AddTaskRequest, UpdateTaskRequest
- myrm_agent_harness.agent.context_management.session_task_state::SessionTaskState

[OUTPUT]
- GET /api/v1/chats/{chat_id}/tasks
- POST /api/v1/chats/{chat_id}/tasks
- PATCH /api/v1/chats/{chat_id}/tasks/{task_id}
- DELETE /api/v1/chats/{chat_id}/tasks/{task_id}

[POS]
Server API layer for Item 31 AntiCompactionPersistentTaskHudAndStateIsolationEngine.
Maintains session task state independent of LLM chat history.
Strictly under 250 lines. Zero `Any`.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException, status
from myrm_agent_harness.agent.context_management.session_task_state import (
    SessionTaskState,
    TaskItem,
    TaskStatus,
    format_compaction_immune_task_hud,
)
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

router = APIRouter(tags=["task-hud"])

# In-memory storage for session task states (single-node sandbox)
_SESSION_TASK_REGISTRY: dict[str, SessionTaskState] = {}


def get_or_create_session_tasks(session_id: str) -> SessionTaskState:
    """Retrieve or initialize the isolated task state machine for a session."""
    if session_id not in _SESSION_TASK_REGISTRY:
        _SESSION_TASK_REGISTRY[session_id] = SessionTaskState(session_id=session_id)
    return _SESSION_TASK_REGISTRY[session_id]


class TaskItemResponse(BaseModel):
    """Serialized representation of a single task item."""

    id: str
    title: str
    status: TaskStatus
    progress_percent: int
    details: str
    created_at: str
    updated_at: str


class SessionTaskHudResponse(BaseModel):
    """Aggregate response containing all tasks, overall progress, and HUD injection string."""

    session_id: str
    tasks: list[TaskItemResponse]
    overall_progress: int
    active_task_id: str | None
    hud_injection_text: str
    updated_at: str


class AddTaskRequest(BaseModel):
    """Payload to create or overwrite a task in the session."""

    id: str = Field(..., description="Unique task identifier, e.g. 'step_1'")
    title: str = Field(..., min_length=1, description="Concise task title")
    details: str = Field(default="", description="Optional task elaboration or parameters")
    status: TaskStatus = Field(default="pending", description="Initial task status")
    progress_percent: int = Field(default=0, ge=0, le=100, description="Task completion percentage")


class UpdateTaskRequest(BaseModel):
    """Payload to patch an existing task status or progress."""

    status: TaskStatus = Field(..., description="Target execution status")
    progress_percent: int | None = Field(default=None, ge=0, le=100, description="Optional progress override")
    details: str | None = Field(default=None, description="Optional updated task notes")


def _to_response_item(t: TaskItem) -> TaskItemResponse:
    return TaskItemResponse(
        id=t.id,
        title=t.title,
        status=t.status,
        progress_percent=t.progress_percent,
        details=t.details,
        created_at=t.created_at,
        updated_at=t.updated_at,
    )


@router.get("/{chat_id}/tasks", response_model=SessionTaskHudResponse)
async def get_chat_tasks(chat_id: str) -> SessionTaskHudResponse:
    """Fetch the persistent, compaction-immune task state for a session."""
    state = get_or_create_session_tasks(chat_id)
    active = state.get_active_task()

    return SessionTaskHudResponse(
        session_id=chat_id,
        tasks=[_to_response_item(t) for t in state.tasks],
        overall_progress=state.calculate_overall_progress(),
        active_task_id=active.id if active else None,
        hud_injection_text=format_compaction_immune_task_hud(state),
        updated_at=state.updated_at,
    )


@router.post("/{chat_id}/tasks", response_model=TaskItemResponse)
async def add_chat_task(chat_id: str, request: AddTaskRequest) -> TaskItemResponse:
    """Add a new task to the session state."""
    state = get_or_create_session_tasks(chat_id)
    task = state.add_task(
        task_id=request.id,
        title=request.title,
        details=request.details,
        status=request.status,
        progress_percent=request.progress_percent,
    )
    return _to_response_item(task)


@router.patch("/{chat_id}/tasks/{task_id}", response_model=TaskItemResponse)
async def update_chat_task(chat_id: str, task_id: str, request: UpdateTaskRequest) -> TaskItemResponse:
    """Atomically update an existing task status and progress."""
    state = get_or_create_session_tasks(chat_id)
    task = state.update_task_status(
        task_id=task_id,
        status=request.status,
        progress_percent=request.progress_percent,
        details=request.details,
    )
    if not task:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found in chat '{chat_id}'.",
        )
    return _to_response_item(task)


@router.delete("/{chat_id}/tasks/{task_id}", status_code=status.HTTP_204_NO_CONTENT)
async def delete_chat_task(chat_id: str, task_id: str) -> None:
    """Remove a task from the session task list."""
    state = get_or_create_session_tasks(chat_id)
    removed = state.remove_task(task_id)
    if not removed:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Task '{task_id}' not found in chat '{chat_id}'.",
        )
