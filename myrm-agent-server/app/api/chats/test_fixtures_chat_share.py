"""Local-only chat share Chrome E2E seed routes.

[INPUT]
app.config.deploy_mode::is_local_mode (POS: local/tauri gate)
app.services.agent.agent_service::AgentService (POS: agent list, first agent bound to the seed chat)
app.services.chat.chat_service::ChatService (POS: chat + message persistence)

[OUTPUT]
seed_chat_share_fixture: chat with a user + assistant exchange (public share page renderable)

[POS]
Mounted via test_fixtures router include.
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

_SHARE_USER_TEXT = "Chat share Chrome E2E fixture question"
_SHARE_ASSISTANT_TEXT = "Chat share Chrome E2E fixture answer — visible on the public share page."


@router.post("/test/seed-chat-share-fixture", include_in_schema=False)
async def seed_chat_share_fixture() -> dict[str, str]:
    """Local dev/test only: seed a chat with a renderable exchange for share Chrome E2E."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500,
            detail="No agents available for chat share E2E seed",
        )

    agent = agents[0]
    chat_id = f"e2eshare{uuid4().hex[:8]}"

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Chat share Chrome E2E",
            agent_id=agent.id,
            messages=[],
        ),
    )

    now = datetime.now(UTC)
    timezone = "UTC"
    await ChatService.append_message(chat_id, "user", _SHARE_USER_TEXT, now, timezone)
    await ChatService.append_message(chat_id, "assistant", _SHARE_ASSISTANT_TEXT, now, timezone)

    return {
        "chat_id": chat_id,
        "agent_id": agent.id,
        "user_text": _SHARE_USER_TEXT,
        "assistant_text": _SHARE_ASSISTANT_TEXT,
        "ui_path": f"/{chat_id}",
    }
