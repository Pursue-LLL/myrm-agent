"""Background task API routes.

Provides REST endpoints for frontend to query, cancel, and steer
background tasks. Tasks are now persisted via the Kanban system,
providing durability, restart recovery, and zombie detection.

[INPUT]
- app.core.channel_bridge.setup::get_background_task_handler (POS: Channel gateway lifecycle)
- app.core.channel_bridge.background_task_handler::ChannelBackgroundTaskHandler (POS: Background task handler)

[OUTPUT]
- router: FastAPI APIRouter with /background-tasks endpoints (list, get, cancel, steer)

[POS]
REST API layer for background task management. Reads persistent task state
from the Kanban system via ChannelBackgroundTaskHandler, which delegates
to KanbanService for durable storage.
"""

from __future__ import annotations

import time

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.channel_bridge.setup import get_background_task_handler

router = APIRouter(tags=["background-tasks"])


class BackgroundTaskResponse(BaseModel):
    """Single background task info for API response."""

    task_id: str
    prompt: str
    status: str
    created_at: float
    completed_at: float | None = None
    result_preview: str | None = None


class SteerRequest(BaseModel):
    """Request body for steering a background task."""

    instruction: str


@router.get("")
async def list_background_tasks() -> dict[str, list[BackgroundTaskResponse]]:
    """List all background tasks."""
    handler = get_background_task_handler()
    if not handler:
        return {"tasks": []}

    from app.channels.types import InboundMessage

    synthetic_msg = InboundMessage(
        channel="webui",
        sender_id="webui",
        chat_id="webui",
        content="",
        user_id="webui",
    )
    task_infos = await handler.list_background(synthetic_msg)

    return {
        "tasks": [
            BackgroundTaskResponse(
                task_id=t.task_id,
                prompt=t.prompt,
                status=t.status,
                created_at=t.created_at,
                completed_at=t.completed_at,
                result_preview=t.result_preview,
            )
            for t in task_infos
        ]
    }


@router.get("/{task_id}")
async def get_background_task(task_id: str) -> BackgroundTaskResponse:
    """Get a specific background task."""
    handler = get_background_task_handler()
    if not handler:
        raise HTTPException(status_code=404, detail="Background task handler not initialized")

    from app.services.kanban import KanbanService

    svc = KanbanService.get_instance()
    task = await svc.store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Background task not found")

    from app.core.channel_bridge.background_task_handler import _kanban_status_to_bg_status

    status = _kanban_status_to_bg_status(task.status)
    completed_at = task.completed_at.timestamp() if task.completed_at else None
    created_at = task.created_at.timestamp() if task.created_at else time.time()

    return BackgroundTaskResponse(
        task_id=task.task_id,
        prompt=task.description or task.title,
        status=status,
        created_at=created_at,
        completed_at=completed_at,
        result_preview=None,
    )


@router.post("/{task_id}/cancel")
async def cancel_background_task(task_id: str) -> dict[str, str]:
    """Cancel a background task (running or queued)."""
    handler = get_background_task_handler()
    if not handler:
        raise HTTPException(status_code=404, detail="Background task handler not initialized")

    from app.channels.types import InboundMessage

    synthetic_msg = InboundMessage(
        channel="webui",
        sender_id="webui",
        chat_id="webui",
        content="",
        user_id="webui",
    )
    success = await handler.cancel_background(synthetic_msg, task_id)
    if not success:
        raise HTTPException(status_code=400, detail="Task is not cancellable or not found")

    return {"message": "Background task cancelled", "task_id": task_id}


@router.post("/{task_id}/steer")
async def steer_background_task(task_id: str, body: SteerRequest) -> dict[str, str]:
    """Inject a steering instruction into a running background task."""
    handler = get_background_task_handler()
    if not handler:
        raise HTTPException(status_code=404, detail="Background task handler not initialized")

    from app.channels.types import InboundMessage

    synthetic_msg = InboundMessage(
        channel="webui",
        sender_id="webui",
        chat_id="webui",
        content="",
        user_id="webui",
    )

    success = await handler.steer_background(synthetic_msg, task_id, body.instruction)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to steer task (not running or tokens unavailable)")

    return {"message": "Steering instruction sent", "task_id": task_id}


__all__ = ["router"]
