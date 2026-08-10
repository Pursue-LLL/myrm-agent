"""Local-only voice background task seed for Chrome E2E.

[INPUT]
- .test_fixtures::_ensure_e2e_chat (POS: create a local e2e web chat)
- app.services.agent.agent_service::AgentService (POS: resolve default agent)
- app.core.channel_bridge.persistent_background::BACKGROUND_SOURCE_VOICE (POS: voice task source)
- app.services.kanban.event_publisher::emit_source_chat_done (POS: BACKGROUND_TASK_DONE publisher)
- myrm_agent_harness.toolkits.kanban.types::KanbanTask/TaskPriority/TaskStatus (POS: Kanban DTOs)

[OUTPUT]
- POST /background-tasks/test/seed-voice-done: seed a completed voice Kanban task and
  publish BACKGROUND_TASK_DONE through the real Kanban event publisher.

[POS]
Voice background task E2E fixture. The running WebuiVoiceWorkNotifier appends the
result to the chat and broadcasts SYSTEM_NOTIFICATION (kind=voice_background_task_done)
over SSE — exactly what the WebUI voice-bg-done announcement consumes.
"""

from __future__ import annotations

import uuid

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.services.agent.agent_service import AgentService

from .test_fixtures import _ensure_e2e_chat

router = APIRouter()


@router.post("/test/seed-voice-done", include_in_schema=False)
async def seed_voice_done() -> dict[str, str]:
    """Local dev/test only: seed a completed voice background task for Chrome E2E.

    Walks the real delivery path end to end: creates a web chat, then builds a
    voice Kanban task and publishes BACKGROUND_TASK_DONE via the real Kanban
    event publisher. The running WebuiVoiceWorkNotifier appends the result to
    the chat and broadcasts SYSTEM_NOTIFICATION (kind=voice_background_task_done)
    over SSE — exactly what the WebUI voice-bg-done announcement consumes.

    A KanbanTask is constructed in memory (no dispatcher wake) so the seed
    stays deterministic and does not start a real agent run.
    """
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    from myrm_agent_harness.toolkits.kanban.types import (
        KANBAN_SOURCE_CHAT_METADATA_KEY,
        KanbanTask,
        TaskPriority,
        TaskStatus,
    )

    from app.core.channel_bridge.persistent_background import BACKGROUND_SOURCE_VOICE
    from app.services.kanban.event_publisher import emit_source_chat_done

    agents, _total = await AgentService.get_agent_list(1, 100)
    agent_id = agents[0].id if agents else None

    chat_id = f"e2evoice{uuid.uuid4().hex[:10]}"
    await _ensure_e2e_chat(chat_id)

    task_id = f"voice-e2e-{uuid.uuid4().hex[:8]}"
    task = KanbanTask(
        task_id=task_id,
        board_id="e2e-voice-board",
        title="Voice E2E background task",
        description="E2E voice background task",
        status=TaskStatus.COMPLETED,
        priority=TaskPriority.NORMAL,
        agent_id=agent_id,
        result="E2E voice background task result",
        metadata={
            "background_source": BACKGROUND_SOURCE_VOICE,
            "channel": "realtime_voice",
            "chat_id": chat_id,
            "user_id": "local-user",
            "locale": "en",
            KANBAN_SOURCE_CHAT_METADATA_KEY: chat_id,
        },
    )

    emit_source_chat_done("task_completed", task)

    return {"chat_id": chat_id, "task_id": task_id, "board_id": task.board_id}
