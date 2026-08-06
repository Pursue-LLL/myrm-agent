"""Local-only memory lifecycle Chrome E2E seed routes.

[INPUT]
- app.config.deploy_mode::is_local_mode (POS: gate local-only access)
- app.services.chat.chat_service::ChatService (POS: seed chat + messages)
- app.services.memory.operation_ledger::MemoryOperationLedgerService (POS: ledger trace hydrate)

[OUTPUT]
- router: POST /test/seed-memory-lifecycle-fixture (POS: E2E seed for extract error timeline)

[POS] app.api.chats — Chrome E2E fixture for MemoryInsightPanel lifecycle strip + retry.
"""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import APIRouter, HTTPException
from myrm_agent_harness.toolkits.memory import (
    MemoryOperationKind,
    MemoryOperationStatus,
)

from app.config.deploy_mode import is_local_mode
from app.database.connection import get_session
from app.database.dto import ChatCreate
from app.services.agent.agent_service import AgentService
from app.services.chat.chat_service import ChatService
from app.services.memory.operation_ledger import MemoryOperationLedgerService

router = APIRouter()

_FIXTURE_USER = "Remember I do not eat cilantro (memory lifecycle E2E fixture)."
_FIXTURE_ASSISTANT = "Noted — I will remember your food preference."


@router.post("/test/seed-memory-lifecycle-fixture", include_in_schema=False)
async def seed_memory_lifecycle_fixture() -> dict[str, str]:
    """Local dev/test only: seed chat + ledger write/extract error for lifecycle UI."""
    if not is_local_mode():
        raise HTTPException(status_code=404, detail="Not found")

    agents, _total = await AgentService.get_agent_list(1, 100)
    if not agents:
        raise HTTPException(
            status_code=500, detail="No agents available for memory lifecycle E2E seed"
        )

    agent = agents[0]
    chat_id = f"e2ememlife{uuid4().hex[:8]}"
    message_id = str(uuid4())
    base = datetime.now(UTC)
    user_time = base
    # Assistant must precede ledger events for P1 isTraceMemoryEventForMessage (messageCreatedAtMs gate).
    assistant_time = base + timedelta(milliseconds=200)
    ledger_time = base + timedelta(seconds=2)
    timezone = "UTC"

    await ChatService.create_or_update_chat(
        ChatCreate(
            chat_id=chat_id,
            title="Memory lifecycle E2E fixture",
            agent_id=agent.id,
            messages=[],
        ),
    )
    await ChatService.append_message(
        chat_id, "user", _FIXTURE_USER, user_time, timezone
    )
    await ChatService.append_message(
        chat_id,
        "assistant",
        _FIXTURE_ASSISTANT,
        assistant_time,
        timezone,
        message_id=message_id,
    )

    async with get_session() as db:
        ledger = MemoryOperationLedgerService(db)
        await ledger.record_event(
            kind=MemoryOperationKind.WRITE,
            status=MemoryOperationStatus.SUCCESS,
            summary="Memory write ok (E2E fixture)",
            source="e2e_memory_lifecycle_fixture",
            target_kind="chat",
            target_id=chat_id,
            metadata={"chat_id": chat_id, "phase": "write"},
            occurred_at=ledger_time,
            commit=False,
        )
        await ledger.record_event(
            kind=MemoryOperationKind.EXTRACT,
            status=MemoryOperationStatus.ERROR,
            summary="Memory extraction failed (E2E fixture 429)",
            source="e2e_memory_lifecycle_fixture",
            target_kind="chat",
            target_id=chat_id,
            metadata={"chat_id": chat_id, "phase": "extract"},
            occurred_at=ledger_time,
            commit=True,
        )

    return {
        "chat_id": chat_id,
        "message_id": message_id,
        "ui_path": f"/{chat_id}",
    }
