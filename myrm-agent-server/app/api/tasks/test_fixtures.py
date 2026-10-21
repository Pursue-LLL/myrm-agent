"""Local-only HTTP fixtures for media task Chrome E2E.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: local-only route guard)
- app.lifecycle.task_worker::get_task_store (POS: SQLiteTaskStore provider)

[OUTPUT]
- seed_media_fixture: insert image_generate rows into live TaskStore for Panel E2E

[POS]
Tasks API local test fixture. Enables Chrome E2E to assert media Panel rows without LLM.
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from myrm_agent_harness.toolkits.tasks import (
    ErrorRecoverability,
    Task,
    TaskError,
    TaskStatus,
    TaskStore,
)

from app.api.tasks.deps import get_task_store
from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService

router = APIRouter()

_FAILED_PROMPT = "MYRM_E2E_MEDIA_FAILED_PROMPT"
_SUCCEEDED_PROMPT = "MYRM_E2E_MEDIA_SUCCEEDED_PROMPT"
_RUNNING_PROMPT = "MYRM_E2E_MEDIA_RUNNING_PROMPT"
_FAILED_ERROR_MESSAGE = "MYRM_E2E_MEDIA_API_ERROR"


async def _ensure_e2e_chat(chat_id: str) -> None:
    agents, _total = await AgentService.get_agent_list(1, 100)
    agent_id = agents[0].id if agents else None
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Media task Chrome E2E",
            agent_id=agent_id,
            messages=[],
        ),
    )


def _new_task_id() -> str:
    return f"img-e2e-{uuid.uuid4().hex[:8]}"


def _base_payload(*, chat_id: str, prompt: str) -> dict[str, object]:
    return {
        "prompt": prompt,
        "chat_id": chat_id,
        "size": "1024x1024",
        "quality": "standard",
    }


@router.post("/test/seed-media-fixture", include_in_schema=False)
async def seed_media_fixture(
    mode: Literal["failed", "succeeded", "running"] = Query(default="failed"),
    store: TaskStore = Depends(get_task_store),
) -> dict[str, object]:
    """Local dev/test only: seed an image_generate task row for Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    chat_id = f"e2e-media-{uuid.uuid4().hex[:10]}"
    await _ensure_e2e_chat(chat_id)

    task_id = _new_task_id()
    now = datetime.now(UTC)

    if mode == "running":
        task = Task(
            task_id=task_id,
            task_type="image_generate",
            user_id="local",
            status=TaskStatus.RUNNING,
            payload=_base_payload(chat_id=chat_id, prompt=_RUNNING_PROMPT),
            started_at=now,
            progress=0.42,
            progress_message="MYRM_E2E_MEDIA_RUNNING",
        )
    elif mode == "succeeded":
        task = Task(
            task_id=task_id,
            task_type="image_generate",
            user_id="local",
            status=TaskStatus.SUCCEEDED,
            payload=_base_payload(chat_id=chat_id, prompt=_SUCCEEDED_PROMPT),
            started_at=now,
            completed_at=now,
            progress=1.0,
            result={"image_urls": ["https://cdn.example/e2e-media.png"]},
        )
    else:
        task = Task(
            task_id=task_id,
            task_type="image_generate",
            user_id="local",
            status=TaskStatus.FAILED,
            payload=_base_payload(chat_id=chat_id, prompt=_FAILED_PROMPT),
            started_at=now,
            completed_at=now,
            progress=0.0,
            error=TaskError(
                error_type="api_error",
                message=_FAILED_ERROR_MESSAGE,
                recoverable=ErrorRecoverability.PERMANENT,
            ),
        )

    await store.create_task(task)

    return {
        "task_id": task_id,
        "chat_id": chat_id,
        "task_type": task.task_type,
        "status": task.status.value,
        "prompt": task.payload.get("prompt"),
    }
