"""Local-only Co-Pilot Chrome E2E seed routes.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
- app.services.chat.chat_service::ChatService (POS: chat persistence)
- app.services.copilot.run_digest_store::RunDigestStore (POS: run digest SSOT)

[OUTPUT]
- seed_copilot_fixture: chat + assistant markdown + active run digest

[POS]
Chats API local fixture for Lean Co-Pilot Chrome E2E without live LLM.
"""

from __future__ import annotations

from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService
from app.services.copilot.run_digest_store import RunDigestStore

router = APIRouter()

_ASSISTANT_MARKDOWN = "Co-Pilot E2E fixture — tool stderr: connection refused on port 8080."


@router.post("/test/seed-copilot-fixture", include_in_schema=False)
async def seed_copilot_fixture() -> dict[str, str]:
    """Local dev/test only: seed chat messages and an active run digest."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    chat_id = f"e2ecopilot{uuid4().hex[:10]}"
    now = datetime.now(UTC)
    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(status_code=500, detail="No agents available for Co-Pilot E2E seed")
    agent_id = agents[0].id

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="E2E Co-Pilot",
            agent_id=agent_id,
            messages=[],
        ),
    )
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content="Co-Pilot E2E fixture user prompt",
        sent_at=now,
        sent_timezone="UTC",
        message_id=f"msg_user_{uuid4().hex[:8]}",
        action_mode="agent",
        agent_id=agent_id,
    )
    await ChatService.append_message(
        chat_id,
        "assistant",
        _ASSISTANT_MARKDOWN,
        now,
        "UTC",
    )

    RunDigestStore.begin_run(chat_id)
    RunDigestStore.update_from_progress(
        chat_id,
        [{"tool_name": "web_search", "step_key": "ws1", "status": "running"}],
    )

    return {
        "chat_id": chat_id,
        "ui_path": f"/{chat_id}",
        "mobile_path": f"/mobile/status/{chat_id}",
        "assistant_snippet": "connection refused",
    }
