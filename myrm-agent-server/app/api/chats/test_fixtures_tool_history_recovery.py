"""Local-only tool_history recovery Chrome E2E seed routes.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: gate local-only access)
- app.services.agent.agent_service::AgentService (POS: resolve default agent)
- app.services.chat.chat_service::ChatService (POS: seed chat + messages)

[OUTPUT]
- router: POST /test/seed-tool-history-recovery-fixture (POS: E2E seed endpoint)

[POSITION] app.api.chats — Chrome E2E test fixture for tool_history_recovery UI.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService

router = APIRouter()

_RECOVERY_ANSWER = "Tool history recovery Chrome E2E fixture answer."


@router.post("/test/seed-tool-history-recovery-fixture", include_in_schema=False)
async def seed_tool_history_recovery_fixture() -> dict[str, str]:
    """Local dev/test only: seed chat with tool_history_recovery progress step."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500,
            detail="No agents available for tool-history recovery E2E seed",
        )

    agent = agents[0]
    chat_id = f"e2etoolhist{uuid4().hex[:8]}"
    message_id = str(uuid4())

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Tool history recovery Chrome E2E",
            agent_id=agent.id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    await ChatService.append_message(
        chat_id,
        "user",
        "Tool history recovery E2E fixture question",
        now,
        timezone,
    )

    extra_data: dict[str, object] = {
        "progressSteps": [
            {
                "step_key": "tool_history_recovery",
                "status": "success",
                "items": [],
            },
        ]
    }
    await ChatService.append_message(
        chat_id,
        "assistant",
        _RECOVERY_ANSWER,
        now,
        timezone,
        message_id=message_id,
        extra_data=extra_data,
    )

    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "ui_path": f"/{chat_id}",
        "agent_id": agent.id,
    }
