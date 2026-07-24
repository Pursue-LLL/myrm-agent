"""Background task API routes.

Provides REST endpoints for frontend to query, cancel, and steer
background tasks. Agent tasks are persisted via the Kanban system;
shell jobs merge in-process harness registry with durable BackgroundJobStore.

[INPUT]
- app.core.channel_bridge.setup::get_background_task_handler (POS: Channel gateway lifecycle)
- app.core.channel_bridge.background_task_handler::ChannelBackgroundTaskHandler (POS: Background task handler)
- app.services.agent.shell_background_tasks (POS: registry + Store facade)

[OUTPUT]
- router: FastAPI APIRouter with /background-tasks endpoints (list, get, cancel, steer, shell stdin)

[POS]
REST API layer for background task management. Merges Kanban agent tasks and
shell jobs (live + durable) for the GUI Activity panel.
"""

from __future__ import annotations

import time
from typing import Literal

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.api.background_tasks.test_fixtures import (
    router as background_tasks_test_fixtures_router,
)
from app.core.channel_bridge.setup import get_background_task_handler
from app.services.agent.shell_background_tasks import (
    ShellBackgroundTaskDTO,
    cancel_shell_background_task,
    find_shell_background_task,
    list_shell_background_tasks,
    shell_registry_is_ephemeral,
    write_shell_background_stdin,
)

router = APIRouter(tags=["background-tasks"])

BackgroundTaskKind = Literal["agent", "shell"]


class BackgroundTaskResponse(BaseModel):
    """Single background task info for API response."""

    kind: BackgroundTaskKind = "agent"
    task_id: str
    prompt: str
    status: str
    created_at: float
    completed_at: float | None = None
    result_preview: str | None = None
    chat_id: str | None = None
    pid: int | None = None
    progress_percent: int | None = None
    exit_code: int | None = None
    error_category: str | None = None
    job_id: str | None = None
    vault_log_ref: str | None = None


class BackgroundTaskListResponse(BaseModel):
    """List payload including ephemeral shell registry notice."""

    tasks: list[BackgroundTaskResponse]
    registry_ephemeral: bool = True


class SteerRequest(BaseModel):
    """Request body for steering a background task."""

    instruction: str


class ShellStdinRequest(BaseModel):
    """Request body for writing to a shell background task stdin."""

    data: str = ""
    submit: bool = False
    close: bool = False


def _shell_row_to_response(row: ShellBackgroundTaskDTO) -> BackgroundTaskResponse:
    return BackgroundTaskResponse(
        kind="shell",
        task_id=row.task_id,
        prompt=row.prompt,
        status=row.status,
        created_at=row.created_at,
        completed_at=row.completed_at,
        result_preview=row.result_preview,
        chat_id=row.chat_id,
        pid=row.pid,
        progress_percent=row.progress_percent,
        exit_code=row.exit_code,
        error_category=row.error_category,
        job_id=row.job_id,
        vault_log_ref=row.vault_log_ref,
    )


async def _list_agent_tasks() -> list[BackgroundTaskResponse]:
    handler = get_background_task_handler()
    if not handler:
        return []

    from app.channels.types import InboundMessage

    synthetic_msg = InboundMessage(
        channel="webui",
        sender_id="webui",
        chat_id="webui",
        content="",
        user_id="webui",
    )
    task_infos = await handler.list_background(synthetic_msg)
    return [
        BackgroundTaskResponse(
            kind="agent",
            task_id=t.task_id,
            prompt=t.prompt,
            status=t.status,
            created_at=t.created_at,
            completed_at=t.completed_at,
            result_preview=t.result_preview,
        )
        for t in task_infos
    ]


@router.get("")
async def list_background_tasks() -> BackgroundTaskListResponse:
    """List agent (Kanban) and shell (harness registry) background tasks."""
    agent_tasks = await _list_agent_tasks()
    shell_tasks = [_shell_row_to_response(row) for row in list_shell_background_tasks()]
    merged = agent_tasks + shell_tasks
    merged.sort(key=lambda t: t.created_at, reverse=True)
    return BackgroundTaskListResponse(
        tasks=merged,
        registry_ephemeral=shell_registry_is_ephemeral(),
    )


