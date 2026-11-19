"""Local-only HTTP fixtures for media task Chrome E2E.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: local-only route guard)
- app.api.tasks.deps::get_task_store (POS: SQLiteTaskStore FastAPI dependency)
- app.ai_agents.media_tools.media_persist::create_media_persist_callback (POS: the production store-and-reference path)
- app.tasks.executors.image_executor::image_task_result (POS: the result shape of a finished image task)

[OUTPUT]
- seed_media_fixture: insert image_generate rows into live TaskStore for Panel E2E

[POS]
Tasks API local test fixture. Enables Chrome E2E to assert media Panel rows without LLM. A succeeded row holds an
image stored through the same callback the engines use, so its card loads a real file instead of a made-up address.
"""

from __future__ import annotations

import io
import uuid
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from myrm_agent_harness.toolkits.llms.image import MediaMeta
from myrm_agent_harness.toolkits.tasks import (
    ErrorRecoverability,
    Task,
    TaskError,
    TaskStatus,
    TaskStore,
)

from app.ai_agents.media_tools.media_persist import create_media_persist_callback
from app.api.tasks.deps import get_task_store
from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService
from app.tasks.executors.image_executor import image_task_result

router = APIRouter()

_FAILED_PROMPT = "MYRM_E2E_MEDIA_FAILED_PROMPT"
_SUCCEEDED_PROMPT = "MYRM_E2E_MEDIA_SUCCEEDED_PROMPT"
_RUNNING_PROMPT = "MYRM_E2E_MEDIA_RUNNING_PROMPT"
_FAILED_ERROR_MESSAGE = "MYRM_E2E_MEDIA_API_ERROR"
_FIXTURE_MODEL = "e2e-fixture"
_FIXTURE_IMAGE_SIDE = 64


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
    }


def _fixture_png() -> bytes:
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (_FIXTURE_IMAGE_SIDE, _FIXTURE_IMAGE_SIDE), (46, 92, 255)).save(buffer, format="PNG")
    return buffer.getvalue()


async def _store_fixture_image(chat_id: str) -> dict[str, object]:
    """Store a real image through the production persist callback and return the finished task's result."""
    persist = create_media_persist_callback(chat_id=chat_id, model_name=_FIXTURE_MODEL, source="e2e-fixture")
    meta = MediaMeta(prompt=_SUCCEEDED_PROMPT, model=_FIXTURE_MODEL, resolution=f"{_FIXTURE_IMAGE_SIDE}x{_FIXTURE_IMAGE_SIDE}")
    reference = await persist(_fixture_png(), "image/png", meta)
    return image_task_result(reference, "image/png", prompt=_SUCCEEDED_PROMPT, model=_FIXTURE_MODEL, latency_ms=1)


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
            result=await _store_fixture_image(chat_id),
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
