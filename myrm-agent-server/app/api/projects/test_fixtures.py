"""Local-only project turn-lock Chrome E2E seed routes.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.project.orchestrator::project_orchestrator (POS: project turn lock)
app.services.agent.agent_service::AgentService (POS: agent list for seed scope)
app.services.chat.chat_service::ChatService (POS: chat/message persistence)

[OUTPUT]
seed_turn_lock_fixture: project + bound chat + deterministically held turn lock
for Chrome E2E verifying the `waiting_for_turn` SSE path in a real UI turn.

[POS]
Local-only deterministic lock holder: acquiring the project lock here simulates
another agent actively running, so the next real UI turn reliably observes
waiting_for_turn → waiting_for_turn_clear without relying on flaky real
concurrency timing. Mounted via api/projects/__init__.py.
"""

from __future__ import annotations

import asyncio
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService
from app.services.project.orchestrator import project_orchestrator
from app.services.project.project_service import ProjectService

router = APIRouter()


@router.post("/test/seed-turn-lock", include_in_schema=False)
async def seed_turn_lock(hold_ms: int = 25000) -> dict[str, object]:
    """Local dev/test only: seed a project-bound chat and hold its turn lock.

    `hold_ms` controls how long the project lock is held; the lock is acquired
    synchronously before this handler returns, so a subsequent real agent turn
    is guaranteed to observe `waiting_for_turn` while another agent is running.
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    if hold_ms < 1000 or hold_ms > 60000:
        raise HTTPException(
            status_code=400,
            detail="hold_ms must be between 1000 and 60000",
        )

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500,
            detail="No agents available for turn-lock E2E seed",
        )
    agent = agents[0]

    project = await ProjectService.create_project(
        name=f"E2E Turn Lock {uuid4().hex[:8]}",
    )
    project_id = str(project["id"])

    chat_id = f"e2eturnlock{uuid4().hex[:8]}"
    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Turn lock Chrome E2E",
            agent_id=agent.id,
            messages=[],
        ),
    )
    moved = await ProjectService.move_chat_to_project(chat_id, project_id)
    if not moved:
        raise HTTPException(
            status_code=500,
            detail="Failed to bind chat to project for turn-lock E2E seed",
        )

    # Acquire deterministically before returning; the background task releases
    # after `hold_ms`, so the next agent turn blocks until then.
    await project_orchestrator.acquire(project_id)

    async def _release_later() -> None:
        await asyncio.sleep(hold_ms / 1000.0)
        project_orchestrator.release(project_id)

    asyncio.create_task(
        _release_later(),
        name=f"turn_lock_hold_{project_id}",
    )

    return {
        "project_id": project_id,
        "chat_id": chat_id,
        "ui_path": f"/{chat_id}",
        "hold_ms": hold_ms,
    }
