"""Background task API routes.

Provides REST endpoints for frontend to query, cancel, and steer
background tasks spawned via /btw (/background /bg) slash commands.

[INPUT]
- app.core.channel_bridge.setup::get_background_task_handler (POS: Channel gateway lifecycle)
- app.core.channel_bridge.background_task_handler::ChannelBackgroundTaskHandler (POS: Background task handler)

[OUTPUT]
- router: FastAPI APIRouter with /background-tasks endpoints (list, get, cancel, steer)

[POS]
REST API layer for background task management. Exposes in-memory task state
from ChannelBackgroundTaskHandler to the frontend via standard HTTP endpoints.
"""

from __future__ import annotations

import logging

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.core.channel_bridge.setup import get_background_task_handler

logger = logging.getLogger(__name__)

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

    tasks = list(handler._tasks.values())
    return {
        "tasks": [
            BackgroundTaskResponse(
                task_id=t.task_id,
                prompt=t.prompt,
                status=t.status,
                created_at=t.created_at,
                completed_at=t.completed_at,
                result_preview=t.result[:200] if t.result else None,
            )
            for t in sorted(tasks, key=lambda x: x.created_at, reverse=True)
        ]
    }


@router.get("/{task_id}")
async def get_background_task(task_id: str) -> BackgroundTaskResponse:
    """Get a specific background task."""
    handler = get_background_task_handler()
    if not handler:
        raise HTTPException(status_code=404, detail="Background task handler not initialized")

    record = handler._tasks.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Background task not found")

    return BackgroundTaskResponse(
        task_id=record.task_id,
        prompt=record.prompt,
        status=record.status,
        created_at=record.created_at,
        completed_at=record.completed_at,
        result_preview=record.result[:200] if record.result else None,
    )


@router.post("/{task_id}/cancel")
async def cancel_background_task(task_id: str) -> dict[str, str]:
    """Cancel a running background task."""
    handler = get_background_task_handler()
    if not handler:
        raise HTTPException(status_code=404, detail="Background task handler not initialized")

    record = handler._tasks.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Background task not found")

    if record.status != "running":
        raise HTTPException(status_code=400, detail=f"Task is not running (status: {record.status})")

    from app.channels.types import InboundMessage

    synthetic_msg = InboundMessage(
        channel=record.channel,
        sender_id=record.chat_id,
        chat_id=record.chat_id,
        content="",
        user_id=record.user_id,
    )
    await handler.cancel_background(synthetic_msg, task_id)

    return {"message": "Background task cancelled", "task_id": task_id}


@router.post("/{task_id}/steer")
async def steer_background_task(task_id: str, body: SteerRequest) -> dict[str, str]:
    """Inject a steering instruction into a running background task."""
    handler = get_background_task_handler()
    if not handler:
        raise HTTPException(status_code=404, detail="Background task handler not initialized")

    record = handler._tasks.get(task_id)
    if not record:
        raise HTTPException(status_code=404, detail="Background task not found")

    if record.status != "running":
        raise HTTPException(status_code=400, detail=f"Task is not running (status: {record.status})")

    from app.channels.types import InboundMessage

    synthetic_msg = InboundMessage(
        channel=record.channel,
        sender_id=record.chat_id,
        chat_id=record.chat_id,
        content="",
        user_id=record.user_id,
    )

    success = await handler.steer_background(synthetic_msg, task_id, body.instruction)
    if not success:
        raise HTTPException(status_code=400, detail="Failed to steer task")

    return {"message": "Steering instruction sent", "task_id": task_id}


__all__ = ["router"]