@router.get("/{task_id}")
async def get_background_task(task_id: str) -> BackgroundTaskResponse:
    """Get a specific background task."""
    if task_id.startswith("shell:"):
        suffix = task_id.split(":", maxsplit=1)[1] if ":" in task_id else ""
        if not suffix:
            raise HTTPException(status_code=404, detail="Invalid shell task id")
        row = find_shell_background_task(suffix)
        if row is None:
            raise HTTPException(
                status_code=404, detail="Shell background task not found"
            )
        return _shell_row_to_response(row)

    handler = get_background_task_handler()
    if not handler:
        raise HTTPException(
            status_code=404, detail="Background task handler not initialized"
        )

    from app.services.kanban import KanbanService

    svc = KanbanService.get_instance()
    task = await svc.store.get_task(task_id)
    if not task:
        raise HTTPException(status_code=404, detail="Background task not found")

    from app.core.channel_bridge.background_task_handler import (
        _kanban_status_to_bg_status,
    )

    status = _kanban_status_to_bg_status(task.status, task.error)
    completed_at = task.completed_at.timestamp() if task.completed_at else None
    created_at = task.created_at.timestamp() if task.created_at else time.time()

    return BackgroundTaskResponse(
        kind="agent",
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
    if task_id.startswith("shell:"):
        suffix = task_id.split(":", maxsplit=1)[1] if ":" in task_id else ""
        if not suffix:
            raise HTTPException(status_code=400, detail="Invalid shell task id")
        row = find_shell_background_task(suffix)
        if row is None or row.pid is None:
            raise HTTPException(
                status_code=400, detail="Shell task is not cancellable or not found"
            )
        success = await cancel_shell_background_task(row.pid)
        if not success:
            raise HTTPException(
                status_code=400, detail="Shell task is not cancellable or not found"
            )
        return {"message": "Shell background task cancelled", "task_id": task_id}

    handler = get_background_task_handler()
    if not handler:
        raise HTTPException(
            status_code=404, detail="Background task handler not initialized"
        )

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
        raise HTTPException(
            status_code=400, detail="Task is not cancellable or not found"
        )

    return {"message": "Background task cancelled", "task_id": task_id}


@router.post("/{task_id}/stdin")
async def shell_background_stdin(
    task_id: str, body: ShellStdinRequest
) -> dict[str, object]:
    """Write to a running shell background task stdin (GUI manual input)."""
    if not task_id.startswith("shell:"):
        raise HTTPException(status_code=400, detail="Not a shell background task")
    suffix = task_id.split(":", maxsplit=1)[1] if ":" in task_id else ""
    if not suffix:
        raise HTTPException(status_code=400, detail="Invalid shell task id")
    row = find_shell_background_task(suffix)
    if row is None or row.pid is None:
        raise HTTPException(status_code=404, detail="Shell background task not found")
    if row.status != "running":
        raise HTTPException(status_code=400, detail="Shell task is not running")
    result = await write_shell_background_stdin(
        row.pid,
        body.data,
        submit=body.submit,
        close=body.close,
    )
    if not result.get("ok"):
        raise HTTPException(
            status_code=400, detail=str(result.get("error", "stdin_failed"))
        )
    return {"message": "Shell stdin written", "task_id": task_id, "result": result}


@router.post("/{task_id}/steer")
async def steer_background_task(task_id: str, body: SteerRequest) -> dict[str, str]:
    """Inject a steering instruction into a running background task."""
    if task_id.startswith("shell:"):
        raise HTTPException(
            status_code=400, detail="Shell tasks do not support steering"
        )

    handler = get_background_task_handler()
    if not handler:
        raise HTTPException(
            status_code=404, detail="Background task handler not initialized"
        )

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
        raise HTTPException(
            status_code=400,
            detail="Failed to steer task (not running or tokens unavailable)",
        )

    return {"message": "Steering instruction sent", "task_id": task_id}


router.include_router(background_tasks_test_fixtures_router)


__all__ = ["router"]
