"""Local-only stream retry busy Chrome E2E seed routes.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: restrict seed endpoints to local/tauri)
- app.services.agent.agent_service::AgentService (POS: pick agent for E2E seed chat)
- app.services.agent.gateway::get_agent_gateway (POS: reserve/release session lock)
- app.services.chat.chat_service::ChatService (POS: chat + user message persistence)

[OUTPUT]
- seed_stream_retry_busy_fixture: create chat, hold gateway session until release
- release_stream_retry_busy_fixture: release held session for reconnect contract E2E

[POS]
Chats API local fixture for stream retry / AgentBusy Chrome E2E without live LLM.
"""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from uuid import uuid4

from fastapi import APIRouter, HTTPException

from app.config.deploy_mode import is_local_mode
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.agent.gateway import get_agent_gateway
from app.services.chat.chat_service import ChatService

router = APIRouter()

_BUSY_HOLD_EVENTS: dict[str, asyncio.Event] = {}
_BUSY_QUERY_TEXT = "E2E stream retry busy fixture ping message"


async def _hold_busy_session(chat_id: str) -> None:
    event = asyncio.Event()
    _BUSY_HOLD_EVENTS[chat_id] = event
    try:
        await event.wait()
    finally:
        _BUSY_HOLD_EVENTS.pop(chat_id, None)
        get_agent_gateway().release_session(chat_id)


@router.post("/test/seed-stream-retry-busy-fixture", include_in_schema=False)
async def seed_stream_retry_busy_fixture() -> dict[str, str]:
    """Seed chat + user message and hold gateway session lock until release."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    chat_id = f"e2estreamretry{uuid4().hex[:10]}"
    message_id = f"msg_{uuid4().hex[:12]}"
    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(status_code=500, detail="No agents available for stream retry busy E2E seed")
    agent_id = agents[0].id

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="E2E Stream Retry Busy",
            agent_id=agent_id,
            messages=[],
        ),
    )
    await ChatService.ensure_chat_and_append_user_message(
        chat_id=chat_id,
        content=_BUSY_QUERY_TEXT,
        sent_at=datetime.now(UTC),
        sent_timezone="UTC",
        message_id=message_id,
        action_mode="agent",
        agent_id=agent_id,
    )

    gateway = get_agent_gateway()
    gateway.reserve_session(chat_id, active_message_id=message_id)
    asyncio.create_task(_hold_busy_session(chat_id), name=f"stream-retry-busy-{chat_id}")

    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "query": _BUSY_QUERY_TEXT,
        "ui_path": f"/{chat_id}",
    }


@router.post("/test/release-stream-retry-busy-fixture", include_in_schema=False)
async def release_stream_retry_busy_fixture(chat_id: str) -> dict[str, bool]:
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")
    event = _BUSY_HOLD_EVENTS.get(chat_id.strip())
    if event is None:
        get_agent_gateway().release_session(chat_id.strip())
        return {"released": True, "had_hold_task": False}
    event.set()
    return {"released": True, "had_hold_task": True}
